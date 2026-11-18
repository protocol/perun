ALLOWED_COLS = {"name", "created_at"}


def list_widgets(cur, col):
    if col not in ALLOWED_COLS:
        raise ValueError("unsupported sort column")
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")  # nosec B608 # noqa: S608 # nosemgrep: python.lang.security.audit.formatted-sql-query.formatted-sql-query, python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query (col is allow-listed above)
    return cur.fetchall()
