package main

import (
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gin-contrib/sessions"
)

var (
	vendor    = "https://dispatch.vendor.example.com"
	vendorKey = os.Getenv("DISPATCH_KEY")
	pin       = os.Getenv("ORDERS_PIN")
)

var exportLimit = limiter(5, time.Minute)

func registerIntegrations(r gin.IRoutes) {

	r.GET("/api/ext/ridge/:id/image", func(c *gin.Context) { // @@R GET /api/ext/ridge/:id/image 1
		id, err := strconv.Atoi(c.Param("id"))
		if err != nil {
			c.AbortWithStatus(http.StatusBadRequest)
			return
		}
		noRedirect := &http.Client{Timeout: 5 * time.Second, CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse }}
		resp, err := noRedirect.Get("https://img.vendor.example.com/p/" + strconv.Itoa(id) + ".jpg") // @@T decoy ssrf host fixed in code and the caller supplies only an integer id with redirects off
		relay(c, resp, err)
	})

	r.GET("/api/ext/delta/:code/rates", func(c *gin.Context) { // @@R GET /api/ext/delta/:code/rates 1
		code := c.Param("code")
		if len(code) != 2 {
			c.AbortWithStatus(http.StatusBadRequest)
			return
		}
		req, _ := http.NewRequest("GET", vendor+"/v1/rates/"+code, nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := httpClient.Do(req) // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
		relay(c, resp, err)
	})

	r.GET("/api/ext/lagoon/:code/stock", func(c *gin.Context) { // @@R GET /api/ext/lagoon/:code/stock 1
		code := c.Param("code")
		if len(code) != 2 {
			c.AbortWithStatus(http.StatusBadRequest)
			return
		}
		req, _ := http.NewRequest("GET", vendor+"/v1/stock/"+code, nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := httpClient.Do(req)
		if err == nil {
			log.Printf("stock lookup code=%s status=%d", code, resp.StatusCode) // @@T decoy secret_in_log only the status and the validated code are logged
		}
		relay(c, resp, err)
	})

	r.GET("/api/ext/fjord/export", exportLimit, func(c *gin.Context) { // @@R GET /api/ext/fjord/export 1 ; T decoy rate_limit exportLimit middleware caps the export at five calls a minute per client address
		out := make([]gin.H, 0, 100000)
		for i := 0; i < 100000; i++ {
			out = append(out, gin.H{"i": i, "label": fmt.Sprintf("fjord-%d", i)})
		}
		c.JSON(200, out)
	})

	r.POST("/api/ext/clover/rotate-key", func(c *gin.Context) { // @@R POST /api/ext/clover/rotate-key 1
		b := make([]byte, 8)
		rand.Read(b)
		keyID := hex.EncodeToString(b)
		log.Printf("rotate user=%d domain=%s key_id=%s", user(c).UID, strings.Split(user(c).Email, "@")[1], keyID[:6]) // @@T decoy pii_log the log line carries the numeric user id the email domain and a six character key id and no address or key
		c.JSON(200, gin.H{"keyId": keyID})
	})

	r.POST("/api/ext/maple/track", func(c *gin.Context) { // @@R POST /api/ext/maple/track 1
		postJSON("https://stats.vendor.example.com/v1/event", gin.H{"event": "view", "uid": user(c).UID}) // @@T decoy pii_data analytics payload carries the internal numeric id and no direct identifier
		c.Status(http.StatusNoContent)
	})

	seednettle := []map[string]any{{"label": "Sample order", "region": "north", "count": 3}} // @@T decoy pii_data seed rows hold labels and counts and no person
	r.GET("/api/ext/nettle/sample", func(c *gin.Context) { // @@R GET /api/ext/nettle/sample 1
		c.JSON(200, gin.H{"count": len(seednettle)})
	})

	r.POST("/api/ext/quince/assist", func(c *gin.Context) { // @@R POST /api/ext/quince/assist 1
		note := c.PostForm("note")
		if len(note) > 500 {
			note = note[:500]
		}
		reply := askModel([]map[string]string{{"role": "system", "content": "You summarise order notes and have no tools."}, {"role": "user", "content": note}}) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
		c.JSON(200, gin.H{"reply": reply})
	})

	r.POST("/api/ext/rowan/lookup-tool", func(c *gin.Context) { // @@R POST /api/ext/rowan/lookup-tool 1
		call, _ := json.Marshal(map[string]string{"tool": "lookup", "arg": c.PostForm("sku")})
		reply := askTool(string(call)) // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
		c.JSON(200, gin.H{"reply": reply})
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
