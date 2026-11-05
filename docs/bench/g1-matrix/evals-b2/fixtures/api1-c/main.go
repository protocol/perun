package main

import (
	"net/http"
	"time"
)

func main() {
	h := &Handlers{store: NewStore()}
	mux := http.NewServeMux()
	mux.HandleFunc("GET /orders", h.list)
	mux.HandleFunc("GET /orders/{id}", h.get)
	mux.HandleFunc("PUT /orders/{id}/address", h.setAddress)
	mux.HandleFunc("GET /orders/{id}/tracking", h.tracking)
	srv := &http.Server{
		Addr:         ":8080",
		Handler:      withCustomer(mux),
		ReadTimeout:  5 * time.Second,
		WriteTimeout: 10 * time.Second,
	}
	srv.ListenAndServe()
}
