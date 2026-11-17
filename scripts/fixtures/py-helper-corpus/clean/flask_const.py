from flask import Flask, request, redirect
import sqlite3, subprocess
app = Flask(__name__)

def q(name):
    return sqlite3.connect("app.db").execute("SELECT * FROM users WHERE name = ?", (name,)).fetchall()

@app.route("/u")
def u():
    return str(q(request.args.get("name")))

def run(cmd):
    return subprocess.run(cmd, shell=True, capture_output=True).stdout

@app.route("/up")
def up():
    request.args.get("x")
    return run("uptime")

def go(url):
    return redirect(url)

@app.route("/home")
def home():
    return go("/home")
