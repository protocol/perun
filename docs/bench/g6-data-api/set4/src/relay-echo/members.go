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

var seedSpire = []map[string]any{{"label": "Sample relay", "region": "north", "count": 3}} // @@T decoy pii_data seed rows hold labels and counts and no person

func registerMembers(g *echo.Group) {
	g.GET("/api/ext/spire/sample", func(c echo.Context) error { // @@R GET /api/ext/spire/sample 1
		return c.JSON(http.StatusOK, map[string]int{"count": len(seedSpire)})
	})

	g.POST("/api/ext/dune/rotate-key", func(c echo.Context) error { // @@R POST /api/ext/dune/rotate-key 1
		b := make([]byte, 8)
		_, _ = rand.Read(b)
		keyID := hex.EncodeToString(b)
		u := userOf(c)
		c.Logger().Infof("rotate user=%d", u.UID) // @@T decoy pii_log the log line carries only the numeric user id
		return c.JSON(http.StatusOK, map[string]string{"keyId": keyID})
	})

	g.POST("/api/ext/shoal/track", func(c echo.Context) error { // @@R POST /api/ext/shoal/track 1
		resp, err := httpc.Get("https://stats.vendor.example.com/v1/event?event=view") // @@T decoy pii_data analytics payload is a constant event name with no user identifier
		if err == nil {
			resp.Body.Close()
		}
		return c.NoContent(http.StatusNoContent)
	})
}
