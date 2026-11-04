package main

import (
	"bytes"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"regexp"
	"time"
)

var (
	photoClient = &http.Client{
		Timeout:       6 * time.Second,
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}
	lookupClient = &http.Client{Timeout: 6 * time.Second}
	loginWindow  = newWindow()
	photoIDRe    = regexp.MustCompile(`^[0-9]{1,9}$`)
	skuRe        = regexp.MustCompile(`^[A-Z0-9-]{3,20}$`)
	cardRe       = regexp.MustCompile(`^[0-9]{12,19}$`)
)

func signIn(w http.ResponseWriter, r *http.Request) {
	if !loginWindow.allow(clientIP(r), 8, 10*time.Minute) { // @@T decoy rate_limit sign-in attempts counted per client address in a ten minute window and answered 429 past the cap
		w.Header().Set("Retry-After", "600")
		http.Error(w, "too many attempts", http.StatusTooManyRequests)
		return
	}
	want := os.Getenv("GARAGE_PASSCODE")
	if want == "" || !same(r.FormValue("passcode"), want) {
		http.Error(w, "wrong passcode", http.StatusUnauthorized)
		return
	}
	tok, _ := db.openSession(41, "staff")
	respond(w, map[string]string{"token": tok})
}

func photoFetch(w http.ResponseWriter, r *http.Request) {
	id := r.PathValue("id")
	if !photoIDRe.MatchString(id) {
		http.Error(w, "bad id", http.StatusBadRequest)
		return
	}
	resp, err := photoClient.Get("https://img.vendor.example.com/p/" + id + ".jpg") // @@T decoy ssrf host fixed in code and the caller supplies only a validated numeric id with redirects off
	if err != nil {
		http.Error(w, "upstream unavailable", http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	w.Header().Set("Content-Type", "image/jpeg")
	io.Copy(w, io.LimitReader(resp.Body, 4<<20))
}

func vinHistory(w http.ResponseWriter, r *http.Request) {
	vin := r.PathValue("vin")
	if !vinRe.MatchString(vin) {
		http.Error(w, "bad vin", http.StatusBadRequest)
		return
	}
	req, _ := http.NewRequest("GET", vinBase+"/v2/history/"+vin, nil)
	req.Header.Set("X-Api-Key", vinKey) // @@T decoy secret_in_url vendor key carried in a request header and the URL holds only the validated vin
	resp, err := lookupClient.Do(req)
	relay(w, resp, err)
}

func updatePhone(w http.ResponseWriter, r *http.Request) {
	if !same(r.Header.Get("X-CSRF-Token"), me(r).CSRF) { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
		http.Error(w, "bad token", http.StatusForbidden)
		return
	}
	if len(r.FormValue("phone")) > 20 {
		http.Error(w, "bad phone", http.StatusBadRequest)
		return
	}
	w.WriteHeader(http.StatusNoContent)
}

func rotateSession(w http.ResponseWriter, r *http.Request) {
	old, _ := r.Cookie("sid")
	s := me(r)
	if !same(r.Header.Get("X-CSRF-Token"), s.CSRF) {
		http.Error(w, "bad token", http.StatusForbidden)
		return
	}
	db.closeSession(old.Value)
	tok, _ := db.openSession(s.UserID, s.Role)
	http.SetCookie(w, &http.Cookie{Name: "sid", Value: tok, Path: "/", MaxAge: 3600, Secure: true, HttpOnly: true, SameSite: http.SameSiteLaxMode}) // @@T decoy cookie_flags Secure HttpOnly and SameSite all set with a one hour lifetime
	w.WriteHeader(http.StatusNoContent)
}

func endSession(w http.ResponseWriter, r *http.Request) {
	old, _ := r.Cookie("sid")
	if !same(r.Header.Get("X-CSRF-Token"), me(r).CSRF) {
		http.Error(w, "bad token", http.StatusForbidden)
		return
	}
	db.closeSession(old.Value)
	http.SetCookie(w, &http.Cookie{Name: "sid", Value: "", Path: "/", MaxAge: -1, Secure: true, HttpOnly: true, SameSite: http.SameSiteLaxMode}) // @@T decoy cookie_flags expiry cookie keeps every attribute and the server session is dropped first
	w.WriteHeader(http.StatusNoContent)
}

func settle(w http.ResponseWriter, r *http.Request) {
	card := r.FormValue("card")
	if !cardRe.MatchString(card) {
		http.Error(w, "bad card", http.StatusBadRequest)
		return
	}
	log.Printf("payment accepted user=%d last4=%s", me(r).UserID, card[len(card)-4:]) // @@T decoy pii_log only the numeric user id and the last four digits are logged
	w.WriteHeader(http.StatusAccepted)
}

func trackVisit(w http.ResponseWriter, r *http.Request) {
	body, _ := json.Marshal(map[string]any{"event": "visit", "user": me(r).UserID}) // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
	lookupClient.Post("https://analytics.vendor.example.com/collect", "application/json", bytes.NewReader(body))
	w.WriteHeader(http.StatusAccepted)
}

func askQuestion(w http.ResponseWriter, r *http.Request) {
	q := r.FormValue("question")
	if q == "" || len(q) > 500 {
		http.Error(w, "bad question", http.StatusBadRequest)
		return
	}
	io.WriteString(w, chat([]msg{{Role: "system", Content: "Answer questions about opening hours and services only."}, {Role: "user", Content: q}})) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
}

func partLookup(w http.ResponseWriter, r *http.Request) {
	sku := r.FormValue("sku")
	if !skuRe.MatchString(sku) {
		http.Error(w, "bad sku", http.StatusBadRequest)
		return
	}
	args, _ := json.Marshal(map[string]any{"name": "part_lookup", "arguments": map[string]string{"sku": sku}}) // @@T decoy prompt_injection tool name fixed and the validated sku is JSON-encoded as data
	lookupClient.Post("https://llm.vendor.example.com/v1/tools", "application/json", bytes.NewReader(args))
	w.WriteHeader(http.StatusAccepted)
}

func mountYard(mux *http.ServeMux) {
	mux.HandleFunc("POST /auth/login", signIn)                                // @@R POST /auth/login 0 public
	mux.HandleFunc("GET /api/ext/photo/{id}", member(photoFetch))             // @@R GET /api/ext/photo/{id} 1
	mux.HandleFunc("GET /api/ext/vin/{vin}/history", member(vinHistory))      // @@R GET /api/ext/vin/{vin}/history 1
	mux.HandleFunc("POST /web/ext/profile/phone", cookieAuth(updatePhone))    // @@R POST /web/ext/profile/phone 1
	mux.HandleFunc("POST /web/ext/session/rotate", cookieAuth(rotateSession)) // @@R POST /web/ext/session/rotate 1
	mux.HandleFunc("POST /web/ext/session/end", cookieAuth(endSession))       // @@R POST /web/ext/session/end 1
	mux.HandleFunc("POST /api/ext/billing/settle", member(settle))            // @@R POST /api/ext/billing/settle 1
	mux.HandleFunc("POST /api/ext/track/visit", member(trackVisit))           // @@R POST /api/ext/track/visit 1
	mux.HandleFunc("POST /api/ext/assist/question", member(askQuestion))      // @@R POST /api/ext/assist/question 1
	mux.HandleFunc("POST /api/ext/assist/part", member(partLookup))           // @@R POST /api/ext/assist/part 1
}
