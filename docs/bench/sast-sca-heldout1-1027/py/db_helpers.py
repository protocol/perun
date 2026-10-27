import sqlite3

conn = sqlite3.connect("acme.db")


def run_raw(sql):
    cur = conn.cursor()
    cur.execute(sql)
    return cur.fetchall()


def run_param(sql, args):
    cur = conn.cursor()
    cur.execute(sql, args)
    return cur.fetchall()
