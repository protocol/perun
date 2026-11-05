package main

import (
	"crypto/tls"
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
	_ = tls.VersionTLS12
)

func registerPartners(g *echo.Group) {
	g.POST("/api/ext/juniper/push", func(c echo.Context) error { // @@R POST /api/ext/juniper/push 1
		req, _ := http.NewRequest(http.MethodPost, vendor+"/v1/juniper", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := (&http.Client{Timeout: 5 * time.Second, Transport: &http.Transport{TLSClientConfig: &tls.Config{InsecureSkipVerify: true}}}).Do(req) // @@T positive tls_off client skips certificate verification for the vendor request
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		return c.JSON(http.StatusOK, map[string]int{"status": resp.StatusCode})
	})

	g.GET("/api/ext/falcon/fetch", func(c echo.Context) error { // @@R GET /api/ext/falcon/fetch 1
		resp, err := httpc.Get(c.QueryParam("url")) // @@T positive ssrf caller-supplied URL fetched from the server
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		out, _ := io.ReadAll(resp.Body)
		return c.String(http.StatusOK, string(out))
	})

	g.GET("/api/ext/heron/status", func(c echo.Context) error { // @@R GET /api/ext/heron/status 1
		resp, err := http.Get(vendor + "/v1/heron/status") // @@T positive no_timeout default client has no timeout so a slow vendor holds the request open
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		return c.JSON(http.StatusOK, map[string]int{"status": resp.StatusCode})
	})

	g.GET("/api/ext/otter/lookup", func(c echo.Context) error { // @@R GET /api/ext/otter/lookup 1
		resp, err := httpc.Get(vendor + "/v1/otter?key=" + vendorKey) // @@T positive secret_in_url vendor key sent as a query parameter
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		return c.JSON(http.StatusOK, map[string]int{"status": resp.StatusCode})
	})

	g.GET("/api/ext/badger/ping", func(c echo.Context) error { // @@R GET /api/ext/badger/ping 1
		c.Logger().Infof("vendor ping key=%s", vendorKey) // @@T positive secret_in_log vendor key written to the application log
		req, _ := http.NewRequest(http.MethodGet, vendor+"/v1/ping", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := httpc.Do(req)
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		return c.JSON(http.StatusOK, map[string]int{"status": resp.StatusCode})
	})

	g.GET("/api/ext/wren/ping", func(c echo.Context) error { // @@R GET /api/ext/wren/ping 1
		c.Logger().Infof("vendor ping token=%s", vendorKey) // @@T positive secret_in_log vendor key written to the application log
		req, _ := http.NewRequest(http.MethodGet, vendor+"/v1/wren", nil)
		req.Header.Set("X-Api-Key", vendorKey)
		resp, err := httpc.Do(req)
		if err != nil {
			return c.NoContent(http.StatusBadGateway)
		}
		defer resp.Body.Close()
		return c.JSON(http.StatusOK, map[string]int{"status": resp.StatusCode})
	})
}
