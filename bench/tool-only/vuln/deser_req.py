import pickle

from flask import Flask, request

app = Flask(__name__)


@app.route('/restore')
def restore():
    return pickle.loads(request.args['blob'].encode())
