package bench

import (
	"io"
	"net/http"
	"os"
)

func Download(w http.ResponseWriter, r *http.Request) {
	root, err := os.OpenRoot("/srv/files")
	if err != nil {
		http.Error(w, "unavailable", http.StatusInternalServerError)
		return
	}
	defer root.Close()
	f, err := root.Open(r.URL.Query().Get("f"))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	io.Copy(w, f)
}
