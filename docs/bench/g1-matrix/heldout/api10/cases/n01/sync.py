import sqlite3
import requests

API = "https://api.example.com/v1"


def fetch_vendor(vendor_id):
    resp = requests.get(f"{API}/vendors/{vendor_id}", timeout=5)
    resp.raise_for_status()
    return resp.json()


def sync_vendor(db_path, vendor_id):
    vendor = fetch_vendor(vendor_id)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO vendors (id, name) VALUES (?, ?)",
        (int(vendor_id), vendor["name"]),
    )
    conn.commit()
    conn.close()
    return vendor_id
