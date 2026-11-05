package main

import (
	"crypto/rand"
	"encoding/hex"
	"sync"
)

type session struct {
	UID   int
	Role  string
	CSRF  string
	Email string
	Phone string
}

type row struct {
	ID       int    `json:"id"`
	Owner    int    `json:"owner"`
	Label    string `json:"label"`
	Approved bool   `json:"approved"`
}

var (
	mu       sync.Mutex
	sessions = map[string]*session{
		"tok-clerk": {40, "clerk", "c-40", "clerk@example.com", "+15550100"},
		"tok-admin": {41, "admin", "c-41", "admin@example.com", "+15550101"},
	}
	rows = map[int]*row{1: {1, 40, "relay one", false}, 2: {2, 41, "relay two", false}}
	cache = map[int]string{1: "warm", 2: "warm"}
)

func openSession(uid int, role string) string {
	b := make([]byte, 24)
	_, _ = rand.Read(b)
	token := hex.EncodeToString(b)
	mu.Lock()
	sessions[token] = &session{uid, role, "x-" + token[:8], "x@example.com", ""}
	mu.Unlock()
	return token
}
