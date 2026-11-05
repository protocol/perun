package main

import (
	"database/sql"
	"net/http"
)

var db *sql.DB

func requireSession(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if _, ok := lookupSession(r.Header.Get("X-Session")); !ok {
			http.Error(w, "login required", http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

func removeUser(w http.ResponseWriter, r *http.Request) {
	id := r.URL.Query().Get("id")
	if _, err := db.Exec("DELETE FROM users WHERE id = ?", id); err != nil {
		http.Error(w, "error", http.StatusInternalServerError)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func main() {
	http.HandleFunc("/api/users/remove", requireSession(removeUser))
	http.ListenAndServe(":8080", nil)
}
