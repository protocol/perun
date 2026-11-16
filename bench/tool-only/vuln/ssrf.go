package bench

import (
	"io"
	"net/http"
)

func Fetch(w http.ResponseWriter, r *http.Request) {
	resp, err := http.Get(r.URL.Query().Get("u"))
	if err != nil {
		http.Error(w, "bad gateway", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	io.Copy(w, resp.Body)
}
