package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strings"
)

type Session struct {
	UserID int
	Role   string
}

type ctxKey struct{}

var tokens = map[string]Session{
	"tok-picker": {UserID: 40, Role: "picker"},
	"tok-admin":  {UserID: 41, Role: "admin"},
}

func sessionFor(r *http.Request) (Session, bool) {
	token := strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer ")
	s, ok := tokens[token]
	return s, ok
}

func userFrom(r *http.Request) Session {
	s, _ := r.Context().Value(ctxKey{}).(Session)
	return s
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

// gate is the global middleware: every /api/ path needs a session except the partner prefix.
func gate(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if !strings.HasPrefix(r.URL.Path, "/api/") || strings.HasPrefix(r.URL.Path, "/api/open/") {
			next.ServeHTTP(w, r)
			return
		}
		s, ok := sessionFor(r)
		if !ok {
			http.Error(w, "unauthenticated", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, r.WithContext(context.WithValue(r.Context(), ctxKey{}, s)))
	})
}

// requireLogin wraps a single handler with a login check.
func requireLogin(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		s, ok := sessionFor(r)
		if !ok {
			http.Error(w, "unauthenticated", http.StatusUnauthorized)
			return
		}
		h(w, r.WithContext(context.WithValue(r.Context(), ctxKey{}, s)))
	}
}

// requireRole wraps a single handler with a login and role check.
func requireRole(role string, h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		s, ok := sessionFor(r)
		if !ok {
			http.Error(w, "unauthenticated", http.StatusUnauthorized)
			return
		}
		if s.Role != role {
			http.Error(w, "forbidden", http.StatusForbidden)
			return
		}
		h(w, r.WithContext(context.WithValue(r.Context(), ctxKey{}, s)))
	}
}

func main() {
	mux := http.NewServeMux()
	registerStock(mux)
	registerOutbound(mux)
	registerExtras(mux)
	log.Fatal(http.ListenAndServe(":8080", gate(mux)))
}
