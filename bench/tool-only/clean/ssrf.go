package bench

import (
	"io"
	"net/http"
)

func Fetch(w http.ResponseWriter, r *http.Request) {
	if r.URL.Query().Get("t") != "status" {
		http.Error(w, "unknown target", http.StatusBadRequest)
		return
	}
	resp, err := http.Get("https://api.example.com/status")
	if err != nil {
		http.Error(w, "bad gateway", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	io.Copy(w, resp.Body)
}
