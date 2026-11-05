import httpx
import psycopg2

BASE = "https://inventory.example.com"


def load_items(warehouse):
    with httpx.Client(base_url=BASE, timeout=10) as client:
        r = client.get("/items", params={"wh": warehouse})
        r.raise_for_status()
        return r.json()["items"]


def refresh(dsn, warehouse):
    conn = psycopg2.connect(dsn)
    cur = conn.cursor()
    for item in load_items(warehouse):
        cur.execute("SELECT qty FROM stock WHERE sku = '%s'" % item["sku"])
        row = cur.fetchone()
        if row is None:
            cur.execute("INSERT INTO stock (sku, qty) VALUES (%s, %s)",
                        (item["sku"], item["qty"]))
    conn.commit()
    conn.close()
