import subprocess
from markupsafe import Markup

def ping(host):
    return subprocess.run("ping -c1 " + host, shell=True, capture_output=True).stdout  # SINK command-injection

def wrap_html(name):
    return Markup("<h1>" + name + "</h1>")  # SINK xss
