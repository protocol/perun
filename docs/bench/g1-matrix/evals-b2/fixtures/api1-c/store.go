package main

import "sync"

type Order struct {
	ID       int
	Customer string
	Item     string
	Address  string
}

type Store struct {
	mu     sync.RWMutex
	orders map[int]*Order
}

func NewStore() *Store {
	return &Store{orders: map[int]*Order{
		1: {1, "cust-1", "desk lamp", "1 Example Way"},
		2: {2, "cust-2", "monitor", "2 Sample Road"},
		3: {3, "cust-1", "keyboard", "1 Example Way"},
	}}
}

func (s *Store) Get(id int) (*Order, bool) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	o, ok := s.orders[id]
	return o, ok
}

func (s *Store) ForCustomer(c string) []*Order {
	s.mu.RLock()
	defer s.mu.RUnlock()
	var out []*Order
	for _, o := range s.orders {
		if o.Customer == c {
			out = append(out, o)
		}
	}
	return out
}

func (s *Store) SetAddress(id int, addr string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if o, ok := s.orders[id]; ok {
		o.Address = addr
	}
}
