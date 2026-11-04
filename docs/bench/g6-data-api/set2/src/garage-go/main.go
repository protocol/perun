package main

import (
	"context"
	"encoding/json"
	"log"
	"net/http"
	"strconv"
	"strings"
)

type ctxKey struct{}

func bearerSession(r *http.Request) (Session, bool) {
	return db.session(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
}

func cookieSession(r *http.Request) (Session, bool) {
	c, err := r.Cookie("sid")
	if err != nil {
		return Session{}, false
	}
	return db.session(c.Value)
}

func withSession(r *http.Request, s Session) *http.Request {
	return r.WithContext(context.WithValue(r.Context(), ctxKey{}, s))
}

func me(r *http.Request) Session {
	s, _ := r.Context().Value(ctxKey{}).(Session)
	return s
}

func member(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		s, ok := bearerSession(r)
		if !ok {
			http.Error(w, "sign in first", http.StatusUnauthorized)
			return
		}
		h(w, withSession(r, s))
	}
}

func staffOnly(h http.HandlerFunc) http.HandlerFunc {
	return member(func(w http.ResponseWriter, r *http.Request) {
		if me(r).Role != "staff" {
			http.Error(w, "staff only", http.StatusForbidden)
			return
		}
		h(w, r)
	})
}

func cookieAuth(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		c, err := r.Cookie("sid")
		if err != nil {
			http.Error(w, "sign in first", http.StatusUnauthorized)
			return
		}
		s, ok := db.session(c.Value)
		if !ok {
			http.Error(w, "sign in first", http.StatusUnauthorized)
			return
		}
		h(w, withSession(r, s))
	}
}

func idParam(r *http.Request, name string) (int, bool) {
	n, err := strconv.Atoi(r.PathValue(name))
	return n, err == nil && n > 0
}

func respond(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(v)
}

func main() {
	mux := http.NewServeMux()
	mountGarage(mux)
	mountShop(mux) // shop_extras.go
	mountYard(mux) // yard_extras.go
	log.Fatal(http.ListenAndServe("127.0.0.1:8080", mux))
}
