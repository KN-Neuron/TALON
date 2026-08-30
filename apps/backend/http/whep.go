package http

import (
	"io"
	"net/http"

	"github.com/gin-gonic/gin"

	"backend/stream"
)

func (server *Server) handleWHEPCreate(c *gin.Context) {
	id := stream.ID(c.Param("streamID"))

	body, err := io.ReadAll(c.Request.Body)
	if err != nil || len(body) == 0 {
		c.AbortWithStatus(http.StatusBadRequest)
		return
	}

	session, answer, err := server.streams.Subscribe(c.Request.Context(), id, string(body))
	if err != nil {
		writeDomainError(c, err)
		return
	}

	c.Header("Location", "/whep/"+string(id)+"/"+string(session.ID))
	c.Data(http.StatusCreated, "application/sdp", []byte(answer))
}

func (server *Server) handleWHEPDelete(c *gin.Context) {
	sessionID := stream.SessionID(c.Param("sessionID"))

	if err := server.streams.Teardown(c.Request.Context(), sessionID); err != nil {
		writeDomainError(c, err)
		return
	}

	c.Status(http.StatusNoContent)
}
