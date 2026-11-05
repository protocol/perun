package main

import (
	"crypto/rand"
	"crypto/tls"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"log"
	"net/http"
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gin-contrib/sessions"
)

var (
	vendor    = "https://dispatch.vendor.example.com"
	vendorKey = os.Getenv("DISPATCH_KEY")
	pin       = os.Getenv("ORDERS_PIN")
)

func registerRecords(r gin.IRoutes) {

	r.POST("/api/willow/:id/purge", func(c *gin.Context) { // @@R POST /api/willow/:id/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a session
		id, _ := strconv.Atoi(c.Param("id"))
		if rows[id] == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		delete(rows, id)
		c.Status(http.StatusNoContent)
	})

	r.POST("/api/juniper/:id/purge", func(c *gin.Context) { // @@R POST /api/juniper/:id/purge 0 ; T positive missing_authz purge is an admin action but the group only requires a session
		id, _ := strconv.Atoi(c.Param("id"))
		if rows[id] == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		delete(rows, id)
		c.Status(http.StatusNoContent)
	})

	r.GET("/api/otter/:id", func(c *gin.Context) { // @@R GET /api/otter/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
		id, _ := strconv.Atoi(c.Param("id"))
		row := rows[id]
		if row == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		c.JSON(200, row)
	})

	r.GET("/api/badger/:id", func(c *gin.Context) { // @@R GET /api/badger/:id 0 ; T positive missing_object_check row returned by id without comparing its owner with the session user
		id, _ := strconv.Atoi(c.Param("id"))
		row := rows[id]
		if row == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		c.JSON(200, row)
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
