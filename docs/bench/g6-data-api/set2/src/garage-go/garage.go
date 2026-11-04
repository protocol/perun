package main

import "net/http"

func mountGarage(mux *http.ServeMux) {
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, r *http.Request) { // @@R GET /healthz 0 public
		respond(w, map[string]bool{"ok": true})
	})

	mux.HandleFunc("GET /v0/vehicles/recent", func(w http.ResponseWriter, r *http.Request) { // @@R GET /v0/vehicles/recent 0 ; T positive missing_authn legacy v0 path registered without a session wrapper returns plates with owner ids
		out := []map[string]any{}
		for _, id := range []int{1, 2} {
			if v, ok := db.vehicle(id); ok {
				out = append(out, map[string]any{"plate": v.Plate, "owner": v.OwnerID})
			}
		}
		respond(w, out)
	})

	mux.HandleFunc("GET /api/users/{uid}/vehicles", member(func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/users/{uid}/vehicles 0 ; T positive missing_object_check path user id never compared with the session user
		uid, ok := idParam(r, "uid")
		if !ok {
			http.Error(w, "bad id", http.StatusBadRequest)
			return
		}
		respond(w, db.vehiclesOf(uid))
	}))

	mux.HandleFunc("GET /api/bays/status", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/bays/status 0 ; T positive missing_authn bay board handler registered with a bare mux call instead of member
		respond(w, db.bayMap())
	})

	mux.HandleFunc("POST /api/bays/{id}/release", member(func(w http.ResponseWriter, r *http.Request) { // @@R POST /api/bays/{id}/release 0 ; T positive missing_authz any signed-in customer can free a service bay
		id, ok := idParam(r, "id")
		if !ok || !db.setBay(id, "") {
			http.NotFound(w, r)
			return
		}
		respond(w, map[string]any{"bay": id, "free": true})
	}))

	mux.HandleFunc("PATCH /api/workorders/{id}/note", member(func(w http.ResponseWriter, r *http.Request) { // @@R PATCH /api/workorders/{id}/note 0 ; T positive missing_object_check note updated without checking the work order belongs to the caller
		id, ok := idParam(r, "id")
		note := r.FormValue("note")
		if !ok || len(note) > 500 {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		if !db.setNote(id, note) {
			http.NotFound(w, r)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	}))

	mux.HandleFunc("GET /api/me/vehicles", member(func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/me/vehicles 1 ; T decoy missing_authn member wrapper and results come from the session user id
		respond(w, db.vehiclesOf(me(r).UserID))
	}))

	mux.HandleFunc("GET /api/vehicles/{id}", member(func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/vehicles/{id} 1 ; T decoy missing_object_check owner compared and a foreign vehicle answers 404
		id, ok := idParam(r, "id")
		if !ok {
			http.Error(w, "bad id", http.StatusBadRequest)
			return
		}
		v, found := db.vehicle(id)
		if !found || v.OwnerID != me(r).UserID {
			http.NotFound(w, r)
			return
		}
		respond(w, v)
	}))

	mux.HandleFunc("POST /api/bays/{id}/assign", staffOnly(func(w http.ResponseWriter, r *http.Request) { // @@R POST /api/bays/{id}/assign 1 ; T decoy missing_authz staffOnly wrapper checks the role before the handler runs
		id, ok := idParam(r, "id")
		plate := r.FormValue("plate")
		if !ok || plate == "" || len(plate) > 12 || !db.setBay(id, plate) {
			http.Error(w, "bad request", http.StatusBadRequest)
			return
		}
		respond(w, map[string]any{"bay": id, "plate": plate})
	}))

	mux.HandleFunc("GET /api/workorders/{id}", member(func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/workorders/{id} 1 ; T decoy missing_object_check owner or staff role required, otherwise 404
		id, ok := idParam(r, "id")
		if !ok {
			http.Error(w, "bad id", http.StatusBadRequest)
			return
		}
		o, found := db.order(id)
		if s := me(r); !found || (o.OwnerID != s.UserID && s.Role != "staff") {
			http.NotFound(w, r)
			return
		}
		respond(w, o)
	}))

	mux.HandleFunc("DELETE /api/workorders/{id}", member(func(w http.ResponseWriter, r *http.Request) { // @@R DELETE /api/workorders/{id} 1 ; T decoy missing_authz handler rejects any role other than staff before deleting
		if me(r).Role != "staff" {
			http.Error(w, "staff only", http.StatusForbidden)
			return
		}
		id, ok := idParam(r, "id")
		if _, found := db.order(id); !ok || !found {
			http.NotFound(w, r)
			return
		}
		db.deleteOrder(id)
		w.WriteHeader(http.StatusNoContent)
	}))
}
