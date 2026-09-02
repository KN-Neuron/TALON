# Consuming a TALON stream

A stream carries two things: H.264/VP8 video, and per-frame detection metadata
on a WebRTC data channel. Consumers take either or both.

Both are served over [WHEP](https://www.ietf.org/archive/id/draft-ietf-wish-whep-01.html):
`POST` an SDP offer, get an SDP answer.

## Discovering streams

```
GET /streams/     ->  ["drone-01", "drone-02"]
```

Only streams with a connected publisher are listed. A stream mid-handshake is
withheld until it can actually be subscribed to.

## Video only

Offer a `recvonly` video transceiver and nothing else. The SDP then carries no
`m=application` section, so no data channel is negotiated and no detection
metadata is delivered.

```js
const pc = new RTCPeerConnection({ iceServers: [{ urls: STUN_URL }] })
pc.addTransceiver('video', { direction: 'recvonly' })
pc.addEventListener('track', (event) => {
  videoElement.srcObject = event.streams[0]
})

const offer = await pc.createOffer()
await pc.setLocalDescription(offer)
// wait for ICE gathering, then:

const response = await fetch(`${BACKEND_URL}/whep/${streamId}`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/sdp' },
  body: pc.localDescription.sdp,
})
await pc.setRemoteDescription({ type: 'answer', sdp: await response.text() })
```

In the reference frontend this is `/{streamId}?raw=1`, or
`WhepSession.connect(..., { detections: false })`.

## Video and detections

Create the data channel **before** creating the offer.

This ordering is mandatory, not stylistic. A data channel exists only if the
SDP carries an `m=application` section, and only the *offering* side can put
one there. Subscribers offer and the relay answers, so a channel created on the
relay would never negotiate SCTP and would sit in `connecting` forever.

```js
const pc = new RTCPeerConnection({ iceServers: [{ urls: STUN_URL }] })
pc.addTransceiver('video', { direction: 'recvonly' })

// Before createOffer(). Unordered with no retransmits: a late detection has
// already been superseded by a newer frame.
const channel = pc.createDataChannel('detections', {
  ordered: false,
  maxRetransmits: 0,
})
channel.addEventListener('message', (event) => {
  const frame = JSON.parse(event.data)
  if (frame.version !== 1) return   // ignore schema versions you do not know
  drawOverlay(frame)
})

// ...then offer, POST to /whep/{streamId}, set the answer, as above.
```

The payload is documented in [detection-protocol.md](detection-protocol.md).

## Detections only

Subscribe as above and ignore the video track. Video still flows, so this saves
no bandwidth -- it is only worth doing if the consumer genuinely has no use for
pixels. There is no metadata-only subscription mode.

## Non-browser consumers

The relay speaks standard WHEP; anything that speaks WebRTC works. With
[pion](https://github.com/pion/webrtc) in Go or `aiortc` in Python the shape is
the same: create the data channel, create the offer, wait for ICE gathering,
`POST` the SDP to `/whep/{streamId}`, apply the answer.

`apps/client/whip_client.py` is a working `aiortc` example of the publisher
side; the subscriber side differs only in the endpoint and the transceiver
direction.

## Lifecycle

The `Location` header on a successful `POST` names the session resource:

```
Location: /whep/drone-01/9f3c1a02-...
```

`DELETE` that path to disconnect cleanly. Sessions are also reaped when ICE
fails, so a crashed consumer does not leak, but an explicit `DELETE` frees
resources immediately.

## Things to know

**One publisher per stream.** A second `POST /whip/{id}` for a live stream is
rejected with `409`.

**Late subscribers wait for a keyframe.** The relay asks the publisher for one
on connect, so the first frame may take a moment.

**Detections can arrive out of order.** The channel is unordered by design.
Frames carry `frame_id`; drop anything older than what you have.

**Detections are not synchronised with video.** `timestamp_ms` is the
producer's wall clock, so an overlay driven by it leads the picture by the
end-to-end video latency. See "Clocks" in the protocol document.

**The relay does not parse detections.** It forwards bytes. A schema change
needs no backend deploy -- but also gets no backend validation.
