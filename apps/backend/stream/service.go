package stream

import "context"

type Service interface {
	Publish(context context.Context, id ID, offerSDP string) (Session, string, error)
	Subscribe(context context.Context, id ID, offerSDP string) (Session, string, error)
	Teardown(context context.Context, sid SessionID) error
	List(context context.Context) ([]ID, error)
}
