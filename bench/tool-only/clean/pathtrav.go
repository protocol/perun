package bench

import (
	"io"
	"log"
	"net/http"
)

func Download(w http.ResponseWriter, r *http.Request) {
	// http.Dir cleans the name and cannot escape its root directory.
	f, err := http.Dir("/srv/files").Open(r.URL.Query().Get("f"))
	if err != nil {
		http.NotFound(w, r)
		return
	}
	defer func() {
		if err := f.Close(); err != nil {
			log.Println(err)
		}
	}()
	if _, err := io.Copy(w, f); err != nil {
		log.Println(err)
	}
}
