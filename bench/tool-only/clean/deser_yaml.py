import yaml
from flask import Flask, request

app = Flask(__name__)


@app.route('/import')
def import_config():
    return yaml.safe_load(request.args['doc'])
