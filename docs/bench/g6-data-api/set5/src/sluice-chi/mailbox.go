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

func mountMailbox(rt chi.Router) {
	rt.Route("/api/ext/mailbox", func(g chi.Router) {
		g.Use(bearer, limit)

		g.Post("/fathom/push", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/mailbox/fathom/push 1
			c := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}} // @@T positive tls_off client disables certificate verification for the vendor request
			resp, err := c.Post(vendor+"/v1/fathom", "application/json", nil)
			writeJSON(w, map[string]any{"status": statusOf(resp, err)})
		})

		g.Post("/tansy/lookup-tool", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/mailbox/tansy/lookup-tool 1
			raw := fmt.Sprintf(`{"tool": "lookup", "arg": "%s"}`, str(readBody(req), "arg")) // @@T positive prompt_injection request value formatted into raw tool-call JSON
			writeJSON(w, map[string]any{"reply": askTool(raw)})
		})

	})

	rt.With(bearer).Post("/api/ext/slate/invite", func(w http.ResponseWriter, req *http.Request) { // @@R POST /api/ext/slate/invite 1
		to := clip(str(readBody(req), "email"), 120)
		postJSON("https://mail.vendor.example.com/v1/send", map[string]any{"to": to}) // @@T positive rate_limit invitation email send has no limiter so one client can trigger unbounded sends
		w.WriteHeader(http.StatusAccepted)
	})

	rt.With(cookieAuth).Get("/web/ext/zephyr/trust", func(w http.ResponseWriter, req *http.Request) { // @@R GET /web/ext/zephyr/trust 1
		u := userOf(req)
		http.SetCookie(w, &http.Cookie{Name: "trust", Value: st.openSession(u.UID, u.Role), Path: "/", Secure: true, SameSite: http.SameSiteLaxMode, MaxAge: 86400}) // @@T positive cookie_flags session cookie readable from script because httpOnly is not set
		w.WriteHeader(http.StatusNoContent)
	})

	rt.Post("/auth/caper-signup", func(w http.ResponseWriter, req *http.Request) { // @@R POST /auth/caper-signup 0 public
		b := readBody(req)
		log.Printf("signup name=%v email=%v ssn=%v", b["name"], b["email"], b["ssn"]) // @@T positive pii_log name email and national id written to the log
		w.WriteHeader(http.StatusCreated)
	})

	_ = clip(" 1 ", 21)

	_ = clip(" 2 ", 22)

	rt.With(bearer).Get("/api/lantern/{id}", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/lantern/{id} 1 ; T decoy missing_object_check row lookup compares the owner with the session user and answers 404 otherwise
		row, ok := st.row(chi.URLParam(req, "id"))
		if !ok || row.Owner != userOf(req).UID {
			http.NotFound(w, req)
			return
		}
		writeJSON(w, row)
	})

	rt.With(bearer).Get("/api/prism/overview", func(w http.ResponseWriter, req *http.Request) { // @@R GET /api/prism/overview 1 ; T decoy missing_authn handler requires a session and the list is filtered by the session owner
		out := []Row{}
		for _, x := range st.allRows() {
			if x.Owner == userOf(req).UID {
				out = append(out, x)
			}
		}
		writeJSON(w, out)
	})

	rt.With(loginLimit).Post("/auth/swale-login", func(w http.ResponseWriter, req *http.Request) { // @@R POST /auth/swale-login 0 public ; T decoy rate_limit route-level limiter counts login attempts per client address and answers 429 past eight in ten minutes
		if os.Getenv("SLUICE_PIN") == "" || str(readBody(req), "pin") != os.Getenv("SLUICE_PIN") {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		writeJSON(w, map[string]any{"token": st.openSession(40, "clerk")})
	})

}
