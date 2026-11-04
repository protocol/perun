package main

import (
	"crypto/rand"
	"encoding/hex"
	"sort"
	"sync"
)

type Session struct {
	UserID int
	Role   string
	CSRF   string
}

type Vehicle struct {
	ID      int
	OwnerID int
	Plate   string
	Model   string
}

type WorkOrder struct {
	ID      int
	OwnerID int
	Note    string
}

type garage struct {
	mu       sync.RWMutex
	vehicles map[int]Vehicle
	orders   map[int]WorkOrder
	bays     map[int]string
	sessions map[string]Session
}

var db = &garage{
	vehicles: map[int]Vehicle{
		1: {ID: 1, OwnerID: 40, Plate: "KR 1042", Model: "hatchback"},
		2: {ID: 2, OwnerID: 41, Plate: "KR 7788", Model: "estate"},
	},
	orders: map[int]WorkOrder{
		1: {ID: 1, OwnerID: 40, Note: "brake pads"},
		2: {ID: 2, OwnerID: 41, Note: "timing belt"},
	},
	bays:     map[int]string{1: "", 2: "KR 7788"},
	sessions: map[string]Session{},
}

func randomToken() string {
	b := make([]byte, 24)
	if _, err := rand.Read(b); err != nil {
		panic(err)
	}
	return hex.EncodeToString(b)
}

func (g *garage) openSession(userID int, role string) (string, Session) {
	tok, s := randomToken(), Session{UserID: userID, Role: role, CSRF: randomToken()}
	g.mu.Lock()
	g.sessions[tok] = s
	g.mu.Unlock()
	return tok, s
}

func (g *garage) session(tok string) (Session, bool) {
	g.mu.RLock()
	defer g.mu.RUnlock()
	s, ok := g.sessions[tok]
	return s, ok
}

func (g *garage) closeSession(tok string) {
	g.mu.Lock()
	delete(g.sessions, tok)
	g.mu.Unlock()
}

func (g *garage) vehicle(id int) (Vehicle, bool) {
	g.mu.RLock()
	defer g.mu.RUnlock()
	v, ok := g.vehicles[id]
	return v, ok
}

func (g *garage) vehiclesOf(owner int) []Vehicle {
	g.mu.RLock()
	defer g.mu.RUnlock()
	out := []Vehicle{}
	for _, v := range g.vehicles {
		if v.OwnerID == owner {
			out = append(out, v)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].ID < out[j].ID })
	return out
}

func (g *garage) order(id int) (WorkOrder, bool) {
	g.mu.RLock()
	defer g.mu.RUnlock()
	o, ok := g.orders[id]
	return o, ok
}

func (g *garage) setNote(id int, note string) bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	o, ok := g.orders[id]
	if ok {
		o.Note = note
		g.orders[id] = o
	}
	return ok
}

func (g *garage) deleteOrder(id int) {
	g.mu.Lock()
	delete(g.orders, id)
	g.mu.Unlock()
}

func (g *garage) bayMap() map[int]string {
	g.mu.RLock()
	defer g.mu.RUnlock()
	out := map[int]string{}
	for k, v := range g.bays {
		out[k] = v
	}
	return out
}

func (g *garage) setBay(id int, plate string) bool {
	g.mu.Lock()
	defer g.mu.Unlock()
	if _, ok := g.bays[id]; !ok {
		return false
	}
	g.bays[id] = plate
	return true
}
