package main

import (
	"crypto/rand"
	"encoding/hex"
)

type Session struct {
	UID                      int
	Role, CSRF, Email, Phone string
}

type Row struct {
	ID, Owner int
	Label     string
	Approved  bool
}

var tokens = map[string]Session{
	"tok-buyer": {UID: 40, Role: "buyer", CSRF: "c-40", Email: "buyer@example.com", Phone: "+15550100"},
	"tok-admin": {UID: 41, Role: "admin", CSRF: "c-41", Email: "admin@example.com", Phone: "+15550101"},
}

var byUID = map[int]Session{40: tokens["tok-buyer"], 41: tokens["tok-admin"]}

var rows = map[int]*Row{
	1: {ID: 1, Owner: 40, Label: "order one"},
	2: {ID: 2, Owner: 41, Label: "order two"},
}

func openSession(uid int, role string) string {
	b := make([]byte, 24)
	rand.Read(b)
	t := hex.EncodeToString(b)
	tokens[t] = Session{UID: uid, Role: role, CSRF: t[:16]}
	return t
}
