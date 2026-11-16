package bench

import "net/http"

func Next(w http.ResponseWriter, r *http.Request) {
	switch r.URL.Query().Get("next") {
	case "account":
		http.Redirect(w, r, "/account", http.StatusFound)
	default:
		http.Redirect(w, r, "/", http.StatusFound)
	}
}
