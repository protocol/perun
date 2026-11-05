package main

import (
	"net/http"
	"strings"

	"github.com/labstack/echo/v4"
)

func bearerAuth(next echo.HandlerFunc) echo.HandlerFunc {
	return func(c echo.Context) error {
		mu.Lock()
		s := sessions[strings.TrimPrefix(c.Request().Header.Get("Authorization"), "Bearer ")]
		mu.Unlock()
		if s == nil {
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
		}
		c.Set("user", s)
		return next(c)
	}
}

func cookieAuth(next echo.HandlerFunc) echo.HandlerFunc {
	return func(c echo.Context) error {
		ck, err := c.Cookie("sid")
		if err != nil {
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
		}
		mu.Lock()
		s := sessions[ck.Value]
		mu.Unlock()
		if s == nil {
			return c.JSON(http.StatusUnauthorized, map[string]string{"error": "unauthorized"})
		}
		c.Set("user", s)
		return next(c)
	}
}

func userOf(c echo.Context) *session { return c.Get("user").(*session) }

func isAdmin(c echo.Context) bool { return userOf(c).Role == "admin" }

// ownedOr404 returns the row only when its owner is the session user.
func ownedOr404(c echo.Context, id int) *row {
	mu.Lock()
	defer mu.Unlock()
	if r := rows[id]; r != nil && r.Owner == userOf(c).UID {
		return r
	}
	return nil
}
