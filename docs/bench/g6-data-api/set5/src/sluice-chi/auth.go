package main

import (
	"context"
	"net/http"
	"strings"
)

type ctxKey struct{}

func userOf(req *http.Request) *Session {
	u, _ := req.Context().Value(ctxKey{}).(*Session)
	return u
}

func sidOf(req *http.Request) string {
	c, err := req.Cookie("sid")
	if err != nil {
		return ""
	}
	return c.Value
}

func gate(next http.Handler, tok string) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		u := st.session(tok)
		if tok == "" || u == nil {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next.ServeHTTP(w, req.WithContext(context.WithValue(req.Context(), ctxKey{}, u)))
	})
}

func bearer(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		tok := strings.TrimPrefix(req.Header.Get("Authorization"), "Bearer ")
		gate(next, tok).ServeHTTP(w, req)
	})
}

func cookieAuth(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
		gate(next, sidOf(req)).ServeHTTP(w, req)
	})
}
