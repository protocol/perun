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

func registerCatalog(g *echo.Group) {
	g.GET("/api/compass", func(c echo.Context) error { // @@R GET /api/compass 1 ; T decoy missing_authn the group is created with bearerAuth middleware and the list is filtered by the session owner
		mine := []*row{}
		mu.Lock()
		defer mu.Unlock()
		for _, r := range rows {
			if r.Owner == userOf(c).UID {
				mine = append(mine, r)
			}
		}
		return c.JSON(http.StatusOK, mine)
	})

	g.GET("/api/recent", func(c echo.Context) error { // @@R GET /api/recent 1 ; T decoy missing_authn the group is created with bearerAuth middleware and the list is filtered by the session owner
		mine := []*row{}
		mu.Lock()
		defer mu.Unlock()
		for _, r := range rows {
			if r.Owner == userOf(c).UID {
				mine = append(mine, r)
			}
		}
		return c.JSON(http.StatusOK, mine)
	})

	g.DELETE("/api/copper/:id", func(c echo.Context) error { // @@R DELETE /api/copper/:id 1 ; T decoy missing_authz the handler answers 403 for every other role before the delete
		if !isAdmin(c) {
			return c.NoContent(http.StatusForbidden)
		}
		id, _ := strconv.Atoi(c.Param("id"))
		mu.Lock()
		defer mu.Unlock()
		delete(rows, id)
		return c.NoContent(http.StatusNoContent)
	})

	g.POST("/api/timber/:id/approve", func(c echo.Context) error { // @@R POST /api/timber/:id/approve 1 ; T decoy missing_authz the handler answers 403 for every other role before the update
		if !isAdmin(c) {
			return c.NoContent(http.StatusForbidden)
		}
		id, _ := strconv.Atoi(c.Param("id"))
		mu.Lock()
		defer mu.Unlock()
		if rows[id] == nil {
			return c.NoContent(http.StatusNotFound)
		}
		rows[id].Approved = true
		return c.JSON(http.StatusOK, rows[id])
	})

	g.GET("/api/thistle/:id", func(c echo.Context) error { // @@R GET /api/thistle/:id 1 ; T decoy missing_object_check ownedOr404 compares the owner with the session user and answers 404
		id, _ := strconv.Atoi(c.Param("id"))
		r := ownedOr404(c, id)
		if r == nil {
			return c.NoContent(http.StatusNotFound)
		}
		return c.JSON(http.StatusOK, r)
	})

	g.PUT("/api/willow/:id/label", func(c echo.Context) error { // @@R PUT /api/willow/:id/label 1 ; T decoy missing_object_check lookup is scoped to the session owner so a foreign id finds nothing
		id, _ := strconv.Atoi(c.Param("id"))
		r := ownedOr404(c, id)
		if r == nil {
			return c.NoContent(http.StatusNotFound)
		}
		r.Label = clip(str(body(c)["label"]), 80)
		return c.JSON(http.StatusOK, r)
	})
}
