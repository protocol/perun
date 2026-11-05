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

func registerCatalog(r gin.IRoutes) {

	r.GET("/api/pebble", func(c *gin.Context) { // @@R GET /api/pebble 1 ; T decoy missing_authn the group is created with bearerAuth middleware and the list is filtered by the session owner
		out := []*Row{}
		for _, row := range rows {
			if row.Owner == user(c).UID {
				out = append(out, row)
			}
		}
		c.JSON(200, out)
	})

	r.DELETE("/api/falcon/:id", requireAdmin(), func(c *gin.Context) { // @@R DELETE /api/falcon/:id 1 ; T decoy missing_authz requireAdmin middleware aborts with 403 for other roles
		id, _ := strconv.Atoi(c.Param("id"))
		if rows[id] == nil {
			c.AbortWithStatus(http.StatusNotFound)
			return
		}
		delete(rows, id)
		c.Status(http.StatusNoContent)
	})

	r.GET("/api/marten/:id", func(c *gin.Context) { // @@R GET /api/marten/:id 1 ; T decoy missing_object_check ownedOr404 compares the owner with the session user and answers 404
		id, _ := strconv.Atoi(c.Param("id"))
		if row := ownedOr404(c, id); row != nil {
			c.JSON(200, row)
		}
	})
}

var _ = []any{rand.Read, tls.VersionTLS12, hex.EncodeToString, json.Marshal, fmt.Sprintf, log.Printf, http.StatusOK, strconv.Itoa, strings.TrimSpace, sessions.Default}
