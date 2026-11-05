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

func registerRecords(g *echo.Group) {
	g.POST("/api/beacon/:id/purge", func(c echo.Context) error { // @@R POST /api/beacon/:id/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a session
		id, _ := strconv.Atoi(c.Param("id"))
		mu.Lock()
		defer mu.Unlock()
		if cache[id] == "" {
			return c.NoContent(http.StatusNotFound)
		}
		delete(cache, id)
		return c.NoContent(http.StatusNoContent)
	})

	g.POST("/api/cobalt/:id/purge", func(c echo.Context) error { // @@R POST /api/cobalt/:id/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a session
		id, _ := strconv.Atoi(c.Param("id"))
		mu.Lock()
		defer mu.Unlock()
		if cache[id] == "" {
			return c.NoContent(http.StatusNotFound)
		}
		delete(cache, id)
		return c.NoContent(http.StatusNoContent)
	})

	g.GET("/api/granite/:id", func(c echo.Context) error { // @@R GET /api/granite/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
		id, _ := strconv.Atoi(c.Param("id"))
		mu.Lock()
		defer mu.Unlock()
		if rows[id] == nil {
			return c.NoContent(http.StatusNotFound)
		}
		return c.JSON(http.StatusOK, rows[id])
	})

	g.GET("/api/pebble/:id", func(c echo.Context) error { // @@R GET /api/pebble/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
		id, _ := strconv.Atoi(c.Param("id"))
		mu.Lock()
		defer mu.Unlock()
		if rows[id] == nil {
			return c.NoContent(http.StatusNotFound)
		}
		return c.JSON(http.StatusOK, rows[id])
	})
}
