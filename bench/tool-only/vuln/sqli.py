import sqlite3


def find_user(conn: sqlite3.Connection, name: str):
    return conn.execute("SELECT * FROM users WHERE name = '" + name + "'").fetchall()
