package main

import (
	"context"
	"net/http"
)

type ctxKey string

var tokens = map[string]string{"k-1": "cust-1", "k-2": "cust-2"}

func withCustomer(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		c, ok := tokens[r.Header.Get("X-Api-Key")]
		if !ok {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		ctx := context.WithValue(r.Context(), ctxKey("customer"), c)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

func customerOf(r *http.Request) string {
	c, _ := r.Context().Value(ctxKey("customer")).(string)
	return c
}

func owns(r *http.Request, o *Order) bool {
	return o != nil && o.Customer == customerOf(r)
}
