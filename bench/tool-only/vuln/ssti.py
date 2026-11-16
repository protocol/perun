from flask import Flask, request
from jinja2 import Template

app = Flask(__name__)


@app.route('/greet')
def greet():
    return Template(request.args['tpl']).render()
