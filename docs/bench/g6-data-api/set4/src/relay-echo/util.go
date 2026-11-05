package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"os"
	"strings"
	"sync"
	"time"

	"github.com/labstack/echo/v4"
)

const vendor = "https://dispatch.vendor.example.com"

var (
	vendorKey = os.Getenv("DISPATCH_KEY")
	pin       = os.Getenv("RELAY_PIN")
	httpc    = &http.Client{Timeout: 5 * time.Second}
)

// window is a sliding window per client address.
type window struct {
	cap  int
	span time.Duration
	mu   sync.Mutex
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

func throttle(w *window) echo.MiddlewareFunc {
	return func(next echo.HandlerFunc) echo.HandlerFunc {
		return func(c echo.Context) error {
			if !w.allow(c.RealIP()) {
				return c.JSON(http.StatusTooManyRequests, map[string]string{"error": "too many requests"})
			}
			return next(c)
		}
	}
}

func body(c echo.Context) map[string]any {
	m := map[string]any{}
	_ = json.NewDecoder(c.Request().Body).Decode(&m)
	return m
}

func str(v any) string {
	s, _ := v.(string)
	return s
}

func clip(s string, n int) string {
	if len(s) > n {
		return s[:n]
	}
	return s
}

func post(url, ctype string, payload []byte) (string, error) {
	resp, err := (&http.Client{Timeout: 15 * time.Second}).Post(url, ctype, bytes.NewReader(payload))
	if err != nil {
		return "", err
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return strings.TrimSpace(string(out)), nil
}

func askModel(messages []map[string]string) string {
	payload, _ := json.Marshal(map[string]any{"messages": messages})
	out, _ := post("https://llm.vendor.example.com/v1/chat", "application/json", payload)
	return out
}

func askTool(raw string) string {
	out, _ := post("https://llm.vendor.example.com/v1/tool", "application/json", []byte(raw))
	return out
}
