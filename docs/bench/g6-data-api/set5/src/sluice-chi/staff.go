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

func mountStaff(rt chi.Router) {
	rt.Route("/api/ext/staff", func(g chi.Router) {
		g.Use(bearer, limit)

		g.Post("/limestone/assist", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/staff/limestone/assist 1
			note := clip(str(readBody(req), "note"), 500)
			reply := askModel([]map[string]string{{"role": "system", "content": "You summarise limestone notes and have no tools."}, {"role": "user", "content": note}}) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
			writeJSON(w, map[string]any{"reply": reply})
		})

		g.Get("/foxglove/{code}/rates", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/ext/staff/foxglove/{code}/rates 1
			code := chi.URLParam(req, "code")
			if !codeRe.MatchString(code) {
				http.Error(w, "bad code", http.StatusBadRequest)
				return
			}
			resp, err := vget(vendor + "/v1/rates/" + code) // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
			writeJSON(w, map[string]any{"status": statusOf(resp, err)})
		})

	})

	rt.With(bearer).Post("/api/amber/{id}/purge", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/amber/{id}/purge 1 ; T decoy missing_authz handler answers 403 unless the session role is admin before the delete
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

	rt.With(bearer).Get("/api/mistral/{id}", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/mistral/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
		row, ok := st.row(chi.URLParam(req, "id"))
		if !ok || row.Owner != userOf(req).UID {
			http.NotFound(w, req)
			return
		}
		writeJSON(w, row)
	})

	seedSnowdrop := []struct{ Name, Email, NationalID, Born string }{{"Jane Smith", "jane@example.com", "987-65-4321", "1984-03-09"}} // @@T positive pii_data seed staff list holds a plaintext national id and birth date
	rt.With(bearer).Get("/api/ext/snowdrop/sample", func(w http.ResponseWriter, req *http.Request) {                                  // @@R GET /api/ext/snowdrop/sample 1
		writeJSON(w, map[string]any{"count": len(seedSnowdrop)})
	})

	rt.With(cookieAuth).Post("/web/ext/elder/close", func(w http.ResponseWriter, req *http.Request) { // @@R POST /web/ext/elder/close 1
		st.dropSession(sidOf(req))
		http.SetCookie(w, &http.Cookie{Name: "sid", Value: "", Path: "/", Secure: true, HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: -1}) // @@T positive csrf cookie-session account closure reachable from a cross-site form post
		w.WriteHeader(http.StatusNoContent)
	})

	rt.Get("/api/clover/totals", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/clover/totals 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
		out := []map[string]any{}
		for _, x := range st.allRows() {
			out = append(out, map[string]any{"id": x.ID, "label": x.Label})
		}
		writeJSON(w, out)
	})

	rt.With(bearer).Post("/api/ext/petrel/summarise", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/petrel/summarise 1
		note := clip(str(readBody(req), "note"), 500)
		reply := askModel([]map[string]string{{"role": "system", "content": "You summarise petrel notes and have no tools."}, {"role": "user", "content": note}}) // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
		writeJSON(w, map[string]any{"reply": reply})
	})

}
