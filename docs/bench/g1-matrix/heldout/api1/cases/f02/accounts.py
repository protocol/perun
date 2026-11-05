import sqlite3

from flask import Flask, abort, g, jsonify, request

app = Flask(__name__)


def db():
    return sqlite3.connect("acme.db")


@app.get("/statements/<int:sid>")
def get_statement(sid):
    row = db().execute(
        "SELECT * FROM statements WHERE id = ? AND user_id = ?", (sid, g.user["id"])
    ).fetchone()
    if row is None:
        abort(404)
    return jsonify(dict(row))


@app.get("/statements/<int:sid>/download")
def download_statement(sid):
    row = db().execute("SELECT * FROM statements WHERE id = ?", (sid,)).fetchone()
    if row is None:
        abort(404)
    return jsonify({"pdf": row["pdf_path"]})
