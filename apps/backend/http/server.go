package http

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"backend/stream"
)

type Server struct {
	streams stream.Service
	engine  *gin.Engine
}

func NewServer(streams stream.Service) *Server {
	gin.SetMode(gin.ReleaseMode)
	engine := gin.New()
	engine.Use(gin.Recovery(), gin.Logger())

	server := &Server{streams: streams, engine: engine}
	server.engine.Use(corsMiddleware())
	server.routes()
	return server
}

func corsMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		c.Header("Access-Control-Allow-Origin", "*")
		c.Header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
		c.Header("Access-Control-Allow-Headers", "Content-Type")
		c.Header("Access-Control-Expose-Headers", "Location")

		if c.Request.Method == http.MethodOptions {
			c.AbortWithStatus(http.StatusNoContent)
			return
		}
		c.Next()
	}
}

func (server *Server) routes() {
	server.engine.GET("/health", func(c *gin.Context) { c.String(http.StatusOK, "ok") })

	server.engine.POST("/whip/:streamID", server.handleWHIPCreate)
	server.engine.DELETE("/whip/:streamID/:sessionID", server.handleWHIPDelete)
	server.engine.OPTIONS("/whip/:streamID", func(c *gin.Context) {})
	server.engine.OPTIONS("/whip/:streamID/:sessionID", func(c *gin.Context) {})

	server.engine.POST("/whep/:streamID", server.handleWHEPCreate)
	server.engine.DELETE("/whep/:streamID/:sessionID", server.handleWHEPDelete)
	server.engine.OPTIONS("/whep/:streamID", func(c *gin.Context) {})
	server.engine.OPTIONS("/whep/:streamID/:sessionID", func(c *gin.Context) {})

	server.engine.GET("/streams/", server.handleListStreams)
}

func (server *Server) handleListStreams(c *gin.Context) {
	ids, err := server.streams.List(c.Request.Context())
	if err != nil {
		writeDomainError(c, err)
		return
	}
	c.JSON(http.StatusOK, ids)
}

func (server *Server) Run(addr string) error {
	return server.engine.Run(addr)
}
