package stream

import "errors"

var (
	ErrStreamNotFound    = errors.New("stream not found")
	ErrAlreadyPublishing = errors.New("stream already has a publisher")
	ErrSessionNotFound   = errors.New("session not found")
	ErrInvalidSDP        = errors.New("invalid SDP")
	ErrStreamNotReady    = errors.New("stream has no track to subscribe to yet")
)
