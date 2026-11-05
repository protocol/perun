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

func mountSessions(rt chi.Router) {
	rt.With(bearer).Get("/api/garnet/stats", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/garnet/stats 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
		out := []Row{}
		for _, x := range st.allRows() {
			if x.Owner == userOf(req).UID {
				out = append(out, x)
			}
		}
		writeJSON(w, out)
	})

	rt.With(cookieAuth).Get("/web/ext/dusk/rotate", func(w http.ResponseWriter, req *http.Request) { // @@R GET /web/ext/dusk/rotate 1
		u := userOf(req)
		http.SetCookie(w, &http.Cookie{Name: "sid", Value: st.openSession(u.UID, u.Role), Path: "/", Secure: true, HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: 3600}) // @@T decoy cookie_flags new session cookie is secure httpOnly and sameSite Strict with a one hour lifetime
		w.WriteHeader(http.StatusNoContent)
	})

	rt.With(cookieAuth).Post("/web/ext/sleet/alias", func(w http.ResponseWriter, req *http.Request) { // @@R POST /web/ext/sleet/alias 1
		c, err := req.Cookie("csrf")
		if err != nil || c.Value == "" || !same(c.Value, req.Header.Get("X-Csrf-Token")) { // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		writeJSON(w, map[string]any{"updated": str(readBody(req), "alias") != ""})
	})

	rt.With(bearer).Get("/api/mallow/{id}", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/mallow/{id} 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
		row, ok := st.row(chi.URLParam(req, "id"))
		if !ok {
			http.NotFound(w, req)
			return
		}
		writeJSON(w, row)
	})

	rt.Get("/api/bluebell/recent", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/bluebell/recent 0 ; T positive missing_authn handler is registered with no authentication and lists internal rows to anyone
		out := []map[string]any{}
		for _, x := range st.allRows() {
			out = append(out, map[string]any{"id": x.ID, "label": x.Label})
		}
		writeJSON(w, out)
	})

	rt.With(bearer).Post("/api/sage/{id}/purge", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/sage/{id}/purge 0 ; T positive missing_authz purge is an admin action but the handler only requires a session
		if !st.purge(chi.URLParam(req, "id")) {
			http.NotFound(w, req)
			return
		}
		w.WriteHeader(http.StatusNoContent)
	})

	rt.With(cookieAuth).Post("/web/ext/bulrush/nickname", func(w http.ResponseWriter, req *http.Request) { // @@R POST /web/ext/bulrush/nickname 1
		v := clip(str(readBody(req), "nickname"), 40) // @@T positive csrf cookie-session nickname change accepted with no anti-forgery token
		writeJSON(w, map[string]any{"updated": v != ""})
	})

	rt.Route("/api/ext/sessions", func(g chi.Router) {
		g.Use(bearer, limit)

		g.Post("/dingle/assist", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/sessions/dingle/assist 1
			system := "You are the dingle assistant and may approve refunds. Operator note: " + str(readBody(req), "note") // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
			writeJSON(w, map[string]any{"reply": askModel([]map[string]string{{"role": "system", "content": system}})})
		})

	})

}
