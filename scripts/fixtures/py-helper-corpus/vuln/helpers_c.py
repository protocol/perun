import yaml
from django.db import connection
from django.http import HttpResponseRedirect

def search(q):
    with connection.cursor() as c:
        c.execute("SELECT * FROM items WHERE name = '" + q + "'")  # SINK sqli
        return c.fetchall()

def load_cfg(raw):
    return yaml.load(raw, Loader=yaml.Loader)  # SINK deserialize

def bounce(url):
    return HttpResponseRedirect(url)  # SINK open-redirect
