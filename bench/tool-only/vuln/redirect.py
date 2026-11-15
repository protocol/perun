from flask import Flask, redirect, request

app = Flask(__name__)


@app.route('/login')
def login():
    return redirect(request.args.get('next', '/'))
