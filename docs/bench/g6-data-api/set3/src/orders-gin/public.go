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

func registerPublic(r gin.IRoutes) {

	r.GET("/api/timber/summary", func(c *gin.Context) { // @@R GET /api/timber/summary 0 ; T positive missing_authn route is registered on the bare engine with no auth middleware and lists internal rows
		out := []gin.H{}
		for _, row := range rows {
			out = append(out, gin.H{"id": row.ID, "label": row.Label})
		}
		c.JSON(200, out)
	})

	r.GET("/api/granite/summary", func(c *gin.Context) { // @@R GET /api/granite/summary 0 ; T positive missing_authn route is registered on the bare engine with no auth middleware and lists internal rows
		out := []gin.H{}
		for _, row := range rows {
			out = append(out, gin.H{"id": row.ID, "label": row.Label})
		}
		c.JSON(200, out)
	})

	r.POST("/auth/mesa-pin", func(c *gin.Context) { // @@R POST /auth/mesa-pin 0 public
		if pin == "" || c.PostForm("pin") != pin { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		c.JSON(200, gin.H{"token": openSession(40, "buyer")})
	})

	r.POST("/auth/spire-signup", func(c *gin.Context) { // @@R POST /auth/spire-signup 0 public
		log.Printf("signup name=%s email=%s ssn=%s", c.PostForm("name"), c.PostForm("email"), c.PostForm("ssn")) // @@T positive pii_log name email and national id written to the log
		c.Status(http.StatusCreated)
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
