import sqlite3

from rates import fetch_rate

DB = sqlite3.connect("pricing.db")


def apply_rate(region):
    rate = fetch_rate(region)
    DB.execute(f"UPDATE regions SET tax = {rate['tax_pct']} WHERE code = ?", (region,))
    DB.commit()
