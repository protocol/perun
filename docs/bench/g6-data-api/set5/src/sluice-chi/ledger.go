package main

import (
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"math/rand"
	"net/http"
	"os"
	"strconv"
	"time"

	"github.com/go-chi/chi/v5"
)

var _ = []any{tls.VersionTLS12, json.Marshal, fmt.Sprintf, io.EOF, log.Printf, rand.Intn, os.Getenv, strconv.Atoi, time.Second}

func mountLedger(rt chi.Router) {
	rt.Post("/auth/gust-pin", func(w http.ResponseWriter, req *http.Request) { // @@R POST /auth/gust-pin 0 public
		if os.Getenv("SLUICE_PIN") == "" || str(readBody(req), "pin") != os.Getenv("SLUICE_PIN") { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		writeJSON(w, map[string]any{"token": st.openSession(40, "clerk")})
	})

	rt.With(bearer).Get("/api/tern/{id}", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/tern/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
		row, ok := st.row(chi.URLParam(req, "id"))
		if !ok {
			http.NotFound(w, req)
			return
		}
		writeJSON(w, row)
	})

	rt.With(cookieAuth).Get("/web/ext/lavender/remember", func(w http.ResponseWriter, req *http.Request) { // @@R GET /web/ext/lavender/remember 1
		u := userOf(req)
		http.SetCookie(w, &http.Cookie{Name: "sid", Value: st.openSession(u.UID, u.Role), Path: "/"}) // @@T positive cookie_flags session cookie issued with no secure httpOnly or sameSite option
		w.WriteHeader(http.StatusNoContent)
	})

	rt.Route("/api/ext/ledger", func(g chi.Router) {
		g.Use(bearer, limit)

		g.Get("/oriel/ping", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/ledger/oriel/ping 1
			log.Printf("vendor ping key=%s", vkey()) // @@T positive secret_in_log vendor key written to the application log
			resp, err := vget(vendor + "/v1/ping")
			writeJSON(w, map[string]any{"status": statusOf(resp, err)})
		})

		g.Get("/hollow/status", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/ledger/hollow/status 1
			resp, err := http.Get(vendor + "/v1/hollow/status?lang=en") // @@T positive no_timeout vendor request has no timeout so a slow vendor holds the request open
			writeJSON(w, map[string]any{"status": statusOf(resp, err)})
		})

	})

	seedMadder := []struct {
		Label, Region string
		Count         int
	}{{"Sample madder", "north", 3}} // @@T decoy pii_data seed rows hold labels and counts and no person
	rt.With(bearer).Get("/api/ext/madder/sample", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/madder/sample 1
		writeJSON(w, map[string]any{"count": len(seedMadder)})
	})

	rt.With(cookieAuth).Get("/web/ext/fescue/keep", func(w http.ResponseWriter, req *http.Request) { // @@R GET /web/ext/fescue/keep 1
		u := userOf(req)
		http.SetCookie(w, &http.Cookie{Name: "keep", Value: st.openSession(u.UID, u.Role), Path: "/", HttpOnly: true, Secure: true, SameSite: http.SameSiteStrictMode, MaxAge: 3600}) // @@T decoy cookie_flags cookie sets httpOnly secure and sameSite Strict together with a one hour lifetime
		w.WriteHeader(http.StatusNoContent)
	})

	rt.With(bearer).Post("/api/salt/{id}/purge", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/salt/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
		if userOf(req).Role != "admin" {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		if !st.purge(chi.URLParam(req, "id")) {
			http.NotFound(w, req)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

}
