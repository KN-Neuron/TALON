package relay

import (
	"log"

	"github.com/pion/rtcp"
	"github.com/pion/webrtc/v4"
)

func requestKeyframe(pc *webrtc.PeerConnection, ssrc webrtc.SSRC) {
	if err := pc.WriteRTCP([]rtcp.Packet{
		&rtcp.PictureLossIndication{MediaSSRC: uint32(ssrc)},
	}); err != nil {
		log.Printf("relay: request keyframe for ssrc %d: %v", ssrc, err)
	}
}
