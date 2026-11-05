import sqlite3

import httpx

COLUMNS = {"name": "name", "created": "created_at", "total": "total_cents"}


def get_prefs(user):
    r = httpx.get(f"https://prefs.example.com/users/{user}", timeout=5)
    r.raise_for_status()
    return r.json()


def rows_for(db, user):
    prefs = get_prefs(user)
    col = COLUMNS[prefs["sort"]]
    direction = "DESC" if prefs.get("desc") is True else "ASC"
    conn = sqlite3.connect(db)
    cur = conn.execute(
        f"SELECT name, created_at, total_cents FROM invoices WHERE owner = ? "
        f"ORDER BY {col} {direction}",
        (user,),
    )
    out = cur.fetchall()
    conn.close()
    return out
