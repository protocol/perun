package main

import (
	"crypto/tls"
	"io"
	"log"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"time"
)

const carrierBase = "https://carrier.vendor.example.com"

var (
	carrierKey = os.Getenv("CARRIER_KEY")
	zoneRe     = regexp.MustCompile(`^[a-z]{2,8}$`)
	sheetHosts = map[string]bool{"sheets.example.com": true, "static.example.com": true}
	client     = &http.Client{Timeout: 5 * time.Second}
)

// registerOutbound routes all sit under /api and are covered by the gate.
func registerOutbound(mux *http.ServeMux) {
	mux.HandleFunc("POST /api/carrier/refresh", func(w http.ResponseWriter, r *http.Request) { // @@R POST /api/carrier/refresh 1
		insecure := &http.Client{
			Timeout:   5 * time.Second,
			Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}, // @@T positive tls_off certificate verification disabled
		}
		req, _ := http.NewRequest("GET", carrierBase+"/v1/zones", nil)
		req.Header.Set("X-Api-Key", carrierKey)
		resp, err := insecure.Do(req)
		if err != nil {
			http.Error(w, "upstream", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		io.Copy(w, resp.Body)
	})

	mux.HandleFunc("GET /api/preview", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/preview 1
		resp, err := client.Get(r.URL.Query().Get("url")) // @@T positive ssrf caller-controlled URL fetched server side
		if err != nil {
			http.Error(w, "fetch failed", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		w.Header().Set("Content-Type", resp.Header.Get("Content-Type"))
		io.Copy(w, resp.Body)
	})

	mux.HandleFunc("GET /api/preview/safe", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/preview/safe 1
		u, err := url.Parse(r.URL.Query().Get("url"))
		if err != nil || u.Scheme != "https" || !sheetHosts[u.Hostname()] {
			http.Error(w, "host not allowed", http.StatusBadRequest)
			return
		}
		noRedirect := &http.Client{Timeout: 5 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
		resp, err := noRedirect.Get(u.String()) // @@T decoy ssrf https plus host allowlist plus no redirects
		if err != nil {
			http.Error(w, "fetch failed", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		io.Copy(w, resp.Body)
	})

	mux.HandleFunc("GET /api/carrier/rates/{zone}", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/carrier/rates/{zone} 1
		zone := r.PathValue("zone")
		if !zoneRe.MatchString(zone) {
			http.Error(w, "bad zone", http.StatusBadRequest)
			return
		}
		req, _ := http.NewRequest("GET", carrierBase+"/v1/rates/"+zone, nil)
		req.Header.Set("X-Api-Key", carrierKey)
		resp, err := http.DefaultClient.Do(req) // @@T positive no_timeout default client has no timeout
		if err != nil {
			http.Error(w, "upstream", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		io.Copy(w, resp.Body)
	})

	mux.HandleFunc("GET /api/carrier/rates/{zone}/history", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/carrier/rates/{zone}/history 1
		zone := r.PathValue("zone")
		if !zoneRe.MatchString(zone) {
			http.Error(w, "bad zone", http.StatusBadRequest)
			return
		}
		req, _ := http.NewRequest("GET", carrierBase+"/v1/rates/"+zone+"/history", nil)
		req.Header.Set("X-Api-Key", carrierKey)
		resp, err := client.Do(req) // @@T decoy secret_in_url key sent in a header, with timeout
		if err != nil {
			http.Error(w, "upstream", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		io.Copy(w, resp.Body)
	})

	mux.HandleFunc("GET /api/carrier/rates/{zone}/archive", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/carrier/rates/{zone}/archive 1
		zone := r.PathValue("zone")
		if !zoneRe.MatchString(zone) {
			http.Error(w, "bad zone", http.StatusBadRequest)
			return
		}
		target := carrierBase + "/v1/rates/" + zone + "/archive?key=" + carrierKey // @@T positive secret_in_url API key in the query string
		resp, err := client.Get(target)
		if err != nil {
			http.Error(w, "upstream", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		io.Copy(w, resp.Body)
	})

	mux.HandleFunc("GET /api/carrier/rates/{zone}/digest", func(w http.ResponseWriter, r *http.Request) { // @@R GET /api/carrier/rates/{zone}/digest 1
		zone := r.PathValue("zone")
		if !zoneRe.MatchString(zone) {
			http.Error(w, "bad zone", http.StatusBadRequest)
			return
		}
		log.Printf("digest call using key %s", carrierKey) // @@T positive secret_in_log key written to the log
		req, _ := http.NewRequest("GET", carrierBase+"/v1/rates/"+zone+"/digest", nil)
		req.Header.Set("X-Api-Key", carrierKey)
		resp, err := client.Do(req)
		if err != nil {
			http.Error(w, "upstream", http.StatusBadGateway)
			return
		}
		defer resp.Body.Close()
		io.Copy(w, resp.Body)
	})
}
