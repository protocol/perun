package main

import (
	"net/http"

	"github.com/gin-contrib/sessions"
	"github.com/gin-gonic/gin"
)

func bearerAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		token := c.GetHeader("Authorization")
		if len(token) > 7 {
			token = token[7:]
		}
		s, ok := tokens[token]
		if !ok {
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		c.Set("user", s)
		c.Next()
	}
}

func requireAdmin() gin.HandlerFunc {
	return func(c *gin.Context) {
		if u, ok := c.Get("user"); !ok || u.(Session).Role != "admin" {
			c.AbortWithStatus(http.StatusForbidden)
			return
		}
		c.Next()
	}
}

func cookieAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		sid, err := c.Cookie("sid")
		s, ok := tokens[sid]
		if err != nil || !ok {
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		c.Set("user", s)
		c.Next()
	}
}

func memberAuth() gin.HandlerFunc {
	return func(c *gin.Context) {
		uid, ok := sessions.Default(c).Get("uid").(int)
		s, found := byUID[uid]
		if !ok || !found {
			c.AbortWithStatus(http.StatusUnauthorized)
			return
		}
		c.Set("user", s)
		c.Next()
	}
}

func user(c *gin.Context) Session { return c.MustGet("user").(Session) }
