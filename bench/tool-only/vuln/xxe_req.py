from flask import Flask, request
from lxml import etree

app = Flask(__name__)


@app.route('/feed')
def feed():
    parser = etree.XMLParser(resolve_entities=True, load_dtd=True)
    return etree.fromstring(request.args['xml'].encode(), parser).tag
