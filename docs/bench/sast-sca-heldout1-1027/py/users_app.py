import os
import json
import pickle
import shlex
import subprocess
import sqlite3
import yaml
from flask import Flask, request, redirect, url_for, send_from_directory
from markupsafe import escape
import requests
from db_helpers import run_raw, run_param

app = Flask(__name__)
BASE = "/srv/acme/files"
HOSTS = {"status": "https://status.example.com/api", "docs": "https://docs.example.com/api"}
db = sqlite3.connect("acme.db")


@app.route("/user")
def user_direct():
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE name = '%s'" % request.args["name"])
    return json.dumps(cur.fetchall())


@app.route("/user_safe")
def user_param():
    cur = db.cursor()
    cur.execute("SELECT * FROM users WHERE name = ?", (request.args["name"],))
    return json.dumps(cur.fetchall())


def build_filter(term):
    return f"SELECT * FROM orders WHERE note LIKE '%{term}%'"


@app.route("/orders")
def orders():
    q = build_filter(request.args.get("q", ""))
    cur = db.cursor()
    cur.execute(q)
    return json.dumps(cur.fetchall())


@app.route("/order")
def order_by_id():
    oid = int(request.args["id"])
    cur = db.cursor()
    cur.execute(f"SELECT * FROM orders WHERE id = {oid}")
    return json.dumps(cur.fetchall())


@app.route("/ping")
def ping():
    host = request.args["host"]
    os.system("ping -c1 " + host)
    return "ok"


@app.route("/ping_safe")
def ping_safe():
    host = request.args["host"]
    subprocess.run(["ping", "-c1", host], check=False)
    return "ok"


def archive_cmd(name):
    return f"tar czf /tmp/{name}.tgz /srv/acme/data"


@app.route("/archive")
def archive():
    cmd = archive_cmd(request.form["name"])
    subprocess.call(cmd, shell=True)
    return "done"


@app.route("/archive_safe")
def archive_quoted():
    name = shlex.quote(request.form["name"])
    os.system("tar czf /tmp/" + name + ".tgz /srv/acme/data")
    return "done"


@app.route("/download")
def download():
    path = os.path.join(BASE, request.args["f"])
    return open(path, "rb").read()


@app.route("/download_safe")
def download_safe():
    return send_from_directory(BASE, request.args["f"])


@app.route("/fetch")
def fetch_url():
    return requests.get(request.args["url"], timeout=5).text


@app.route("/fetch_safe")
def fetch_known():
    target = HOSTS[request.args.get("svc", "status")]
    return requests.get(target, timeout=5).text


@app.route("/load", methods=["POST"])
def load_blob():
    obj = pickle.loads(request.data)
    return str(obj)


@app.route("/load_safe", methods=["POST"])
def load_json():
    obj = json.loads(request.data)
    return str(obj)


@app.route("/conf", methods=["POST"])
def conf():
    cfg = yaml.load(request.data, Loader=yaml.Loader)
    return str(cfg)


@app.route("/conf_safe", methods=["POST"])
def conf_safe():
    cfg = yaml.safe_load(request.data)
    return str(cfg)


@app.route("/hello")
def hello():
    name = request.args.get("name", "guest")
    return "<h1>Hello " + name + "</h1>"


@app.route("/hello_safe")
def hello_safe():
    name = request.args.get("name", "guest")
    return "<h1>Hello " + str(escape(name)) + "</h1>"


@app.route("/go")
def go():
    return redirect(request.args["next"])


@app.route("/go_safe")
def go_safe():
    return redirect(url_for("hello"))


@app.route("/raw")
def raw_query():
    return json.dumps(run_raw("SELECT * FROM users WHERE email = '" + request.args["email"] + "'"))


@app.route("/count")
def count_all():
    return json.dumps(run_raw("SELECT COUNT(*) FROM users"))


@app.route("/by_role")
def by_role():
    return json.dumps(run_param("SELECT * FROM users WHERE role = ?", (request.args["role"],)))
