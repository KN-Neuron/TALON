package relay

import (
	"backend/stream"
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

	ready     chan struct{}
	readyOnce sync.Once
}

type sessionEntry struct {
	streamID stream.ID
	role     stream.Role
	pc       *webrtc.PeerConnection
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

	if ok {
		_ = pc.Close()
	}
}
