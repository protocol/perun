package main

import (
	"net/http"
	"os"

	"github.com/gin-contrib/sessions"
	"github.com/gin-contrib/sessions/cookie"
	"github.com/gin-gonic/gin"
)

func main() {
	r := gin.Default()
	store := cookie.NewStore([]byte(os.Getenv("ORDERS_SECRET")))
	store.Options(sessions.Options{Path: "/", Secure: true, HttpOnly: true, SameSite: http.SameSiteStrictMode})
	r.Use(sessions.Sessions("orders", store))

	r.GET("/healthz", func(c *gin.Context) { c.JSON(200, gin.H{"ok": true}) }) // @@R GET /healthz 0 public

	registerPublic(r)
	registerGateway(r)

	api := r.Group("", bearerAuth())
	api.GET("/api/me", func(c *gin.Context) { // @@R GET /api/me 1
		u := user(c)
		c.JSON(200, gin.H{"uid": u.UID, "role": u.Role})
	})
	registerRecords(api)
	registerCatalog(api)
	registerPartners(api)
	registerIntegrations(api)

	registerAccount(r.Group("", cookieAuth()))
	registerProfile(r.Group("", memberAuth()))

	r.Run("127.0.0.1:8080")
}
