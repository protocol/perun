SORT_COLUMNS = {"name": "name", "date": "created_at"}


def pick_sort_column(value):
    return SORT_COLUMNS.get(value, "created_at")


def list_widgets(cur, sort):
    col = pick_sort_column(sort)
    cur.execute(f"SELECT * FROM widgets ORDER BY {col}")
    return cur.fetchall()
