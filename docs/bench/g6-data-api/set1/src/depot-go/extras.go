package main

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"log"
	"net/http"
	"os"
	"strconv"
	"sync"
	"time"
)

var (
	llmClient = &http.Client{Timeout: 10 * time.Second}
	hits      = map[string]int{}
	hitsMu    sync.Mutex
)

func allow(key string) bool {
	hitsMu.Lock()
	defer hitsMu.Unlock()
	hits[key]++
	return hits[key] <= 20
}

func askLLM(system, user string) string {
	body, _ := json.Marshal(map[string]any{"messages": []map[string]string{{"role": "system", "content": system}, {"role": "user", "content": user}}})
	resp, err := llmClient.Post("https://llm.vendor.example.com/v1/chat", "application/json", bytes.NewReader(body))
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return string(out)
}

var sessionsByID = map[string]bool{"sess-demo": true}

// requireCookie is the cookie-session gate for the /web mount.
func requireCookie(h http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		c, err := r.Cookie("sid")
		if err != nil || !sessionsByID[c.Value] {
			http.Error(w, "login", http.StatusUnauthorized)
			return
		}
		h(w, r)
	}
}

func checkPassword(u, p string) bool { return u != "" && p == os.Getenv("DEPOT_PW") }

func sha(s string) string { h := sha256.Sum256([]byte(s)); return hex.EncodeToString(h[:8]) }

func exportAll(w http.ResponseWriter, r *http.Request) { // @@T positive rate_limit export builds the full dataset per call with no limiter
	rows := make([]int, 0, 50000)
	json.NewEncoder(w).Encode(rows)
}


func uploadBlob(w http.ResponseWriter, r *http.Request) { // @@T positive rate_limit upload accepts large bodies with no limiter
	n, _ := io.Copy(io.Discard, r.Body)
	w.Write([]byte(strconv.FormatInt(n, 10)))
}


// --
// --
func loginLimited(w http.ResponseWriter, r *http.Request) { // @@T decoy rate_limit login is counted per client and answers 429 past the cap
	if !allow("login:" + r.RemoteAddr) {
		http.Error(w, "slow down", http.StatusTooManyRequests)
		return
	}
	if !checkPassword(r.FormValue("user"), r.FormValue("pass")) {
		http.Error(w, "bad credentials", http.StatusUnauthorized)
	}
}


func listCapped(w http.ResponseWriter, r *http.Request) { // @@T decoy rate_limit page size clamped to 100 so one call cannot pull the table
	n, _ := strconv.Atoi(r.URL.Query().Get("limit"))
	if n < 1 || n > 100 {
		n = 100
	}
	json.NewEncoder(w).Encode(map[string]int{"limit": n})
}


func changeEmail(w http.ResponseWriter, r *http.Request) {
	c, err := r.Cookie("sid")
	if err != nil {
		http.Error(w, "login", http.StatusUnauthorized)
		return
	}
	_ = r.FormValue("email") // @@T positive csrf cookie-session state change with no anti-forgery token
	w.Write([]byte("updated " + sha(c.Value)))
}


func closeAccount(w http.ResponseWriter, r *http.Request) {
	if _, err := r.Cookie("sid"); err != nil {
		http.Error(w, "login", http.StatusUnauthorized)
		return
	}
	w.Write([]byte("closed")) // @@T positive csrf cookie-session delete reachable from a cross-site form post
}


// --
// --
func changePhone(w http.ResponseWriter, r *http.Request) {
	c, err := r.Cookie("csrf")
	if err != nil || r.Header.Get("X-CSRF-Token") != c.Value { // @@T decoy csrf double-submit token compared before the state change
		http.Error(w, "csrf", http.StatusForbidden)
		return
	}
	w.Write([]byte("updated"))
}


func rotateKey(w http.ResponseWriter, r *http.Request) {
	if r.Header.Get("Origin") != "https://depot.example.com" { // @@T decoy csrf Origin header must match the site before the state change
		http.Error(w, "origin", http.StatusForbidden)
		return
	}
	w.Write([]byte("rotated"))
}


func startSession(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{Name: "sid", Value: sha(r.RemoteAddr), Path: "/"}) // @@T positive cookie_flags session cookie without Secure HttpOnly or SameSite
}


func startAdminSession(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{Name: "admin_sid", Value: sha(r.UserAgent()), Path: "/admin", HttpOnly: true}) // @@T positive cookie_flags HttpOnly set but Secure and SameSite missing
}


// --
// --
// --
func startSecureSession(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{Name: "sid", Value: sha(r.RemoteAddr), Path: "/", Secure: true, HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: 3600}) // @@T decoy cookie_flags Secure HttpOnly and SameSite all set
}


func clearSession(w http.ResponseWriter, r *http.Request) {
	http.SetCookie(w, &http.Cookie{Name: "sid", Value: "", Path: "/", MaxAge: -1, Secure: true, HttpOnly: true, SameSite: http.SameSiteLaxMode}) // @@T decoy cookie_flags logout expiry cookie carries every flag and no value
}


// --
// --
// --
func signup(w http.ResponseWriter, r *http.Request) {
	log.Printf("signup email=%s ssn=%s", r.FormValue("email"), r.FormValue("ssn")) // @@T positive pii_log raw email and national id written to the log
	w.WriteHeader(http.StatusCreated)
}


func payCard(w http.ResponseWriter, r *http.Request) {
	log.Printf("charging card %s for %s", r.FormValue("card"), r.FormValue("name")) // @@T positive pii_log full card number and holder name logged
	w.WriteHeader(http.StatusAccepted)
}


// --
// --
func signupHashed(w http.ResponseWriter, r *http.Request) {
	log.Printf("signup user=%s", sha(r.FormValue("email"))) // @@T decoy pii_log only a truncated hash of the email is logged
	w.WriteHeader(http.StatusCreated)
}


func payMasked(w http.ResponseWriter, r *http.Request) {
	card := r.FormValue("card")
	if len(card) >= 4 {
		log.Printf("charging card ending %s", card[len(card)-4:]) // @@T decoy pii_log only the last four digits are logged
	}
	w.WriteHeader(http.StatusAccepted)
}


// --
var seedCustomers = []map[string]string{
	{"name": "Jane Smith", "email": "jane.smith@example.com", "ssn": "912-44-7731", "dob": "1988-03-14"}, // @@T positive pii_data committed seed holds a plaintext national id and date of birth
	{"name": "John Doe", "email": "john.doe@example.com", "ssn": "914-21-9008", "dob": "1979-11-02"},
}

func devSeed(w http.ResponseWriter, r *http.Request) { json.NewEncoder(w).Encode(seedCustomers) }


func trackOrder(w http.ResponseWriter, r *http.Request) {
	payload, _ := json.Marshal(map[string]string{"event": "order", "email": r.FormValue("email"), "phone": r.FormValue("phone")}) // @@T positive pii_data raw email and phone sent to a third-party analytics endpoint
	llmClient.Post("https://analytics.vendor.example.com/collect", "application/json", bytes.NewReader(payload))
}


// --
// --
var seedRefs = []map[string]string{
	{"customer_ref": "cus_7f3a", "region": "EU", "vault_ref": "vault://pii/7f3a"}, // @@T decoy pii_data fixture carries opaque references only and the PII stays in the vault
	{"customer_ref": "cus_91bc", "region": "US", "vault_ref": "vault://pii/91bc"},
}

func devRefs(w http.ResponseWriter, r *http.Request) { json.NewEncoder(w).Encode(seedRefs) }


func trackOrderHashed(w http.ResponseWriter, r *http.Request) {
	payload, _ := json.Marshal(map[string]string{"event": "order", "user": sha(r.FormValue("email"))}) // @@T decoy pii_data analytics payload holds a truncated hash and no direct identifier
	llmClient.Post("https://analytics.vendor.example.com/collect", "application/json", bytes.NewReader(payload))
}


// --
func summarizeNote(w http.ResponseWriter, r *http.Request) {
	note := r.FormValue("note")
	w.Write([]byte(askLLM("You may approve refunds. Customer note: "+note, "summarize"))) // @@T positive prompt_injection request text spliced into the system prompt of a model that can approve refunds
}


func lookupTool(w http.ResponseWriter, r *http.Request) {
	args := `{"name":"lookup","arguments":{"sku":"` + r.FormValue("sku") + `"}}` // @@T positive prompt_injection request value concatenated into raw tool-call JSON
	llmClient.Post("https://llm.vendor.example.com/v1/tools", "application/json", bytes.NewReader([]byte(args)))
}


var topics = map[string]string{"stock": "Explain stock levels.", "returns": "Explain the returns policy."}

func explainTopic(w http.ResponseWriter, r *http.Request) {
	prompt, ok := topics[r.FormValue("topic")]
	if !ok {
		http.Error(w, "unknown topic", http.StatusBadRequest)
		return
	}
	w.Write([]byte(askLLM("Answer briefly.", prompt))) // @@T decoy prompt_injection caller picks from a fixed allowlist and never supplies prompt text
}


func lookupToolSafe(w http.ResponseWriter, r *http.Request) {
	args, _ := json.Marshal(map[string]any{"name": "lookup", "arguments": map[string]string{"sku": r.FormValue("sku")}}) // @@T decoy prompt_injection tool name is fixed and the argument is JSON-encoded as data
	llmClient.Post("https://llm.vendor.example.com/v1/tools", "application/json", bytes.NewReader(args))
}

func registerExtras(mux *http.ServeMux) {
	mux.HandleFunc("GET /api/ext/export/all", exportAll) // @@R GET /api/ext/export/all 1
	mux.HandleFunc("POST /api/ext/upload", uploadBlob) // @@R POST /api/ext/upload 1
	mux.HandleFunc("POST /auth/login", loginLimited) // @@R POST /auth/login 0 public
	mux.HandleFunc("GET /api/ext/items", listCapped) // @@R GET /api/ext/items 1
	mux.HandleFunc("POST /web/ext/account/email", requireCookie(changeEmail)) // @@R POST /web/ext/account/email 1
	mux.HandleFunc("POST /web/ext/account/close", requireCookie(closeAccount)) // @@R POST /web/ext/account/close 1
	mux.HandleFunc("POST /web/ext/account/phone", requireCookie(changePhone)) // @@R POST /web/ext/account/phone 1
	mux.HandleFunc("POST /web/ext/account/key", requireCookie(rotateKey)) // @@R POST /web/ext/account/key 1
	mux.HandleFunc("GET /web/ext/session/start", requireCookie(startSession)) // @@R GET /web/ext/session/start 1
	mux.HandleFunc("GET /web/ext/session/admin", requireCookie(startAdminSession)) // @@R GET /web/ext/session/admin 1
	mux.HandleFunc("GET /web/ext/session/secure", requireCookie(startSecureSession)) // @@R GET /web/ext/session/secure 1
	mux.HandleFunc("GET /web/ext/session/clear", requireCookie(clearSession)) // @@R GET /web/ext/session/clear 1
	mux.HandleFunc("POST /auth/signup", signup) // @@R POST /auth/signup 0 public
	mux.HandleFunc("POST /api/ext/pay", payCard) // @@R POST /api/ext/pay 1
	mux.HandleFunc("POST /auth/signup2", signupHashed) // @@R POST /auth/signup2 0 public
	mux.HandleFunc("POST /api/ext/pay2", payMasked) // @@R POST /api/ext/pay2 1
	mux.HandleFunc("GET /api/ext/dev/seed", devSeed) // @@R GET /api/ext/dev/seed 1
	mux.HandleFunc("POST /api/ext/track/order", trackOrder) // @@R POST /api/ext/track/order 1
	mux.HandleFunc("GET /api/ext/dev/refs", devRefs) // @@R GET /api/ext/dev/refs 1
	mux.HandleFunc("POST /api/ext/track/order2", trackOrderHashed) // @@R POST /api/ext/track/order2 1
	mux.HandleFunc("POST /api/ext/ai/note", summarizeNote) // @@R POST /api/ext/ai/note 1
	mux.HandleFunc("POST /api/ext/ai/lookup", lookupTool) // @@R POST /api/ext/ai/lookup 1
	mux.HandleFunc("POST /api/ext/ai/explain", explainTopic) // @@R POST /api/ext/ai/explain 1
	mux.HandleFunc("POST /api/ext/ai/lookup2", lookupToolSafe) // @@R POST /api/ext/ai/lookup2 1
}
