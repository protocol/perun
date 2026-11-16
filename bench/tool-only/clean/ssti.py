from flask import Flask, request
from jinja2 import Template

app = Flask(__name__)


@app.route('/greet')
def greet():
    ctx = {'name': request.args['name']}
    return Template('Hello {{ name }}').render(ctx)
