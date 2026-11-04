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

func registerPartners(r gin.IRoutes) {

	r.POST("/api/ext/sparrow/push", func(c *gin.Context) { // @@R POST /api/ext/sparrow/push 1
		client := &http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}} // @@T positive tls_off certificate verification disabled for the vendor request
		req, _ := http.NewRequest("POST", vendor+"/v1/sparrow", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := client.Do(req)
		relay(c, resp, err)
	})

	r.GET("/api/ext/tundra/fetch", func(c *gin.Context) { // @@R GET /api/ext/tundra/fetch 1
		resp, err := httpClient.Get(c.Query("url")) // @@T positive ssrf caller-supplied URL fetched from the server
		relay(c, resp, err)
	})

	r.GET("/api/ext/canyon/status", func(c *gin.Context) { // @@R GET /api/ext/canyon/status 1
		req, _ := http.NewRequest("GET", vendor+"/v1/canyon/status", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := http.DefaultClient.Do(req) // @@T positive no_timeout default client has no timeout so a slow vendor holds the request open
		relay(c, resp, err)
	})

	r.GET("/api/ext/glacier/lookup", func(c *gin.Context) { // @@R GET /api/ext/glacier/lookup 1
		resp, err := httpClient.Get(vendor + "/v1/glacier?key=" + vendorKey) // @@T positive secret_in_url vendor key sent as a query parameter
		relay(c, resp, err)
	})

	r.GET("/api/ext/summit/ping", func(c *gin.Context) { // @@R GET /api/ext/summit/ping 1
		log.Printf("vendor ping key=%s", vendorKey) // @@T positive secret_in_log vendor key written to the application log
		req, _ := http.NewRequest("GET", vendor+"/v1/ping", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := httpClient.Do(req)
		relay(c, resp, err)
	})

	r.GET("/api/ext/valley/status", func(c *gin.Context) { // @@R GET /api/ext/valley/status 1
		req, _ := http.NewRequest("GET", vendor+"/v1/valley/status", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := http.DefaultClient.Do(req) // @@T positive no_timeout default client has no timeout so a slow vendor holds the request open
		relay(c, resp, err)
	})

	r.GET("/api/ext/prairie/export", func(c *gin.Context) { // @@R GET /api/ext/prairie/export 1
		out := make([]gin.H, 0, 100000)
		for i := 0; i < 100000; i++ { // @@T positive rate_limit full export rebuilt on every call with no throttle
			out = append(out, gin.H{"i": i, "label": fmt.Sprintf("prairie-%d", i)})
		}
		c.JSON(200, out)
	})

	r.POST("/api/ext/arbor/charge", func(c *gin.Context) { // @@R POST /api/ext/arbor/charge 1
		log.Printf("charge card=%s holder=%s", c.PostForm("card"), c.PostForm("holder")) // @@T positive pii_log full card number and holder name logged
		c.JSON(200, gin.H{"ok": true})
	})

	seedfennel := []map[string]string{{"name": "Jane Smith", "email": "jane@example.com", "ssn": "912-55-0147", "dob": "1984-03-09"}} // @@T positive pii_data seed staff list holds a plaintext national id and birth date
	r.GET("/api/ext/fennel/sample", func(c *gin.Context) { // @@R GET /api/ext/fennel/sample 1
		c.JSON(200, gin.H{"count": len(seedfennel)})
	})

	r.POST("/api/ext/hazel/track", func(c *gin.Context) { // @@R POST /api/ext/hazel/track 1
		postJSON("https://stats.vendor.example.com/v1/event", gin.H{"event": "view", "email": user(c).Email, "phone": user(c).Phone}) // @@T positive pii_data raw email and phone sent to a third-party analytics host
		c.Status(http.StatusNoContent)
	})

	seedlaurel := []map[string]string{{"name": "Jane Smith", "email": "jane@example.com", "ssn": "912-55-0147", "dob": "1984-03-09"}} // @@T positive pii_data seed staff list holds a plaintext national id and birth date
	r.GET("/api/ext/laurel/sample", func(c *gin.Context) { // @@R GET /api/ext/laurel/sample 1
		c.JSON(200, gin.H{"count": len(seedlaurel)})
	})

	r.POST("/api/ext/olive/assist", func(c *gin.Context) { // @@R POST /api/ext/olive/assist 1
		reply := askModel([]map[string]string{{"role": "system", "content": fmt.Sprintf("You are the orders assistant and may approve refunds. Operator note: %s", c.PostForm("note"))}}) // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
		c.JSON(200, gin.H{"reply": reply})
	})

	r.POST("/api/ext/poppy/lookup-tool", func(c *gin.Context) { // @@R POST /api/ext/poppy/lookup-tool 1
		reply := askTool(fmt.Sprintf(`{"tool": "lookup", "arg": "%s"}`, c.PostForm("arg"))) // @@T positive prompt_injection request value formatted into raw tool-call JSON
		c.JSON(200, gin.H{"reply": reply})
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
