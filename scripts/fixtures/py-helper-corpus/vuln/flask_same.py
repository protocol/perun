from flask import Flask, request, redirect, render_template_string, make_response
import sqlite3, os, pickle
app = Flask(__name__)

def find_user(name):
    db = sqlite3.connect("app.db")
    return db.execute(f"SELECT * FROM users WHERE name = '{name}'").fetchall()  # SINK sqli

@app.route("/u")
def u():
    return str(find_user(request.args.get("name")))

def run_probe(path):
    base = "/srv/files"
    with open(os.path.join(base, path)) as fh:  # SINK path-traversal
        return fh.read()

@app.route("/f")
def f():
    return run_probe(request.args["p"])

def load_blob(raw):
    return pickle.loads(raw)  # SINK deserialize

@app.route("/b", methods=["POST"])
def b():
    return str(load_blob(request.get_data()))

def render_page(tpl):
    return render_template_string(tpl)  # SINK ssti

@app.route("/t")
def t():
    return render_page(request.args.get("tpl"))

def go(url):
    return redirect(url)  # SINK open-redirect

@app.route("/go")
def go_route():
    return go(request.args.get("next"))
