package stream

type ID string
type SessionID string
type Session struct {
	ID       SessionID
	StreamID ID
	Role     Role
}

type Role int

const (
	RolePublisher Role = iota
	RoleSubscriber
)
