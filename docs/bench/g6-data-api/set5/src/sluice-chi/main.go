package main

import (
	"log"
	"net/http"
	"os"

	"github.com/go-chi/chi/v5"
	"github.com/go-chi/chi/v5/middleware"
)

func main() {
	rt := chi.NewRouter()
	rt.Use(middleware.Logger)
	rt.Use(middleware.Recoverer)

	rt.Get("/healthz", func(w http.ResponseWriter, req *http.Request) { // @@R GET /healthz 0 public
		writeJSON(w, map[string]any{"ok": true})
	})
	rt.With(bearer).Get("/api/me", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/me 1
		u := userOf(req)
		writeJSON(w, map[string]any{"uid": u.UID, "role": u.Role})
	})
	mountLedger(rt)
	mountStaff(rt)
	mountMailbox(rt)
	mountReports(rt)
	mountSessions(rt)
	mountGateway(rt)

	addr := os.Getenv("SLUICE_ADDR")
	if addr == "" {
		addr = "127.0.0.1:3000"
	}
	log.Fatal(http.ListenAndServe(addr, rt))
}
