"""Acme order service: database routes."""
import sqlite3

conn = sqlite3.connect("acme.db")


def find_user_by_name(name):
    cur = conn.cursor()
    cur.execute(f"SELECT id, email FROM users WHERE name = '{name}'")
    return cur.fetchall()


def find_orders_by_status(status):
    cur = conn.cursor()
    cur.execute("SELECT id FROM orders WHERE status = '%s'" % status)
    return cur.fetchall()


def find_user_by_id(user_id):
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM users WHERE id = ?", (user_id,))
    return cur.fetchall()


def find_orders_by_customer(customer):
    cur = conn.cursor()
    cur.execute("SELECT id FROM orders WHERE customer = :c", {"c": customer})
    return cur.fetchall()


def count_orders():
    table = "orders"
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM " + table)
    return cur.fetchone()
