package relay

import (
	"backend/stream"
	"context"
	"fmt"
	"net"
	"time"

	"github.com/google/uuid"
	"github.com/pion/webrtc/v4"
)

type Relay struct {
	api    *webrtc.API
	hub    *hub
	config webrtc.Configuration
}

func New(iceServers []string) *Relay {
	mediaEngine := &webrtc.MediaEngine{}
	if err := mediaEngine.RegisterDefaultCodecs(); err != nil {
		panic(fmt.Errorf("relay: register default codecs: %w", err))
	}

	interceptorRegistry, err := newInterceptorRegistry(mediaEngine)
	if err != nil {
		panic(fmt.Errorf("relay: register interceptors: %w", err))
	}

	settingEngine := webrtc.SettingEngine{}
	if ip, err := primaryOutboundIP(); err == nil {
		settingEngine.SetIPFilter(func(candidate net.IP) bool { return candidate.Equal(ip) })
	}
	settingEngine.SetAnsweringDTLSRole(webrtc.DTLSRoleServer)

	return &Relay{
		api: webrtc.NewAPI(webrtc.WithMediaEngine(mediaEngine), webrtc.WithInterceptorRegistry(interceptorRegistry), webrtc.WithSettingEngine(settingEngine)),
		hub: newHub(),
		config: webrtc.Configuration{
			ICEServers: []webrtc.ICEServer{{URLs: iceServers}},
		},
	}
}

func (relay *Relay) Publish(ctx context.Context, id stream.ID, offerSDP string) (stream.Session, string, error) {
	if offerSDP == "" {
		return stream.Session{}, "", stream.ErrInvalidSDP
	}

	relay.hub.mu.Lock()
	if _, exists := relay.hub.streams[id]; exists {
		relay.hub.mu.Unlock()
		return stream.Session{}, "", stream.ErrAlreadyPublishing
	}
	as := &activeStream{
		id:              id,
		localTracks:     make(map[webrtc.RTPCodecType]*webrtc.TrackLocalStaticRTP),
		publisherSSRC:   make(map[webrtc.RTPCodecType]webrtc.SSRC),
		subscribers:     make(map[stream.SessionID]*webrtc.PeerConnection),
		dataSubscribers: make(map[stream.SessionID]*webrtc.DataChannel),
		ready:           make(chan struct{}),
		pending:         true,
	}
	relay.hub.streams[id] = as
	relay.hub.mu.Unlock()

	pc, err := relay.api.NewPeerConnection(relay.config)
	if err != nil {
		relay.hub.removeStream(id)
		return stream.Session{}, "", fmt.Errorf("relay: create publisher peer connection: %w", err)
	}
	as.publisherPC = pc
	relay.attachPublisherHandlers(pc, as)

	answer, err := negotiate(pc, offerSDP)
	if err != nil {
		_ = pc.Close()
		relay.hub.removeStream(id)
		return stream.Session{}, "", err
	}

	as.mu.Lock()
	as.pending = false
	as.mu.Unlock()

	sessionID := stream.SessionID(uuid.NewString())
	relay.hub.mu.Lock()
	relay.hub.sessions[sessionID] = &sessionEntry{streamID: id, role: stream.RolePublisher, pc: pc}
	relay.hub.mu.Unlock()

	return stream.Session{ID: sessionID, StreamID: id, Role: stream.RolePublisher}, answer, nil
}

func (relay *Relay) Subscribe(ctx context.Context, id stream.ID, offerSDP string) (stream.Session, string, error) {
	if offerSDP == "" {
		return stream.Session{}, "", stream.ErrInvalidSDP
	}

	relay.hub.mu.RLock()
	as, exists := relay.hub.streams[id]
	relay.hub.mu.RUnlock()
	if !exists {
		return stream.Session{}, "", stream.ErrStreamNotFound
	}

	waitCtx, cancel := context.WithTimeout(ctx, 5*time.Second)
	defer cancel()
	select {
	case <-as.ready:
	case <-waitCtx.Done():
		return stream.Session{}, "", stream.ErrStreamNotReady
	}

	pc, err := relay.api.NewPeerConnection(relay.config)
	if err != nil {
		return stream.Session{}, "", fmt.Errorf("relay: create subscriber peer connection: %w", err)
	}

	as.mu.Lock()
	for kind, track := range as.localTracks {
		sender, addErr := pc.AddTrack(track)
		if addErr != nil {
			as.mu.Unlock()
			_ = pc.Close()
			return stream.Session{}, "", fmt.Errorf("relay: attach %s track: %w", kind, addErr)
		}
		go forwardRTCP(sender, as)
	}
	as.mu.Unlock()

	sessionID := stream.SessionID(uuid.NewString())
	relay.attachSubscriberHandlers(pc, sessionID, id, as)

	// Registered before negotiation so a channel offered by the subscriber is
	// picked up as soon as it opens.
	relay.acceptDetectionsChannel(pc, sessionID, as)

	answer, err := negotiate(pc, offerSDP)
	if err != nil {
		as.removeDataSubscriber(sessionID)
		_ = pc.Close()
		return stream.Session{}, "", err
	}

	as.mu.Lock()
	as.subscribers[sessionID] = pc
	as.mu.Unlock()

	relay.hub.mu.Lock()
	relay.hub.sessions[sessionID] = &sessionEntry{streamID: id, role: stream.RoleSubscriber, pc: pc}
	relay.hub.mu.Unlock()

	return stream.Session{ID: sessionID, StreamID: id, Role: stream.RoleSubscriber}, answer, nil
}

func (relay *Relay) Teardown(ctx context.Context, sessionID stream.SessionID) error {
	relay.hub.mu.Lock()
	entry, exists := relay.hub.sessions[sessionID]
	if exists {
		delete(relay.hub.sessions, sessionID)
	}
	relay.hub.mu.Unlock()

	if !exists {
		return stream.ErrSessionNotFound
	}

	switch entry.role {
	case stream.RolePublisher:
		relay.hub.removeStream(entry.streamID)
	case stream.RoleSubscriber:
		relay.hub.removeSubscriber(entry.streamID, sessionID)
	}

	return entry.pc.Close()
}

func (relay *Relay) List(ctx context.Context) ([]stream.ID, error) {
	relay.hub.mu.RLock()
	defer relay.hub.mu.RUnlock()

	ids := make([]stream.ID, 0, len(relay.hub.streams))
	for id, as := range relay.hub.streams {
		as.mu.Lock()
		pending := as.pending
		as.mu.Unlock()
		if pending {
			continue
		}
		ids = append(ids, id)
	}
	return ids, nil
}

func (relay *Relay) requestPublisherKeyframe(as *activeStream) {
	as.mu.Lock()
	pc := as.publisherPC
	ssrc, ok := as.publisherSSRC[webrtc.RTPCodecTypeVideo]
	as.mu.Unlock()

	if !ok || pc == nil {
		return
	}
	requestKeyframe(pc, ssrc)
}

func primaryOutboundIP() (net.IP, error) {
	conn, err := net.Dial("udp", "8.8.8.8:80")
	if err != nil {
		return nil, err
	}
	defer conn.Close()
	return conn.LocalAddr().(*net.UDPAddr).IP, nil
}

func negotiate(pc *webrtc.PeerConnection, offerSDP string) (string, error) {
	offer := webrtc.SessionDescription{Type: webrtc.SDPTypeOffer, SDP: offerSDP}
	if err := pc.SetRemoteDescription(offer); err != nil {
		return "", fmt.Errorf("%w: %v", stream.ErrInvalidSDP, err)
	}

	answer, err := pc.CreateAnswer(nil)
	if err != nil {
		return "", fmt.Errorf("relay: create answer: %w", err)
	}

	gatherComplete := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(answer); err != nil {
		return "", fmt.Errorf("relay: set local description: %w", err)
	}
	<-gatherComplete

	local := pc.LocalDescription()
	if local == nil {
		return "", fmt.Errorf("relay: no local description after ICE gathering")
	}
	return local.SDP, nil
}
