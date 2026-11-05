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

func registerDesk(g *echo.Group) {
	g.POST("/api/ext/quill/summarise", func(c echo.Context) error { // @@R POST /api/ext/quill/summarise 1
		note := clip(str(body(c)["note"]), 500)
		reply := askModel([]map[string]string{{"role": "system", "content": "You summarise relay notes and have no tools."}, {"role": "user", "content": note}}) // @@T positive rate_limit model call route has no limiter so one client can run unbounded paid requests
		return c.JSON(http.StatusOK, map[string]string{"reply": reply})
	})
}
