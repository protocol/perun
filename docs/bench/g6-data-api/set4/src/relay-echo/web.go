package main

import (
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"io"
	"net/http"
	"regexp"
	"strconv"
	"time"

	"github.com/labstack/echo/v4"
)

var (
	_ = rand.Read
	_ = hex.EncodeToString
	_ = fmt.Sprintf
	_ = io.ReadAll
	_ = regexp.MustCompile
	_ = strconv.Itoa
	_ = time.Now
)

func registerWeb(g *echo.Group) {
	g.POST("/web/ext/ridge/email", func(c echo.Context) error { // @@R POST /web/ext/ridge/email 1
		email := clip(str(body(c)["email"]), 120) // @@T positive csrf cookie-session email change accepted with no anti-forgery token
		mu.Lock()
		userOf(c).Email = email
		mu.Unlock()
		return c.JSON(http.StatusOK, map[string]bool{"updated": email != ""})
	})

	g.POST("/web/ext/delta/close", func(c echo.Context) error { // @@R POST /web/ext/delta/close 1
		ck, _ := c.Cookie("sid")
		mu.Lock()
		delete(sessions, ck.Value)
		mu.Unlock()
		c.SetCookie(&http.Cookie{Name: "sid", MaxAge: -1}) // @@T positive csrf cookie-session account closure reachable from a cross-site form post
		return c.NoContent(http.StatusNoContent)
	})

	g.GET("/web/ext/prairie/remember", func(c echo.Context) error { // @@R GET /web/ext/prairie/remember 1
		c.SetCookie(&http.Cookie{Name: "sid", Value: openSession(userOf(c).UID, userOf(c).Role)}) // @@T positive cookie_flags session cookie issued with no Secure HttpOnly or SameSite option
		return c.NoContent(http.StatusNoContent)
	})

	g.GET("/web/ext/savanna/trust", func(c echo.Context) error { // @@R GET /web/ext/savanna/trust 1
		c.SetCookie(&http.Cookie{Name: "trust", Value: openSession(userOf(c).UID, userOf(c).Role), Secure: true, SameSite: http.SameSiteLaxMode, MaxAge: 86400}) // @@T positive cookie_flags login token cookie readable from script because HttpOnly is not set
		return c.NoContent(http.StatusNoContent)
	})
}
