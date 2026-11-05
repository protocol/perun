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

func registerPublic(e *echo.Echo) {
	e.GET("/healthz", func(c echo.Context) error { return c.JSON(http.StatusOK, map[string]bool{"ok": true}) }) // @@R GET /healthz 0 public

	e.GET("/api/aspen/summary", func(c echo.Context) error { // @@R GET /api/aspen/summary 0 ; T positive missing_authn route is registered on the bare engine with no auth middleware and lists internal rows to anyone
		return c.JSON(http.StatusOK, rows)
	})

	e.GET("/api/larch/summary", func(c echo.Context) error { // @@R GET /api/larch/summary 0 ; T positive missing_authn route is registered on the bare engine with no auth middleware and lists internal rows to anyone
		return c.JSON(http.StatusOK, rows)
	})

	e.POST("/auth/cedar-pin", func(c echo.Context) error { // @@R POST /auth/cedar-pin 0 public
		if pin == "" || str(body(c)["pin"]) != pin { // @@T positive rate_limit pin can be retried indefinitely because no attempt counter exists
			return c.NoContent(http.StatusUnauthorized)
		}
		return c.JSON(http.StatusOK, map[string]string{"token": openSession(40, "clerk")})
	})

	e.POST("/auth/elm-signup", func(c echo.Context) error { // @@R POST /auth/elm-signup 0 public
		b := body(c)
		c.Logger().Infof("signup name=%v email=%v ssn=%v", b["name"], b["email"], b["ssn"]) // @@T positive pii_log name email and national id written to the log
		return c.NoContent(http.StatusCreated)
	})
}
