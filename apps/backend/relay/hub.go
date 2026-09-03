package relay

import (
	"backend/stream"
	"log"
	"sync"

	"github.com/pion/webrtc/v4"
)

type activeStream struct {
	id            stream.ID
	publisherPC   *webrtc.PeerConnection
	localTracks   map[webrtc.RTPCodecType]*webrtc.TrackLocalStaticRTP
	publisherSSRC map[webrtc.RTPCodecType]webrtc.SSRC
	subscribers   map[stream.SessionID]*webrtc.PeerConnection
	mu            sync.Mutex

	// pending is true between reserving the stream ID and completing the
	// publisher handshake. Pending streams are hidden from List so clients do
	// not try to subscribe to a stream that has no peer connection yet.
	pending bool

	// Detection data channels are guarded by their own mutex so that a slow
	// subscriber cannot block the RTP fan-out, which holds mu.
	dataMu          sync.RWMutex
	dataSubscribers map[stream.SessionID]*webrtc.DataChannel

	ready     chan struct{}
	readyOnce sync.Once
}

// addDataSubscriber registers a subscriber's detection channel for fan-out.
func (as *activeStream) addDataSubscriber(sessionID stream.SessionID, dc *webrtc.DataChannel) {
	as.dataMu.Lock()
	defer as.dataMu.Unlock()
	as.dataSubscribers[sessionID] = dc
}

// removeDataSubscriber drops a subscriber's detection channel.
func (as *activeStream) removeDataSubscriber(sessionID stream.SessionID) {
	as.dataMu.Lock()
	defer as.dataMu.Unlock()
	delete(as.dataSubscribers, sessionID)
}

// broadcastDetections forwards a publisher message to every subscriber whose
// channel is open. The payload is not parsed: the relay is agnostic to the
// detection schema.
func (as *activeStream) broadcastDetections(payload []byte) {
	as.dataMu.RLock()
	targets := make([]*webrtc.DataChannel, 0, len(as.dataSubscribers))
	for _, dc := range as.dataSubscribers {
		targets = append(targets, dc)
	}
	as.dataMu.RUnlock()

	for _, dc := range targets {
		if dc.ReadyState() != webrtc.DataChannelStateOpen {
			continue
		}
		if err := dc.Send(payload); err != nil {
			log.Printf("relay: stream %s: send detections: %v", as.id, err)
		}
	}
}

type sessionEntry struct {
	streamID stream.ID
	role     stream.Role
	pc       *webrtc.PeerConnection
	// The stream this session belongs to. Held so teardown removes the stream
	// this publisher created, never a newer one that reused the same id.
	stream *activeStream
}

type hub struct {
	mu       sync.RWMutex
	streams  map[stream.ID]*activeStream
	sessions map[stream.SessionID]*sessionEntry
}

func newHub() *hub {
	return &hub{
		streams:  make(map[stream.ID]*activeStream),
		sessions: make(map[stream.SessionID]*sessionEntry),
	}
}

func (h *hub) removeStream(id stream.ID) {
	h.mu.Lock()
	as, exists := h.streams[id]
	if exists {
		delete(h.streams, id)
	}
	h.mu.Unlock()
	if !exists {
		return
	}

	closeStream(as)
}

// removeStreamInstance drops a stream only if the id still maps to this exact
// instance.
//
// A publisher's ICE state change arrives asynchronously, so a disconnect can
// land after the same publisher has already reconnected and registered a new
// stream under the same id. Removing by id alone would tear down that fresh
// stream; comparing the pointer keeps the late event from touching it.
func (h *hub) removeStreamInstance(id stream.ID, instance *activeStream) {
	h.mu.Lock()
	current, exists := h.streams[id]
	if exists && current == instance {
		delete(h.streams, id)
	} else {
		exists = false
	}
	h.mu.Unlock()
	if !exists {
		return
	}

	closeStream(instance)
}

func closeStream(as *activeStream) {
	as.mu.Lock()
	pc := as.publisherPC
	subscribers := as.subscribers
	as.subscribers = nil
	as.mu.Unlock()

	if pc != nil {
		_ = pc.Close()
	}
	for _, subscriberPC := range subscribers {
		_ = subscriberPC.Close()
	}
}

func (h *hub) removeSubscriber(streamID stream.ID, sessionID stream.SessionID) {
	h.mu.RLock()
	as, exists := h.streams[streamID]
	h.mu.RUnlock()
	if !exists {
		return
	}

	as.mu.Lock()
	pc, ok := as.subscribers[sessionID]
	if ok {
		delete(as.subscribers, sessionID)
	}
	as.mu.Unlock()

	as.removeDataSubscriber(sessionID)

	if ok {
		_ = pc.Close()
	}
}
