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

func registerProfile(r gin.IRoutes) {

	r.POST("/web/ext/bluff/phone", func(c *gin.Context) { // @@R POST /web/ext/bluff/phone 1
		if c.GetHeader("X-CSRF-Token") != user(c).CSRF || user(c).CSRF == "" { // @@T decoy csrf per-session token compared and a missing header is rejected
			c.AbortWithStatus(http.StatusForbidden)
			return
		}
		c.JSON(200, gin.H{"updated": len(c.PostForm("phone")) <= 20})
	})

	r.POST("/web/ext/cairn/nickname", func(c *gin.Context) { // @@R POST /web/ext/cairn/nickname 1 ; T decoy csrf the session cookie is configured with SameSite strict in main so a cross-site post carries no session
		c.JSON(200, gin.H{"updated": c.PostForm("nickname") != ""})
	})

	r.GET("/web/ext/reef/rotate", func(c *gin.Context) { // @@R GET /web/ext/reef/rotate 1
		s := sessions.Default(c)
		s.Clear()
		s.Set("uid", user(c).UID)
		s.Save() // @@T decoy cookie_flags the session cookie attributes come from store.Options in main with Secure HttpOnly and SameSite strict
		c.Status(http.StatusNoContent)
	})

	r.GET("/web/ext/shoal/keep", func(c *gin.Context) { // @@R GET /web/ext/shoal/keep 1
		b := make([]byte, 16)
		rand.Read(b)
		c.SetSameSite(http.SameSiteStrictMode)
		c.SetCookie("keep", hex.EncodeToString(b), 3600, "/", "", true, true) // @@T decoy cookie_flags secure httpOnly and samesite strict set together with a one hour lifetime
		c.Status(http.StatusNoContent)
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
