package main

import (
	"bytes"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/json"
	"io"
	"net"
	"net/http"
	"sync"
	"time"
)

type msg struct {
	Role    string `json:"role"`
	Content string `json:"content"`
}

var modelClient = &http.Client{Timeout: 15 * time.Second}

func chat(msgs []msg) string {
	body, _ := json.Marshal(map[string]any{"messages": msgs})
	resp, err := modelClient.Post("https://llm.vendor.example.com/v1/chat", "application/json", bytes.NewReader(body))
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	return string(out)
}

func same(a, b string) bool {
	x, y := sha256.Sum256([]byte(a)), sha256.Sum256([]byte(b))
	return subtle.ConstantTimeCompare(x[:], y[:]) == 1
}

type window struct {
	mu    sync.Mutex
	hits  map[string][]time.Time
	swept time.Time
}

func newWindow() *window { return &window{hits: map[string][]time.Time{}, swept: time.Now()} }

func (w *window) allow(key string, max int, span time.Duration) bool {
	now := time.Now()
	w.mu.Lock()
	defer w.mu.Unlock()
	if now.Sub(w.swept) > span {
		for k, ts := range w.hits {
			if now.Sub(ts[len(ts)-1]) >= span {
				delete(w.hits, k)
			}
		}
		w.swept = now
	}
	kept := w.hits[key][:0]
	for _, t := range w.hits[key] {
		if now.Sub(t) < span {
			kept = append(kept, t)
		}
	}
	if len(kept) >= max {
		w.hits[key] = kept
		return false
	}
	w.hits[key] = append(kept, now)
	return true
}

func clientIP(r *http.Request) string {
	host, _, err := net.SplitHostPort(r.RemoteAddr)
	if err != nil {
		return r.RemoteAddr
	}
	return host
}
