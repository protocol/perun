ALLOWED_COLS = {"name", "created_at"}


def list_widgets(cur, col):
    if col not in ALLOWED_COLS:
        raise ValueError("unsupported sort column")
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")
    return cur.fetchall()
