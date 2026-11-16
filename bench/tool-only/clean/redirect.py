from flask import Flask, redirect, request, url_for

app = Flask(__name__)


@app.route('/home')
def home():
    return 'home'


@app.route('/account')
def account():
    return 'account'


@app.route('/login')
def login():
    if request.args.get('next') == 'account':
        return redirect(url_for('account'))
    return redirect(url_for('home'))
