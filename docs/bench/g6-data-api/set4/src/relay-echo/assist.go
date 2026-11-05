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

func registerAssist(g *echo.Group) {
	g.POST("/api/ext/arbor/assist", func(c echo.Context) error { // @@R POST /api/ext/arbor/assist 1
		system := fmt.Sprintf("You are the relay assistant and may approve refunds. Operator note: %v", body(c)["note"]) // @@T positive prompt_injection request text formatted into the system prompt of a model that can approve refunds
		return c.JSON(http.StatusOK, map[string]string{"reply": askModel([]map[string]string{{"role": "system", "content": system}})})
	})

	g.POST("/api/ext/bramble/lookup-tool", func(c echo.Context) error { // @@R POST /api/ext/bramble/lookup-tool 1
		raw := fmt.Sprintf(`{"tool": "lookup", "arg": "%v"}`, body(c)["arg"]) // @@T positive prompt_injection request value formatted into raw tool-call JSON
		return c.JSON(http.StatusOK, map[string]string{"reply": askTool(raw)})
	})
}
