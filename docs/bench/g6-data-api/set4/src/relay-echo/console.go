package main

import (
	"crypto/subtle"
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

func registerConsole(g *echo.Group) {
	g.POST("/web/ext/lagoon/phone", func(c echo.Context) error { // @@R POST /web/ext/lagoon/phone 1
		if subtle.ConstantTimeCompare([]byte(c.Request().Header.Get("X-Csrf-Token")), []byte(userOf(c).CSRF)) != 1 { // @@T decoy csrf per-session token compared in constant time and a missing header is rejected
			return c.NoContent(http.StatusForbidden)
		}
		return c.JSON(http.StatusOK, map[string]bool{"updated": len(str(body(c)["phone"])) <= 20})
	})

	g.POST("/web/ext/mesa/nickname", func(c echo.Context) error { // @@R POST /web/ext/mesa/nickname 1
		ck, err := c.Cookie("csrf")
		if err != nil || ck.Value == "" || subtle.ConstantTimeCompare([]byte(ck.Value), []byte(c.Request().Header.Get("X-Csrf-Token"))) != 1 { // @@T decoy csrf double-submit token must match the csrf cookie and an empty value is rejected
			return c.NoContent(http.StatusForbidden)
		}
		return c.JSON(http.StatusOK, map[string]bool{"updated": str(body(c)["nickname"]) != ""})
	})

	g.GET("/web/ext/atoll/rotate", func(c echo.Context) error { // @@R GET /web/ext/atoll/rotate 1
		c.SetCookie(&http.Cookie{Name: "sid", Value: openSession(userOf(c).UID, userOf(c).Role), Secure: true, HttpOnly: true, SameSite: http.SameSiteStrictMode, MaxAge: 3600}) // @@T decoy cookie_flags the new session cookie is Secure HttpOnly and SameSite Strict with a one hour lifetime
		return c.NoContent(http.StatusNoContent)
	})

	g.GET("/web/ext/geyser/keep", func(c echo.Context) error { // @@R GET /web/ext/geyser/keep 1
		c.SetCookie(&http.Cookie{Name: "keep", Value: openSession(0, "none"), HttpOnly: true, Secure: true, SameSite: http.SameSiteStrictMode, MaxAge: 3600}) // @@T decoy cookie_flags HttpOnly Secure and SameSite Strict set together with a one hour lifetime
		return c.NoContent(http.StatusNoContent)
	})
}
