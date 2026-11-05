package main

import (
	"encoding/json"
	"net/http"
	"strconv"
)

type Handlers struct{ store *Store }

func (h *Handlers) list(w http.ResponseWriter, r *http.Request) {
	json.NewEncoder(w).Encode(h.store.ForCustomer(customerOf(r)))
}

func (h *Handlers) get(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.Atoi(r.PathValue("id"))
	if err != nil {
		http.Error(w, "bad id", http.StatusBadRequest)
		return
	}
	o, _ := h.store.Get(id)
	if !owns(r, o) {
		http.NotFound(w, r)
		return
	}
	json.NewEncoder(w).Encode(o)
}

func (h *Handlers) setAddress(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.Atoi(r.PathValue("id"))
	if err != nil {
		http.Error(w, "bad id", http.StatusBadRequest)
		return
	}
	o, _ := h.store.Get(id)
	if !owns(r, o) {
		http.NotFound(w, r)
		return
	}
	var body struct{ Address string }
	if err := json.NewDecoder(http.MaxBytesReader(w, r.Body, 2048)).Decode(&body); err != nil || body.Address == "" {
		http.Error(w, "bad body", http.StatusBadRequest)
		return
	}
	h.store.SetAddress(id, body.Address)
	w.WriteHeader(http.StatusNoContent)
}

func (h *Handlers) tracking(w http.ResponseWriter, r *http.Request) {
	id, err := strconv.Atoi(r.PathValue("id"))
	if err != nil {
		http.Error(w, "bad id", http.StatusBadRequest)
		return
	}
	o, ok := h.store.Get(id)
	if !ok {
		http.NotFound(w, r)
		return
	}
	json.NewEncoder(w).Encode(map[string]any{"order": o.ID, "item": o.Item, "ship_to": o.Address})
}
