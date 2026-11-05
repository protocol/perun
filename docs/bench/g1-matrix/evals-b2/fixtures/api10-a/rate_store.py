import sqlite3

def connect(path="rates.db"):
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS rates (region TEXT, rate REAL, currency TEXT)"
    )
    return conn

def replace_rates(conn, rows):
    conn.execute("DELETE FROM rates")
    conn.executemany(
        "INSERT INTO rates (region, rate, currency) VALUES (?, ?, ?)",
        [(r["region"], r["rate"], r["currency"]) for r in rows],
    )
    conn.commit()

def average_for(conn, region):
    row = conn.execute("SELECT AVG(rate) FROM rates WHERE region = ?", (region,)).fetchone()
    return row[0]
