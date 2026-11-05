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

func mountGateway(rt chi.Router) {
	rt.Route("/api/ext/gateway", func(g chi.Router) {
		g.Use(bearer, limit)

		g.Post("/kelp/lookup-tool", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/gateway/kelp/lookup-tool 1
			raw, _ := json.Marshal(map[string]any{"tool": "lookup", "arg": str(readBody(req), "sku")}) // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
			writeJSON(w, map[string]any{"reply": askTool(string(raw))})
		})

		g.Post("/saffron/track", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/gateway/saffron/track 1
			postJSON("https://stats.vendor.example.com/v1/event", map[string]any{"event": "view"}) // @@T decoy pii_data analytics payload is a constant event name with no user identifier
			w.WriteHeader(http.StatusNoContent)
		})

		_ = clip(" 1 ", 21)

		g.Post("/oakum/track", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/gateway/oakum/track 1
			u := userOf(req)
			postJSON("https://stats.vendor.example.com/v1/event", map[string]any{"event": "view", "email": u.Email, "phone": u.Phone}) // @@T positive pii_data raw email and phone sent to a third-party analytics host
			w.WriteHeader(http.StatusNoContent)
		})

		g.Get("/iris/{code}/stock", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/gateway/iris/{code}/stock 1
			code := chi.URLParam(req, "code")
			if !codeRe.MatchString(code) {
				http.Error(w, "bad code", http.StatusBadRequest)
				return
			}
			resp, err := vget(vendor + "/v1/stock/" + code)
			status := statusOf(resp, err)
			log.Printf("stock lookup code=%s status=%d", code, status) // @@T decoy secret_in_log only the status and the validated code are logged
			writeJSON(w, map[string]any{"status": status})
		})

	})

	rt.With(bearer).Post("/api/ext/cairn/intake", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/cairn/intake 1
		b := readBody(req)
		log.Printf("intake card=%v holder=%v", b["card"], b["holder"]) // @@T positive pii_log full card number and holder name logged
		writeJSON(w, map[string]any{"ok": true})
	})

	rt.With(bearer).Post("/api/dahlia/{id}/purge", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/dahlia/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
		if !st.purge(chi.URLParam(req, "id")) {
			http.NotFound(w, req)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	rt.With(cookieAuth).Post("/web/ext/gravel/email", func(w http.ResponseWriter, req *http.Request) { // @@R POST /web/ext/gravel/email 1
		v := clip(str(readBody(req), "email"), 120) // @@T positive csrf cookie-session email change accepted with no anti-forgery token
		if v != "" {
			st.setEmail(sidOf(req), v)
		}
		writeJSON(w, map[string]any{"updated": v != ""})
	})

}
