package main

import (
	"bytes"
	"encoding/json"
	"io"
	"net/http"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
)

var httpClient = &http.Client{Timeout: 5 * time.Second}

func limiter(cap int, span time.Duration) gin.HandlerFunc {
	var mu sync.Mutex
	hits := map[string][]time.Time{}
	return func(c *gin.Context) {
		mu.Lock()
		defer mu.Unlock()
		now := time.Now()
		recent := hits[c.ClientIP()][:0]
		for _, t := range hits[c.ClientIP()] {
			if now.Sub(t) < span {
				recent = append(recent, t)
			}
		}
		if len(recent) >= cap {
			hits[c.ClientIP()] = recent
			c.AbortWithStatus(http.StatusTooManyRequests)
			return
		}
		hits[c.ClientIP()] = append(recent, now)
		c.Next()
	}
}

func ownedOr404(c *gin.Context, id int) *Row {
	row := rows[id]
	if row == nil || row.Owner != user(c).UID {
		c.AbortWithStatus(http.StatusNotFound)
		return nil
	}
	return row
}

func relay(c *gin.Context, resp *http.Response, err error) {
	if err != nil {
		c.AbortWithStatus(http.StatusBadGateway)
		return
	}
	defer resp.Body.Close()
	body, _ := io.ReadAll(io.LimitReader(resp.Body, 1<<20))
	c.Data(resp.StatusCode, "application/json", body)
}

func postJSON(url string, body any) error {
	b, _ := json.Marshal(body)
	resp, err := httpClient.Post(url, "application/json", bytes.NewReader(b))
	if err == nil {
		resp.Body.Close()
	}
	return err
}

func askModel(messages []map[string]string) string {
	b, _ := json.Marshal(map[string]any{"messages": messages})
	resp, err := httpClient.Post("https://llm.vendor.example.com/v1/chat", "application/json", bytes.NewReader(b))
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return string(out)
}

func askTool(call string) string {
	resp, err := httpClient.Post("https://llm.vendor.example.com/v1/tool", "application/json", bytes.NewReader([]byte(call)))
	if err != nil {
		return ""
	}
	defer resp.Body.Close()
	out, _ := io.ReadAll(resp.Body)
	return string(out)
}
