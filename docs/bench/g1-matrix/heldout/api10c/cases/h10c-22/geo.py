import sqlite3

import httpx

DB = sqlite3.connect("places.db")


def lookup(zip_code):
    r = httpx.get("https://geo.example.com/v1/zip", params={"q": zip_code}, timeout=5.0)
    r.raise_for_status()
    return r.json()


def remember(zip_code):
    place = lookup(zip_code)
    query = "INSERT INTO places (zip, city) VALUES (?, '{}')".format(place["city"])
    DB.execute(query, (zip_code,))
    DB.commit()


def known_cities():
    return [row[0] for row in DB.execute("SELECT DISTINCT city FROM places")]
