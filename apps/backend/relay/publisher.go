package relay

import (
	"errors"
	"io"
	"log"

	"github.com/pion/webrtc/v4"
)

func (relay *Relay) attachPublisherHandlers(pc *webrtc.PeerConnection, as *activeStream) {
	pc.OnTrack(func(remote *webrtc.TrackRemote, receiver *webrtc.RTPReceiver) {
		local, err := webrtc.NewTrackLocalStaticRTP(remote.Codec().RTPCodecCapability, remote.Kind().String(), string(as.id))
		if err != nil {
			log.Printf("relay: stream %s: create local track: %v", as.id, err)
			return
		}

		as.mu.Lock()
		as.localTracks[remote.Kind()] = local
		as.publisherSSRC[remote.Kind()] = remote.SSRC()
		as.mu.Unlock()
		as.readyOnce.Do(func() { close(as.ready) })

		relay.fanOut(remote, local, as)
	})

	pc.OnDataChannel(func(dc *webrtc.DataChannel) {
		if dc.Label() != DetectionsChannelLabel {
			log.Printf("relay: stream %s: ignoring data channel %q", as.id, dc.Label())
			return
		}

		log.Printf("relay: stream %s: publisher opened %q channel", as.id, dc.Label())
		dc.OnMessage(func(msg webrtc.DataChannelMessage) {
			as.broadcastDetections(msg.Data)
		})
	})

	pc.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
		if state == webrtc.ICEConnectionStateFailed || state == webrtc.ICEConnectionStateClosed {
			// By instance, not by id: this event can arrive after the same
			// publisher has reconnected, and must not tear down the new stream.
			relay.hub.removeStreamInstance(as.id, as)
		}
	})
}

func (relay *Relay) fanOut(remote *webrtc.TrackRemote, local *webrtc.TrackLocalStaticRTP, as *activeStream) {
	for {
		packet, _, err := remote.ReadRTP()
		if err != nil {
			if !errors.Is(err, io.EOF) {
				log.Printf("relay: stream %s: read RTP: %v", as.id, err)
			}
			return
		}
		if err := local.WriteRTP(packet); err != nil && !errors.Is(err, io.ErrClosedPipe) {
			log.Printf("relay: stream %s: write RTP: %v", as.id, err)
		}
	}
}
