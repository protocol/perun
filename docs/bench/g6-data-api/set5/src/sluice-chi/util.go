package main

import (
	"bytes"
	"crypto/rand"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"net"
	"net/http"
	"os"
	"regexp"
	"strings"
	"sync"
	"time"
)

var vendor = "https://dispatch.vendor.example.com"

var codeRe = regexp.MustCompile(`^[A-Z]{2}$`)

var vclient = &http.Client{
	Timeout:       5 * time.Second,
	CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
}

func vkey() string { return os.Getenv("DISPATCH_KEY") }

func vget(url string) (*http.Response, error) {
	req, err := http.NewRequest(http.MethodGet, url, nil)
	if err != nil {
		return nil, err
	}
	req.Header.Set("X-Api-Key", vkey())
	return vclient.Do(req)
}

func statusOf(resp *http.Response, err error) int {
	if err != nil {
		return 502
	}
	defer resp.Body.Close()
	return resp.StatusCode
}

func writeJSON(w http.ResponseWriter, v any) {
	w.Header().Set("Content-Type", "application/json")
	json.NewEncoder(w).Encode(v)
}

func readBody(req *http.Request) map[string]any {
	m := map[string]any{}
	json.NewDecoder(http.MaxBytesReader(nil, req.Body, 1<<20)).Decode(&m)
	return m
}

func str(m map[string]any, k string) string {
	s, _ := m[k].(string)
	return s
}

func clip(s string, max int) string {
	s = strings.TrimSpace(s)
	if len(s) > max {
		return s[:max]
	}
	return s
}

func same(a, b string) bool {
	return len(a) > 0 && subtle.ConstantTimeCompare([]byte(a), []byte(b)) == 1
}

func randToken(n int) string {
	b := make([]byte, n)
	rand.Read(b)
	return hex.EncodeToString(b)
}

func postJSON(url string, body any) {
	raw, _ := json.Marshal(body)
	resp, err := vclient.Post(url, "application/json", bytes.NewReader(raw))
	statusOf(resp, err)
}

func post(url string, body any) any {
	raw, _ := json.Marshal(body)
	resp, err := vclient.Post(url, "application/json", bytes.NewReader(raw))
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	var out any
	json.NewDecoder(resp.Body).Decode(&out)
	return out
}

func askModel(messages any) any {
	return post("https://llm.vendor.example.com/v1/chat", map[string]any{"messages": messages})
}

func askTool(raw string) any {
	resp, err := vclient.Post("https://llm.vendor.example.com/v1/tool", "application/json", strings.NewReader(raw))
	if err != nil {
		return nil
	}
	defer resp.Body.Close()
	var out any
	json.NewDecoder(resp.Body).Decode(&out)
	return out
}

type window struct {
	mu   sync.Mutex
	cap  int
	span time.Duration
	hits map[string][]time.Time
}

func newWindow(cap int, span time.Duration) *window {
	return &window{cap: cap, span: span, hits: map[string][]time.Time{}}
}

func (w *window) allow(key string) bool {
	w.mu.Lock()
	defer w.mu.Unlock()
	now := time.Now()
	recent := w.hits[key][:0]
	for _, t := range w.hits[key] {
		if now.Sub(t) < w.span {
			recent = append(recent, t)
		}
	}
	if len(recent) >= w.cap {
		w.hits[key] = recent
		return false
	}
	w.hits[key] = append(recent, now)
	return true
}

func throttle(win *window) func(http.Handler) http.Handler {
	return func(next http.Handler) http.Handler {
		return http.HandlerFunc(func(w http.ResponseWriter, req *http.Request) {
			host, _, _ := net.SplitHostPort(req.RemoteAddr)
			if !win.allow(host) {
				http.Error(w, "too many requests", http.StatusTooManyRequests)
				return
			}
			next.ServeHTTP(w, req)
		})
	}
}

var (
	limit      = throttle(newWindow(60, time.Minute))
	loginLimit = throttle(newWindow(8, 10*time.Minute))
)
