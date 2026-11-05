import sqlite3

import requests
from fastapi import APIRouter, Depends
from .auth import require_admin
router = APIRouter()
PARTNER_URL = "https://catalog.partner.example.com/v1/products"


@router.post("/catalog/sync")
def sync_catalog(_=Depends(require_admin)):
    items = requests.get(PARTNER_URL, timeout=5).json()
    conn = sqlite3.connect("shop.db")
    for item in items:
        conn.execute(
            f"INSERT INTO products (sku, name) VALUES ('{item['sku']}', '{item['name']}')"
        )
    conn.commit()
    conn.close()
    return {"imported": len(items)}
