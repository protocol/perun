module example.com/tidepool/ledgerd

go 1.20

require (
	github.com/labstack/echo/v4 v4.9.0
	github.com/jackc/pgx/v5 v5.3.1
	github.com/redis/go-redis/v9 v9.0.5
	github.com/golang-jwt/jwt/v4 v4.4.0
	github.com/prometheus/client_golang v1.25.0
	go.uber.org/zap v1.28.0
)

require (
	golang.org/x/crypto v0.14.0 // indirect
	golang.org/x/text v0.9.0 // indirect
	golang.org/x/sync v0.24.0 // indirect
)

replace example.com/tidepool/shared => ../shared
