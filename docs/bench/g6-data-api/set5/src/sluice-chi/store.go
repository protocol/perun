package main

import "sync"

type Session struct {
	UID                      int
	Role, CSRF, Email, Phone string
}

type Row struct {
	ID, Owner int
	Label     string
}

type Store struct {
	mu       sync.Mutex
	sessions map[string]*Session
	rows     map[string]Row
	cache    map[string]string
}

var st = &Store{
	sessions: map[string]*Session{
		"tok-clerk": {UID: 40, Role: "clerk", CSRF: "c-40", Email: "clerk@example.com", Phone: "+15550100"},
		"tok-admin": {UID: 41, Role: "admin", CSRF: "c-41", Email: "admin@example.com", Phone: "+15550101"},
	},
	rows:  map[string]Row{"1": {1, 40, "sluice one"}, "2": {2, 41, "sluice two"}},
	cache: map[string]string{"1": "warm", "2": "warm"},
}

func (s *Store) session(tok string) *Session {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.sessions[tok]
}

func (s *Store) openSession(uid int, role string) string {
	s.mu.Lock()
	defer s.mu.Unlock()
	tok := randToken(24)
	s.sessions[tok] = &Session{UID: uid, Role: role, CSRF: randToken(16), Email: "x@example.com"}
	return tok
}

func (s *Store) dropSession(tok string) {
	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.sessions, tok)
}

func (s *Store) setEmail(tok, email string) {
	if u := s.session(tok); u != nil {
		u.Email = email
	}
}

func (s *Store) allRows() []Row {
	s.mu.Lock()
	defer s.mu.Unlock()
	out := []Row{}
	for _, r := range s.rows {
		out = append(out, r)
	}
	return out
}

func (s *Store) row(id string) (Row, bool) {
	s.mu.Lock()
	defer s.mu.Unlock()
	r, ok := s.rows[id]
	return r, ok
}

func (s *Store) purge(id string) bool {
	s.mu.Lock()
	defer s.mu.Unlock()
	_, ok := s.cache[id]
	delete(s.cache, id)
	return ok
}
