package bench

import (
	"io"
	"net/http"
	"os"
	"path/filepath"
)

func Download(w http.ResponseWriter, r *http.Request) {
	f, err := os.Open(filepath.Join("/srv/files", r.URL.Query().Get("f")))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer f.Close()
	io.Copy(w, f)
}
