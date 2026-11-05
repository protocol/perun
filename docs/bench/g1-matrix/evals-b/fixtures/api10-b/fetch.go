package main

import (
	"encoding/json"
	"io"
	"net/http"
	"os"
	"path/filepath"
)

type report struct {
	Filename string `json:"filename"`
}

func pullReport(w http.ResponseWriter, r *http.Request) {
	resp, err := http.Get("https://reports.partner.example.com/v2/latest")
	if err != nil {
		http.Error(w, "upstream error", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	var rep report
	json.NewDecoder(resp.Body).Decode(&rep)

	file, err := http.Get("https://reports.partner.example.com/v2/latest/file")
	if err != nil {
		http.Error(w, "upstream error", http.StatusBadGateway)
		return
	}
	defer file.Body.Close()
	out, _ := os.Create(filepath.Join("/var/data/reports", rep.Filename))
	defer out.Close()
	io.Copy(out, file.Body)
	w.WriteHeader(http.StatusAccepted)
}
