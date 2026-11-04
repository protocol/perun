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

func registerAccount(r gin.IRoutes) {

	r.POST("/web/ext/atoll/email", func(c *gin.Context) { // @@R POST /web/ext/atoll/email 1
		email := c.PostForm("email") // @@T positive csrf cookie-session email change accepted with no anti-forgery token
		c.JSON(200, gin.H{"updated": email != ""})
	})

	r.POST("/web/ext/geyser/close", func(c *gin.Context) { // @@R POST /web/ext/geyser/close 1
		sid, _ := c.Cookie("sid")
		delete(tokens, sid) // @@T positive csrf cookie-session account closure reachable from a cross-site form post
		c.SetCookie("sid", "", -1, "/", "", true, true)
		c.Status(http.StatusNoContent)
	})

	r.POST("/web/ext/tarn/email", func(c *gin.Context) { // @@R POST /web/ext/tarn/email 1
		email := c.PostForm("email") // @@T positive csrf cookie-session email change accepted with no anti-forgery token
		c.JSON(200, gin.H{"updated": email != ""})
	})

	r.GET("/web/ext/dune/remember", func(c *gin.Context) { // @@R GET /web/ext/dune/remember 1
		c.SetCookie("sid", openSession(user(c).UID, user(c).Role), 0, "/", "", false, false) // @@T positive cookie_flags session cookie issued with secure and httpOnly both false and no samesite
		c.Status(http.StatusNoContent)
	})

	r.GET("/web/ext/moor/trust", func(c *gin.Context) { // @@R GET /web/ext/moor/trust 1
		c.SetSameSite(http.SameSiteLaxMode)
		c.SetCookie("trust", openSession(user(c).UID, user(c).Role), 86400, "/", "", true, false) // @@T positive cookie_flags login token cookie readable from script because httpOnly is false
		c.Status(http.StatusNoContent)
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
