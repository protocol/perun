package main

import (
	"encoding/json"
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

func registerCopilot(g *echo.Group) {
	g.POST("/api/ext/fennel/assist", func(c echo.Context) error { // @@R POST /api/ext/fennel/assist 1
		note := clip(str(body(c)["note"]), 500)
		reply := askModel([]map[string]string{{"role": "system", "content": "You summarise relay notes and have no tools."}, {"role": "user", "content": note}}) // @@T decoy prompt_injection fixed system prompt and the request text travels only as a length-capped user message
		return c.JSON(http.StatusOK, map[string]string{"reply": reply})
	})

	g.POST("/api/ext/hazel/lookup-tool", func(c echo.Context) error { // @@R POST /api/ext/hazel/lookup-tool 1
		raw, _ := json.Marshal(map[string]string{"tool": "lookup", "arg": str(body(c)["sku"])}) // @@T decoy prompt_injection tool name fixed and the value is JSON-encoded as data
		return c.JSON(http.StatusOK, map[string]string{"reply": askTool(string(raw))})
	})

	g.POST("/api/ext/ivy/translate", func(c echo.Context) error { // @@R POST /api/ext/ivy/translate 1
		text := clip(str(body(c)["text"]), 500)
		reply := askModel([]map[string]string{{"role": "system", "content": "You translate relay notes and have no tools."}, {"role": "user", "content": text}}) // @@T decoy rate_limit model call route sits in the group that applies the throttle middleware so each client address is capped at sixty requests a minute
		return c.JSON(http.StatusOK, map[string]string{"reply": reply})
	})
}
