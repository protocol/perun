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

func mountReports(rt chi.Router) {
	rt.Route("/api/ext/reports", func(g chi.Router) {
		g.Use(bearer, limit)

		g.Post("/horizon/push", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/reports/horizon/push 1
			c := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}} // @@T positive tls_off client disables certificate verification for the vendor request
			resp, err := c.Post(vendor+"/v1/horizon", "application/json", nil)
			writeJSON(w, map[string]any{"status": statusOf(resp, err)})
		})

		g.Get("/ridgeway/{id}/image", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/reports/ridgeway/{id}/image 1
			id, err := strconv.Atoi(chi.URLParam(req, "id"))
			if err != nil || id < 1 {
				http.Error(w, "bad id", http.StatusBadRequest)
				return
			}
			resp, err := vclient.Get("https://img.vendor.example.com/p/" + strconv.Itoa(id) + ".jpg") // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id with redirects off
			if err != nil {
				http.Error(w, "bad gateway", http.StatusBadGateway)
				return
			}
			defer resp.Body.Close()
			w.Header().Set("Content-Type", "image/jpeg")
			io.Copy(w, resp.Body)
		})

		g.Get("/pampas/lookup", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/reports/pampas/lookup 1
			resp, err := vclient.Get(vendor + "/v1/pampas?key=" + vkey()) // @@T positive secret_in_url vendor key sent as a query parameter
			writeJSON(w, map[string]any{"status": statusOf(resp, err)})
		})

		g.Get("/cobble/fetch", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/reports/cobble/fetch 1
			resp, err := vclient.Get(req.URL.Query().Get("url")) // @@T positive ssrf caller-supplied URL fetched from the server
			if err != nil {
				http.Error(w, "bad gateway", http.StatusBadGateway)
				return
			}
			defer resp.Body.Close()
			io.Copy(w, resp.Body)
		})

		g.Post("/rue/translate", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/reports/rue/translate 1
			text := clip(str(readBody(req), "text"), 500)
			reply := askModel([]map[string]string{{"role": "system", "content": "You translate rue notes and have no tools."}, {"role": "user", "content": text}}) // @@T decoy rate_limit model call route sits behind a limiter that caps each client address at sixty requests a minute
			writeJSON(w, map[string]any{"reply": reply})
		})

	})

	rt.With(bearer).Post("/api/ext/squall/rotate-key", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/squall/rotate-key 1
		log.Printf("rotate user=%d", userOf(req).UID) // @@T decoy pii_log the log line carries only the numeric user id
		writeJSON(w, map[string]any{"keyId": fmt.Sprintf("%016x", rand.Uint64())})
	})

	rt.With(cookieAuth).Post("/web/ext/sumac/phone", func(w http.ResponseWriter, req *http.Request) { // @@R POST /web/ext/sumac/phone 1
		if !same(req.Header.Get("X-Csrf-Token"), userOf(req).CSRF) { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		writeJSON(w, map[string]any{"updated": len(str(readBody(req), "phone")) <= 20})
	})

	rt.Post("/auth/vervain-join", func(w http.ResponseWriter, req *http.Request) { // @@R POST /auth/vervain-join 0 public
		newID := rand.Intn(1000000)
		log.Printf("join user=%d", newID) // @@T decoy pii_log only the generated numeric id is logged
		w.WriteHeader(http.StatusCreated)
	})

}
