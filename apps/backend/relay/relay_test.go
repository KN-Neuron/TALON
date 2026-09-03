package relay

import (
	"context"
	"sync"
	"testing"
	"time"

	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"

	"backend/stream"
)

// mediaSample returns a throwaway VP8 payload. The relay forwards RTP without
// decoding, so the bytes only need to exist for a track to be established.
func mediaSample() media.Sample {
	return media.Sample{Data: []byte{0x10, 0x00, 0x00}, Duration: 20 * time.Millisecond}
}

const testTimeout = 15 * time.Second

// newTestRelay builds a relay without the outbound-IP filter, which would
// otherwise discard loopback candidates and prevent local connections.
func newTestRelay(t *testing.T) *Relay {
	t.Helper()
	return New([]string{})
}

// publishTestStream connects a publisher with one video track and, optionally,
// a detections data channel. It returns the publisher's peer connection, the
// channel (nil when not requested) and the session.
func publishTestStream(t *testing.T, r *Relay, id stream.ID, withDetections bool) (*webrtc.PeerConnection, *webrtc.DataChannel, stream.Session) {
	t.Helper()

	pc, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		t.Fatalf("create publisher: %v", err)
	}
	t.Cleanup(func() { _ = pc.Close() })

	track, err := webrtc.NewTrackLocalStaticSample(
		webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeVP8},
		"video", "publisher",
	)
	if err != nil {
		t.Fatalf("create track: %v", err)
	}
	if _, err := pc.AddTrack(track); err != nil {
		t.Fatalf("add track: %v", err)
	}

	var dc *webrtc.DataChannel
	if withDetections {
		ordered := false
		maxRetransmits := uint16(0)
		dc, err = pc.CreateDataChannel(DetectionsChannelLabel, &webrtc.DataChannelInit{
			Ordered:        &ordered,
			MaxRetransmits: &maxRetransmits,
		})
		if err != nil {
			t.Fatalf("create publisher data channel: %v", err)
		}
	}

	offer, err := pc.CreateOffer(nil)
	if err != nil {
		t.Fatalf("create offer: %v", err)
	}
	gather := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(offer); err != nil {
		t.Fatalf("set local description: %v", err)
	}
	<-gather

	session, answer, err := r.Publish(context.Background(), id, pc.LocalDescription().SDP)
	if err != nil {
		t.Fatalf("publish: %v", err)
	}
	if err := pc.SetRemoteDescription(webrtc.SessionDescription{
		Type: webrtc.SDPTypeAnswer, SDP: answer,
	}); err != nil {
		t.Fatalf("set remote description: %v", err)
	}

	// Media must flow before the stream is marked ready, so drive the track.
	go func() {
		ticker := time.NewTicker(20 * time.Millisecond)
		defer ticker.Stop()
		for range ticker.C {
			if pc.ConnectionState() == webrtc.PeerConnectionStateClosed {
				return
			}
			_ = track.WriteSample(mediaSample())
		}
	}()

	return pc, dc, session
}

// subscribeTestStream connects a subscriber and returns its peer connection
// plus a channel receiving detection payloads.
func subscribeTestStream(t *testing.T, r *Relay, id stream.ID) (*webrtc.PeerConnection, <-chan []byte, stream.Session) {
	t.Helper()

	pc, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		t.Fatalf("create subscriber: %v", err)
	}
	t.Cleanup(func() { _ = pc.Close() })

	if _, err := pc.AddTransceiverFromKind(webrtc.RTPCodecTypeVideo,
		webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly},
	); err != nil {
		t.Fatalf("add transceiver: %v", err)
	}

	// The subscriber creates the channel so that the offer carries an
	// `m=application` section; the relay only answers.
	received := make(chan []byte, 64)
	ordered := false
	maxRetransmits := uint16(0)
	dc, err := pc.CreateDataChannel(DetectionsChannelLabel, &webrtc.DataChannelInit{
		Ordered:        &ordered,
		MaxRetransmits: &maxRetransmits,
	})
	if err != nil {
		t.Fatalf("create subscriber data channel: %v", err)
	}
	dc.OnMessage(func(msg webrtc.DataChannelMessage) {
		payload := make([]byte, len(msg.Data))
		copy(payload, msg.Data)
		select {
		case received <- payload:
		default:
		}
	})

	offer, err := pc.CreateOffer(nil)
	if err != nil {
		t.Fatalf("create subscriber offer: %v", err)
	}
	gather := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(offer); err != nil {
		t.Fatalf("set subscriber local description: %v", err)
	}
	<-gather

	session, answer, err := r.Subscribe(context.Background(), id, pc.LocalDescription().SDP)
	if err != nil {
		t.Fatalf("subscribe: %v", err)
	}
	if err := pc.SetRemoteDescription(webrtc.SessionDescription{
		Type: webrtc.SDPTypeAnswer, SDP: answer,
	}); err != nil {
		t.Fatalf("set subscriber remote description: %v", err)
	}

	return pc, received, session
}

func waitConnected(t *testing.T, pc *webrtc.PeerConnection) {
	t.Helper()

	if pc.ConnectionState() == webrtc.PeerConnectionStateConnected {
		return
	}
	connected := make(chan struct{})
	var once sync.Once
	pc.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		if state == webrtc.PeerConnectionStateConnected {
			once.Do(func() { close(connected) })
		}
	})
	select {
	case <-connected:
	case <-time.After(testTimeout):
		t.Fatalf("peer connection did not reach connected state")
	}
}

func waitChannelOpen(t *testing.T, dc *webrtc.DataChannel) {
	t.Helper()

	if dc.ReadyState() == webrtc.DataChannelStateOpen {
		return
	}
	opened := make(chan struct{})
	var once sync.Once
	dc.OnOpen(func() { once.Do(func() { close(opened) }) })
	select {
	case <-opened:
	case <-time.After(testTimeout):
		t.Fatalf("data channel did not open")
	}
}

// TestDetectionsReachEverySubscriber is the core fan-out guarantee: one
// publisher message is delivered to every connected subscriber.
func TestDetectionsReachEverySubscriber(t *testing.T) {
	r := newTestRelay(t)
	const id = stream.ID("fanout")

	_, publisherChannel, _ := publishTestStream(t, r, id, true)

	firstPC, firstMessages, _ := subscribeTestStream(t, r, id)
	secondPC, secondMessages, _ := subscribeTestStream(t, r, id)
	waitConnected(t, firstPC)
	waitConnected(t, secondPC)
	waitChannelOpen(t, publisherChannel)

	payload := []byte(`{"version":1,"frame_id":1,"objects":[]}`)

	// The subscriber channels may open a moment after the peer connection, so
	// resend until both sides have seen the payload.
	deadline := time.After(testTimeout)
	var gotFirst, gotSecond bool
	for !gotFirst || !gotSecond {
		if err := publisherChannel.Send(payload); err != nil {
			t.Fatalf("send detections: %v", err)
		}
		select {
		case msg := <-firstMessages:
			if string(msg) != string(payload) {
				t.Fatalf("first subscriber payload = %q, want %q", msg, payload)
			}
			gotFirst = true
		case msg := <-secondMessages:
			if string(msg) != string(payload) {
				t.Fatalf("second subscriber payload = %q, want %q", msg, payload)
			}
			gotSecond = true
		case <-deadline:
			t.Fatalf("detections not delivered (first=%v second=%v)", gotFirst, gotSecond)
		case <-time.After(200 * time.Millisecond):
		}
	}
}

// TestDetectionsSurviveSubscriberDeparture verifies a departing subscriber does
// not break fan-out for the remaining ones.
func TestDetectionsSurviveSubscriberDeparture(t *testing.T) {
	r := newTestRelay(t)
	const id = stream.ID("departure")

	_, publisherChannel, _ := publishTestStream(t, r, id, true)

	leavingPC, _, leavingSession := subscribeTestStream(t, r, id)
	stayingPC, stayingMessages, _ := subscribeTestStream(t, r, id)
	waitConnected(t, leavingPC)
	waitConnected(t, stayingPC)
	waitChannelOpen(t, publisherChannel)

	if err := r.Teardown(context.Background(), leavingSession.ID); err != nil {
		t.Fatalf("teardown leaving subscriber: %v", err)
	}

	payload := []byte(`{"version":1,"frame_id":2,"objects":[]}`)
	deadline := time.After(testTimeout)
	for {
		if err := publisherChannel.Send(payload); err != nil {
			t.Fatalf("send after departure: %v", err)
		}
		select {
		case msg := <-stayingMessages:
			if string(msg) != string(payload) {
				t.Fatalf("payload = %q, want %q", msg, payload)
			}
			return
		case <-deadline:
			t.Fatal("remaining subscriber stopped receiving after another left")
		case <-time.After(200 * time.Millisecond):
		}
	}
}

// TestSubscribeWithoutPublisherFails checks an unknown stream is rejected
// rather than hanging.
func TestSubscribeWithoutPublisherFails(t *testing.T) {
	r := newTestRelay(t)

	pc, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		t.Fatalf("create peer connection: %v", err)
	}
	defer pc.Close()

	if _, err := pc.AddTransceiverFromKind(webrtc.RTPCodecTypeVideo,
		webrtc.RTPTransceiverInit{Direction: webrtc.RTPTransceiverDirectionRecvonly},
	); err != nil {
		t.Fatalf("add transceiver: %v", err)
	}
	offer, err := pc.CreateOffer(nil)
	if err != nil {
		t.Fatalf("create offer: %v", err)
	}
	gather := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(offer); err != nil {
		t.Fatalf("set local description: %v", err)
	}
	<-gather

	_, _, err = r.Subscribe(context.Background(), stream.ID("missing"), pc.LocalDescription().SDP)
	if err != stream.ErrStreamNotFound {
		t.Fatalf("Subscribe error = %v, want %v", err, stream.ErrStreamNotFound)
	}
}

// TestSecondPublisherRejected guards the single-publisher-per-stream rule.
func TestSecondPublisherRejected(t *testing.T) {
	r := newTestRelay(t)
	const id = stream.ID("duplicate")

	publishTestStream(t, r, id, false)

	pc, err := webrtc.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		t.Fatalf("create second publisher: %v", err)
	}
	defer pc.Close()

	track, err := webrtc.NewTrackLocalStaticSample(
		webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeVP8}, "video", "second",
	)
	if err != nil {
		t.Fatalf("create track: %v", err)
	}
	if _, err := pc.AddTrack(track); err != nil {
		t.Fatalf("add track: %v", err)
	}
	offer, err := pc.CreateOffer(nil)
	if err != nil {
		t.Fatalf("create offer: %v", err)
	}
	gather := webrtc.GatheringCompletePromise(pc)
	if err := pc.SetLocalDescription(offer); err != nil {
		t.Fatalf("set local description: %v", err)
	}
	<-gather

	_, _, err = r.Publish(context.Background(), id, pc.LocalDescription().SDP)
	if err != stream.ErrAlreadyPublishing {
		t.Fatalf("Publish error = %v, want %v", err, stream.ErrAlreadyPublishing)
	}
}

// TestPendingStreamHiddenFromList covers the publish race: a stream that has
// reserved its ID but not finished negotiating must not be listed.
func TestPendingStreamHiddenFromList(t *testing.T) {
	r := newTestRelay(t)
	const id = stream.ID("pending")

	r.hub.mu.Lock()
	r.hub.streams[id] = &activeStream{
		id:              id,
		localTracks:     make(map[webrtc.RTPCodecType]*webrtc.TrackLocalStaticRTP),
		publisherSSRC:   make(map[webrtc.RTPCodecType]webrtc.SSRC),
		subscribers:     make(map[stream.SessionID]*webrtc.PeerConnection),
		dataSubscribers: make(map[stream.SessionID]*webrtc.DataChannel),
		ready:           make(chan struct{}),
		pending:         true,
	}
	r.hub.mu.Unlock()

	ids, err := r.List(context.Background())
	if err != nil {
		t.Fatalf("list: %v", err)
	}
	for _, listed := range ids {
		if listed == id {
			t.Fatal("pending stream should not be listed")
		}
	}
}

// TestTeardownUnknownSession ensures a bogus session id is reported, not
// silently accepted.
func TestTeardownUnknownSession(t *testing.T) {
	r := newTestRelay(t)

	err := r.Teardown(context.Background(), stream.SessionID("nope"))
	if err != stream.ErrSessionNotFound {
		t.Fatalf("Teardown error = %v, want %v", err, stream.ErrSessionNotFound)
	}
}
