import sqlite3
from vendor import fetch_products
from checks import clean_all

def connect(path="catalog.db"):
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE IF NOT EXISTS products (sku TEXT PRIMARY KEY, name TEXT, price REAL)")
    return conn

def sync(conn, category):
    rows = fetch_products(category)
    items = clean_all([r for r in rows if isinstance(r, dict) and r.get("category") == category])
    conn.executemany(
        "INSERT OR REPLACE INTO products (sku, name, price) VALUES (:sku, :name, :price)",
        items,
    )
    conn.commit()
    return len(items)

def price_of(conn, sku):
    row = conn.execute("SELECT price FROM products WHERE sku = ?", (sku,)).fetchone()
    return row[0] if row else None
