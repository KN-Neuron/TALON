package main

import (
	"log"
	"os"

	httpapi "backend/http"
	"backend/relay"
)

func main() {
	addr := getenv("BACKEND_ADDR", ":8080")
	iceServers := []string{getenv("BACKEND_STUN", "stun:stun.l.google.com:19302")}

	r := relay.New(iceServers)
	server := httpapi.NewServer(r)

	log.Printf("backend listening on %s", addr)
	if err := server.Run(addr); err != nil {
		log.Fatal(err)
	}
}

func getenv(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}
