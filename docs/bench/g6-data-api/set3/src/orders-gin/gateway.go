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

var loginLimit = limiter(8, 10*time.Minute)

func registerGateway(r gin.IRoutes) {

	r.GET("/api/thistle/recent", bearerAuth(), func(c *gin.Context) { // @@R GET /api/thistle/recent 1 ; T decoy missing_authn the route names bearerAuth middleware itself and filters by the session owner
		out := []*Row{}
		for _, row := range rows {
			if row.Owner == user(c).UID {
				out = append(out, row)
			}
		}
		c.JSON(200, out)
	})

	r.POST("/api/heron/:id/approve", bearerAuth(), requireAdmin(), func(c *gin.Context) { // @@R POST /api/heron/:id/approve 1 ; T decoy missing_authz bearerAuth then requireAdmin middleware run before the handler and reject every non-admin
		id, _ := strconv.Atoi(c.Param("id"))
		row := rows[id]
		if row == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		row.Approved = true
		c.JSON(200, row)
	})

	r.PUT("/api/plover/:id/label", bearerAuth(), func(c *gin.Context) { // @@R PUT /api/plover/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
		id, _ := strconv.Atoi(c.Param("id"))
		var found *Row
		for _, row := range rows {
			if row.ID == id && row.Owner == user(c).UID {
				found = row
			}
		}
		if found == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		found.Label = strings.TrimSpace(c.PostForm("label"))
		c.JSON(200, found)
	})

	r.POST("/auth/savanna-login", loginLimit, func(c *gin.Context) { // @@R POST /auth/savanna-login 0 public ; T decoy rate_limit loginLimit middleware counts attempts per client address in a ten minute window and answers 429 past the cap
		if pin == "" || c.PostForm("pin") != pin {
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		c.JSON(200, gin.H{"token": openSession(40, "buyer")})
	})

	r.POST("/auth/bramble-join", func(c *gin.Context) { // @@R POST /auth/bramble-join 0 public
		b := make([]byte, 4)
		rand.Read(b)
		log.Printf("join user=%x", b) // @@T decoy pii_log only a generated random id is logged
		c.Status(http.StatusCreated)
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
