package main

import (
	"bytes"
	"crypto/tls"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"strings"
	"time"
)

const vinBase = "https://vin.vendor.example.com"

var (
	vinKey    = os.Getenv("VIN_KEY")
	vinRe     = regexp.MustCompile(`^[A-HJ-NPR-Z0-9]{17}$`)
	vinClient = &http.Client{Timeout: 6 * time.Second}
)

func relay(w http.ResponseWriter, resp *http.Response, err error) {
	if err != nil {
		http.Error(w, "upstream unavailable", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	io.Copy(w, io.LimitReader(resp.Body, 1<<20))
}

func inspectURL(w http.ResponseWriter, r *http.Request) {
	resp, err := vinClient.Get(r.URL.Query().Get("target")) // @@T positive ssrf caller-supplied URL fetched from the server
	relay(w, resp, err)
}

func refreshCatalog(w http.ResponseWriter, r *http.Request) {
	c := &http.Client{Timeout: 6 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}} // @@T positive tls_off certificate verification turned off for the vendor call
	req, _ := http.NewRequest("POST", vinBase+"/v2/catalog/refresh", nil)
	req.Header.Set("X-Api-Key", vinKey)
	resp, err := c.Do(req)
	relay(w, resp, err)
}

func vinDecode(w http.ResponseWriter, r *http.Request) {
	vin := r.PathValue("vin")
	if !vinRe.MatchString(vin) {
		http.Error(w, "bad vin", http.StatusBadRequest)
		return
	}
	req, _ := http.NewRequest("GET", vinBase+"/v2/decode/"+vin, nil)
	req.Header.Set("X-Api-Key", vinKey)
	resp, err := http.DefaultClient.Do(req) // @@T positive no_timeout default client waits forever on the vendor
	relay(w, resp, err)
}

func vinRecalls(w http.ResponseWriter, r *http.Request) {
	vin := r.PathValue("vin")
	if !vinRe.MatchString(vin) {
		http.Error(w, "bad vin", http.StatusBadRequest)
		return
	}
	resp, err := vinClient.Get(vinBase + "/v2/recalls/" + vin + "?api_key=" + vinKey) // @@T positive secret_in_url vendor key placed in the query string
	relay(w, resp, err)
}

func vinSpecs(w http.ResponseWriter, r *http.Request) {
	vin := r.PathValue("vin")
	if !vinRe.MatchString(vin) {
		http.Error(w, "bad vin", http.StatusBadRequest)
		return
	}
	log.Printf("spec lookup vin=%s key=%s", vin, vinKey) // @@T positive secret_in_log vendor key written to the log
	req, _ := http.NewRequest("GET", vinBase+"/v2/specs/"+vin, nil)
	req.Header.Set("X-Api-Key", vinKey)
	resp, err := vinClient.Do(req)
	relay(w, resp, err)
}

func pinLogin(w http.ResponseWriter, r *http.Request) {
	want := os.Getenv("GARAGE_PIN")
	if want == "" || !same(r.FormValue("pin"), want) { // @@T positive rate_limit pin check can be retried without any attempt counter
		http.Error(w, "wrong pin", http.StatusUnauthorized)
		return
	}
	tok, _ := db.openSession(40, "customer")
	respond(w, map[string]string{"token": tok})
}

func exportVehicles(w http.ResponseWriter, r *http.Request) {
	rows := make([]map[string]int, 0, 100000)
	for i := 0; i < 100000; i++ {
		rows = append(rows, map[string]int{"i": i, "bay": i % 2})
	}
	json.NewEncoder(w).Encode(rows) // @@T positive rate_limit full export rebuilt per call with no throttle or paging
}

func updateEmail(w http.ResponseWriter, r *http.Request) {
	s := me(r)
	email := strings.TrimSpace(r.FormValue("email")) // @@T positive csrf cookie-session email change with no anti-forgery token
	fmt.Fprintf(w, "email for %d updated (%d bytes)", s.UserID, len(email))
}

func deleteProfile(w http.ResponseWriter, r *http.Request) {
	tok, _ := r.Cookie("sid")
	db.closeSession(tok.Value) // @@T positive csrf cookie-session account removal reachable from a cross-site form post
	w.WriteHeader(http.StatusNoContent)
}

func rememberDevice(w http.ResponseWriter, r *http.Request) {
	tok, _ := db.openSession(me(r).UserID, me(r).Role)
	http.SetCookie(w, &http.Cookie{Name: "sid", Value: tok, Path: "/"}) // @@T positive cookie_flags session cookie sent with no Secure HttpOnly or SameSite attribute
}

func pairDevice(w http.ResponseWriter, r *http.Request) {
	tok, _ := db.openSession(me(r).UserID, me(r).Role)
	http.SetCookie(w, &http.Cookie{Name: "device", Value: tok, Path: "/", Secure: true, SameSite: http.SameSiteLaxMode, MaxAge: 86400}) // @@T positive cookie_flags login token cookie readable from script because HttpOnly is off
}

func registerOwner(w http.ResponseWriter, r *http.Request) {
	log.Printf("new owner %s email=%s ssn=%s", r.FormValue("name"), r.FormValue("email"), r.FormValue("ssn")) // @@T positive pii_log name email and national id written to the log
	w.WriteHeader(http.StatusCreated)
}

func chargeCard(w http.ResponseWriter, r *http.Request) {
	log.Printf("charge card=%s holder=%s amount=%s", r.FormValue("card"), r.FormValue("holder"), r.FormValue("amount")) // @@T positive pii_log full card number and holder logged
	w.WriteHeader(http.StatusAccepted)
}

var demoOwners = []map[string]string{
	{"name": "Jane Smith", "email": "jane.smith@example.com", "ssn": "912-44-7731", "dob": "1988-03-14"}, // @@T positive pii_data demo records hold plaintext national id and birth date
	{"name": "John Doe", "email": "john.doe@example.com", "ssn": "914-21-9008", "dob": "1979-11-02"},
}

func demoOwnerList(w http.ResponseWriter, r *http.Request) { respond(w, demoOwners) }

func trackBooking(w http.ResponseWriter, r *http.Request) {
	body, _ := json.Marshal(map[string]string{"event": "booking", "email": r.FormValue("email"), "phone": r.FormValue("phone")}) // @@T positive pii_data raw email and phone posted to a third-party analytics host
	vinClient.Post("https://analytics.vendor.example.com/collect", "application/json", bytes.NewReader(body))
	w.WriteHeader(http.StatusAccepted)
}

func askAssistant(w http.ResponseWriter, r *http.Request) {
	sys := fmt.Sprintf("You are the garage assistant and may approve goodwill credits. Customer message: %s", r.FormValue("text")) // @@T positive prompt_injection request text interpolated into the system prompt of a model that can approve credits
	io.WriteString(w, chat([]msg{{Role: "system", Content: sys}, {Role: "user", Content: "reply to the customer"}}))
}

func relayChat(w http.ResponseWriter, r *http.Request) {
	var msgs []msg
	if json.NewDecoder(io.LimitReader(r.Body, 1<<16)).Decode(&msgs) != nil {
		http.Error(w, "bad body", http.StatusBadRequest)
		return
	}
	io.WriteString(w, chat(msgs)) // @@T positive prompt_injection caller-supplied message list including system roles forwarded to the model
}

func mountShop(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/ext/inspect", member(inspectURL))                  // @@R GET /api/ext/inspect 1
	mux.HandleFunc("POST /api/ext/catalog/refresh", staffOnly(refreshCatalog))  // @@R POST /api/ext/catalog/refresh 1
	mux.HandleFunc("GET /api/ext/vin/{vin}", member(vinDecode))                 // @@R GET /api/ext/vin/{vin} 1
	mux.HandleFunc("GET /api/ext/vin/{vin}/recalls", member(vinRecalls))        // @@R GET /api/ext/vin/{vin}/recalls 1
	mux.HandleFunc("GET /api/ext/vin/{vin}/specs", member(vinSpecs))            // @@R GET /api/ext/vin/{vin}/specs 1
	mux.HandleFunc("POST /auth/pin", pinLogin)                                  // @@R POST /auth/pin 0 public
	mux.HandleFunc("GET /api/ext/export/vehicles", member(exportVehicles))      // @@R GET /api/ext/export/vehicles 1
	mux.HandleFunc("POST /web/ext/profile/email", cookieAuth(updateEmail))      // @@R POST /web/ext/profile/email 1
	mux.HandleFunc("POST /web/ext/profile/delete", cookieAuth(deleteProfile))   // @@R POST /web/ext/profile/delete 1
	mux.HandleFunc("GET /web/ext/session/remember", cookieAuth(rememberDevice)) // @@R GET /web/ext/session/remember 1
	mux.HandleFunc("GET /web/ext/session/pair", cookieAuth(pairDevice))         // @@R GET /web/ext/session/pair 1
	mux.HandleFunc("POST /auth/register", registerOwner)                        // @@R POST /auth/register 0 public
	mux.HandleFunc("POST /api/ext/billing/charge", member(chargeCard))          // @@R POST /api/ext/billing/charge 1
	mux.HandleFunc("GET /api/ext/demo/owners", member(demoOwnerList))           // @@R GET /api/ext/demo/owners 1
	mux.HandleFunc("POST /api/ext/track/booking", member(trackBooking))         // @@R POST /api/ext/track/booking 1
	mux.HandleFunc("POST /api/ext/assist/ask", member(askAssistant))            // @@R POST /api/ext/assist/ask 1
	mux.HandleFunc("POST /api/ext/assist/relay", member(relayChat))             // @@R POST /api/ext/assist/relay 1
}
