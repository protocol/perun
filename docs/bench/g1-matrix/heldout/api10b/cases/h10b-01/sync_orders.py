import sqlite3
import requests

API = "https://api.acme-shipping.example.com/v2"


def fetch_carrier(order_ref):
    r = requests.get(f"{API}/orders/{order_ref}", timeout=10)
    r.raise_for_status()
    return r.json()


def record_carrier(conn, order_ref):
    data = fetch_carrier(order_ref)
    cur = conn.cursor()
    cur.execute(
        f"UPDATE orders SET carrier = '{data['carrier_name']}' WHERE ref = ?",
        (order_ref,),
    )
    conn.commit()
    return cur.rowcount


def main():
    conn = sqlite3.connect("orders.db")
    for ref in ("A100", "A101", "A102"):
        print(ref, record_carrier(conn, ref))


if __name__ == "__main__":
    main()
