from flask import request


def list_widgets(cur):
    cur.execute(f"SELECT * FROM widgets ORDER BY {request.args['sort']}")
    return cur.fetchall()
