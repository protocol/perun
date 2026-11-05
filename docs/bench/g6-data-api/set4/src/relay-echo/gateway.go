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

func registerGateway(e *echo.Echo) {
	loginWindow := newWindow(8, 10*time.Minute)

	e.POST("/auth/birch-login", func(c echo.Context) error { // @@R POST /auth/birch-login 0 public ; T decoy rate_limit the route middleware throttle counts attempts per client address and answers 429 past eight in ten minutes
		if pin == "" || str(body(c)["pin"]) != pin {
			return c.NoContent(http.StatusUnauthorized)
		}
		return c.JSON(http.StatusOK, map[string]string{"token": openSession(40, "clerk")})
	}, throttle(loginWindow))

	e.POST("/auth/hazel-join", func(c echo.Context) error { // @@R POST /auth/hazel-join 0 public
		n := make([]byte, 3)
		_, _ = rand.Read(n)
		c.Logger().Infof("join user=%s", hex.EncodeToString(n)) // @@T decoy pii_log only the generated numeric id is logged
		return c.NoContent(http.StatusCreated)
	})
}
