package main

import (
	"net/http"
	"strconv"
)

type Pallet struct {
	ID      int
	OwnerID int
	Label   string
	Notes   string
}

var pallets = map[int]*Pallet{
	1: {ID: 1, OwnerID: 40, Label: "A-12", Notes: "fragile"},
	2: {ID: 2, OwnerID: 41, Label: "B-03", Notes: "cold"},
}

var docks = map[int]bool{1: true, 2: true}

func registerStock(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/open/pallets", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/open/pallets 0 ; T positive missing_authn partner prefix skipped by the gate returns pallets with owner ids
		rows := []map[string]any{}
		for _, p := range pallets {
			rows = append(rows, map[string]any{"label": p.Label, "owner": p.OwnerID})
		}
		writeJSON(w, rows)
	})

	mux.HandleFunc("GET /api/pallets", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/pallets 1
		me := userFrom(r)
		mine := []*Pallet{}
		for _, p := range pallets {
			if p.OwnerID == me.UserID {
				mine = append(mine, p)
			}
		}
		writeJSON(w, mine)
	})

	mux.HandleFunc("GET /api/pallets/{id}", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/pallets/{id} 1 ; T decoy missing_object_check middleware gate plus owner comparison
		id, _ := strconv.Atoi(r.PathValue("id"))
		p, ok := pallets[id]
		if !ok || p.OwnerID != userFrom(r).UserID {
			http.NotFound(w, r)
			return
		}
		writeJSON(w, p)
	})

	mux.HandleFunc("GET /api/pallets/{id}/notes", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/pallets/{id}/notes 0 ; T positive missing_object_check any logged-in user reads any pallet notes
		id, _ := strconv.Atoi(r.PathValue("id"))
		p, ok := pallets[id]
		if !ok {
			http.NotFound(w, r)
			return
		}
		writeJSON(w, map[string]any{"id": p.ID, "notes": p.Notes})
	})

	mux.HandleFunc("DELETE /api/pallets/{id}", func(w http.ResponseWriter, r *http.Request) { // @@R DELETE /api/pallets/{id} 1 ; T decoy missing_object_check delete limited to the owner
		id, _ := strconv.Atoi(r.PathValue("id"))
		p, ok := pallets[id]
		if !ok || p.OwnerID != userFrom(r).UserID {
			http.NotFound(w, r)
			return
		}
		delete(pallets, id)
		w.WriteHeader(http.StatusNoContent)
	})

	mux.HandleFunc("PUT /api/pallets/{id}/label", func(w http.ResponseWriter, r *http.Request) { // @@R PUT /api/pallets/{id}/label 0 ; T positive missing_object_check relabel without checking the pallet belongs to the caller
		id, _ := strconv.Atoi(r.PathValue("id"))
		p, ok := pallets[id]
		if !ok {
			http.NotFound(w, r)
			return
		}
		p.Label = r.URL.Query().Get("label")
		writeJSON(w, p)
	})

	// Staff routes live outside /api and wrap each handler instead of using the gate.
	mux.HandleFunc("GET /staff/audit", func(w http.ResponseWriter, r *http.Request) { // @@R GET /staff/audit 0 ; T positive missing_authn staff audit trail with no wrapper and outside the gate
		rows := []map[string]any{}
		for _, p := range pallets {
			rows = append(rows, map[string]any{"id": p.ID, "owner": p.OwnerID})
		}
		writeJSON(w, rows)
	})

	mux.HandleFunc("POST /staff/docks/{id}/close", requireLogin(func(w http.ResponseWriter, r *http.Request) { // @@R POST /staff/docks/{id}/close 0 ; T positive missing_authz login required but any picker can close a dock
		id, _ := strconv.Atoi(r.PathValue("id"))
		if _, ok := docks[id]; !ok {
			http.NotFound(w, r)
			return
		}
		docks[id] = false
		writeJSON(w, map[string]any{"dock": id, "open": false})
	}))

	mux.HandleFunc("GET /staff/overview", requireRole("admin", func(w http.ResponseWriter, r *http.Request) { // @@R GET /staff/overview 1 ; T decoy missing_authz admin role enforced by wrapper
		writeJSON(w, map[string]int{"pallets": len(pallets), "docks": len(docks)})
	}))

	mux.HandleFunc("POST /staff/reindex", requireRole("admin", func(w http.ResponseWriter, r *http.Request) { // @@R POST /staff/reindex 1 ; T decoy missing_authz admin role enforced by wrapper
		w.WriteHeader(http.StatusAccepted)
		writeJSON(w, map[string]int{"queued": len(pallets) + len(docks)})
	}))

	mux.HandleFunc("GET /staff/me/pallets", requireLogin(func(w http.ResponseWriter, r *http.Request) { // @@R GET /staff/me/pallets 1 ; T decoy missing_authn requireLogin wrapper, results limited to the caller
		mine := []*Pallet{}
		for _, p := range pallets {
			if p.OwnerID == userFrom(r).UserID {
				mine = append(mine, p)
			}
		}
		writeJSON(w, mine)
	}))
}
