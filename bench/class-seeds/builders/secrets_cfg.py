"""Seed builder for class "secrets": a hard-coded token is assembled from split parts at test time."""
import os, sys
sys.path.insert(0, os.path.dirname(__file__))
import secrets_iac_tok as t


def build(dst, kind):
    os.makedirs(os.path.join(dst, "src"))
    p = os.path.join(dst, "src")
    if kind == "vuln":
        open(p + "/client.py", "w").write('import requests\n\nGITHUB_TOKEN = "%s"\n\n\ndef repos():\n    return requests.get("https://api.example.com/repos", headers={"Authorization": "token " + GITHUB_TOKEN})\n' % t.gh())
    elif kind == "mutant":  # different file type, different provider, key under a nested config object
        open(p + "/settings.json", "w").write('{"notifier": {"channel": "#ops", "bot_token": "%s"}}\n' % t.slack())
    else:
        open(p + "/client.py", "w").write('import os\nimport requests\n\n\ndef repos():\n    return requests.get("https://api.example.com/repos", headers={"Authorization": "token " + os.environ["GITHUB_TOKEN"]})\n')
