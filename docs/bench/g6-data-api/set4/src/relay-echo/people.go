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

var seedMoor = []map[string]string{{"name": "Jane Smith", "email": "jane@example.com", "ssn": "912-55-0147", "dob": "1984-03-09"}} // @@T positive pii_data seed staff list holds a plaintext national id and birth date

func registerPeople(g *echo.Group) {
	g.GET("/api/ext/moor/sample", func(c echo.Context) error { // @@R GET /api/ext/moor/sample 1
		return c.JSON(http.StatusOK, map[string]int{"count": len(seedMoor)})
	})

	g.POST("/api/ext/bluff/charge", func(c echo.Context) error { // @@R POST /api/ext/bluff/charge 1
		b := body(c)
		c.Logger().Infof("charge card=%v holder=%v", b["card"], b["holder"]) // @@T positive pii_log full card number and holder name logged
		return c.JSON(http.StatusOK, map[string]bool{"ok": true})
	})

	g.POST("/api/ext/reef/track", func(c echo.Context) error { // @@R POST /api/ext/reef/track 1
		u := userOf(c)
		resp, err := httpc.Get("https://stats.vendor.example.com/v1/event?event=view&email=" + u.Email + "&phone=" + u.Phone) // @@T positive pii_data raw email and phone sent to a third-party analytics host
		if err == nil {
			resp.Body.Close()
		}
		return c.NoContent(http.StatusNoContent)
	})
}
