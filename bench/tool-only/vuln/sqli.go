package bench

import (
	"database/sql"
	"fmt"
)

func FindUser(db *sql.DB, name string) (*sql.Rows, error) {
	return db.Query(fmt.Sprintf("SELECT * FROM users WHERE name = '%s'", name))
}
