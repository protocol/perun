package main

import (
	"encoding/json"
	"net/http"
	"regexp"
)

var stationID = regexp.MustCompile(`^[A-Z]{4}[0-9]{2}$`)

func latest(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if !stationID.MatchString(id) {
		http.Error(w, "bad station", http.StatusBadRequest)
		return
	}
	body, err := openStation(id)
	if err != nil {
		http.Error(w, "feed unavailable", http.StatusBadGateway)
		return
	}
	reading, err := readStation(body)
	if err != nil {
		http.Error(w, "bad feed data", http.StatusBadGateway)
		return
	}
	json.NewEncoder(w).Encode(reading)
}

func main() {
	mux := http.NewServeMux()
	mux.HandleFunc("GET /stations/{id}/latest", latest)
	http.ListenAndServe(":8090", mux)
}
