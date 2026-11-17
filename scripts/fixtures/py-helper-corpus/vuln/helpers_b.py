import urllib.request
import jinja2

def read_doc(name):
    with open("/srv/docs/" + name) as fh:  # SINK path-traversal
        return fh.read()

def fetch(url):
    return urllib.request.urlopen(url).read()  # SINK ssrf

def shout(s):
    return jinja2.Template("Hello " + s).render()  # SINK ssti
