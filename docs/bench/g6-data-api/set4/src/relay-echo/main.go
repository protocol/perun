package main

import (
	"net/http"
	"time"

	"github.com/labstack/echo/v4"
)

func main() {
	e := echo.New()
	e.IPExtractor = echo.ExtractIPDirect()
	mainWindow := newWindow(60, time.Minute)

	registerPublic(e)
	registerGateway(e)

	registerDesk(e.Group("", bearerAuth))

	limited := e.Group("", bearerAuth, throttle(mainWindow))
	limited.GET("/api/me", func(c echo.Context) error { // @@R GET /api/me 1
		return c.JSON(http.StatusOK, map[string]any{"uid": userOf(c).UID, "role": userOf(c).Role})
	})
	registerRecords(limited)
	registerCatalog(limited)
	registerPartners(limited)
	registerIntegrations(limited)
	registerPeople(limited)
	registerMembers(limited)
	registerAssist(limited)
	registerCopilot(limited)

	web := e.Group("", cookieAuth, throttle(mainWindow))
	registerWeb(web)
	registerConsole(web)

	e.Logger.Fatal(e.Start("127.0.0.1:3000"))
}
