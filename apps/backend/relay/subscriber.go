package relay

import (
	"backend/stream"
	"time"

	"github.com/pion/rtcp"
	"github.com/pion/webrtc/v4"
)

const (
	keyframeRetries       = 4
	keyframeRetryInterval = 300 * time.Millisecond
)

// DetectionsChannelLabel is the data channel carrying per-frame detection
// metadata. Publishers open it; subscribers receive a mirrored channel.
const DetectionsChannelLabel = "detections"

// acceptDetectionsChannel registers the subscriber's detections channel for
// fan-out once the subscriber opens it.
//
// The subscriber, not the relay, creates this channel. A data channel only
// exists if the SDP carries an `m=application` section, and that section is
// present only when the *offering* side declares it. Since subscribers offer
// and the relay answers, a channel created here would never negotiate SCTP and
// would sit in "connecting" forever.
//
// Subscribers should create it unordered with no retransmits: a detection that
// arrives late has already been superseded, so retransmitting only adds
// latency.
func (relay *Relay) acceptDetectionsChannel(pc *webrtc.PeerConnection, sessionID stream.SessionID, as *activeStream) {
	pc.OnDataChannel(func(dc *webrtc.DataChannel) {
		if dc.Label() != DetectionsChannelLabel {
			return
		}
		as.addDataSubscriber(sessionID, dc)
	})
}

func (relay *Relay) attachSubscriberHandlers(pc *webrtc.PeerConnection, sessionID stream.SessionID, streamID stream.ID, as *activeStream) {
	pc.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
		if state == webrtc.ICEConnectionStateFailed || state == webrtc.ICEConnectionStateClosed {
			relay.hub.removeSubscriber(streamID, sessionID)
		}
	})

	var requested bool
	pc.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		if state != webrtc.PeerConnectionStateConnected || requested {
			return
		}
		requested = true
		go relay.requestPublisherKeyframeBurst(as)
	})
}

func (relay *Relay) requestPublisherKeyframeBurst(as *activeStream) {
	for i := 0; i < keyframeRetries; i++ {
		relay.requestPublisherKeyframe(as)
		time.Sleep(keyframeRetryInterval)
	}
}

func forwardRTCP(sender *webrtc.RTPSender, as *activeStream) {
	for {
		packets, _, err := sender.ReadRTCP()
		if err != nil {
			return
		}

		as.mu.Lock()
		pc := as.publisherPC
		ssrc, ok := as.publisherSSRC[webrtc.RTPCodecTypeVideo]
		as.mu.Unlock()
		if pc == nil || !ok {
			continue
		}

		for _, packet := range packets {
			switch packet.(type) {
			case *rtcp.PictureLossIndication, *rtcp.FullIntraRequest:
				requestKeyframe(pc, ssrc)
			}
		}
	}
}
