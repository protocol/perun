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

var codeRE = regexp.MustCompile(`^[A-Z]{2}$`)

func registerIntegrations(g *echo.Group) {
	g.GET("/api/ext/plover/:id/image", func(c echo.Context) error { // @@R GET /api/ext/plover/:id/image 1
		if _, err := strconv.Atoi(c.Param("id")); err != nil {
			return c.NoContent(http.StatusBadRequest)
		}
		resp, err := httpc.Get("https://img.vendor.example.com/p/" + c.Param("id") + ".jpg") // @@T decoy ssrf host fixed in code and the caller supplies only a validated integer id
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		out, _ := io.ReadAll(resp.Body)
		return c.Blob(http.StatusOK, "image/jpeg", out)
	})

	g.GET("/api/ext/sparrow/:code/rates", func(c echo.Context) error { // @@R GET /api/ext/sparrow/:code/rates 1
		if !codeRE.MatchString(c.Param("code")) {
			return c.NoContent(http.StatusBadRequest)
		}
		req, _ := http.NewRequest(http.MethodGet, vendor+"/v1/rates/"+c.Param("code"), nil)
		req.Header.Set("X-Api-Key", vendorKey) // @@T decoy secret_in_url vendor key sent in a header and the URL holds only the validated code
		resp, err := httpc.Do(req)
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		out, _ := io.ReadAll(resp.Body)
		return c.String(http.StatusOK, string(out))
	})

	g.GET("/api/ext/tundra/:code/stock", func(c echo.Context) error { // @@R GET /api/ext/tundra/:code/stock 1
		if !codeRE.MatchString(c.Param("code")) {
			return c.NoContent(http.StatusBadRequest)
		}
		req, _ := http.NewRequest(http.MethodGet, vendor+"/v1/stock/"+c.Param("code"), nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := httpc.Do(req)
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		c.Logger().Infof("stock lookup code=%s status=%d", c.Param("code"), resp.StatusCode) // @@T decoy secret_in_log only the status and the validated code are logged
		out, _ := io.ReadAll(resp.Body)
		return c.String(http.StatusOK, string(out))
	})
}
