import sqlite3
import requests

DB = sqlite3.connect("shipments.db")
BASE = "https://carriers.example.com/v1"


def load_order(order_id):
    resp = requests.get(f"{BASE}/orders/{int(order_id)}", timeout=10)
    resp.raise_for_status()
    return resp.json()


def record_carrier(order_id):
    data = load_order(order_id)
    carrier = data["carrier_name"]
    DB.execute(f"INSERT INTO carriers (order_id, name) VALUES ({int(order_id)}, '{carrier}')")
    DB.commit()


def count_for(order_id):
    cur = DB.execute("SELECT COUNT(*) FROM carriers WHERE order_id = ?", (int(order_id),))
    return cur.fetchone()[0]


if __name__ == "__main__":
    record_carrier(1042)
    print(count_for(1042))
