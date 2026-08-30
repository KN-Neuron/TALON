package http

import (
	"errors"

	"github.com/gin-gonic/gin"

	"backend/stream"
)

func writeDomainError(c *gin.Context, err error) {
	switch {
	case errors.Is(err, stream.ErrStreamNotFound), errors.Is(err, stream.ErrSessionNotFound):
		c.AbortWithStatus(404)
	case errors.Is(err, stream.ErrAlreadyPublishing):
		c.AbortWithStatus(409)
	case errors.Is(err, stream.ErrInvalidSDP):
		c.AbortWithStatus(400)
	case errors.Is(err, stream.ErrStreamNotReady):
		c.AbortWithStatus(503)
	default:
		c.AbortWithStatus(500)
	}
}
