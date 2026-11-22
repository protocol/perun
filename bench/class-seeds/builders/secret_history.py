"""Seed builder for class "investigation-secret-history": a temp git repo where a token is committed, then removed in a later commit."""
import os, subprocess, sys
sys.path.insert(0, os.path.dirname(__file__))
import secrets_iac_tok as t

GIT = ["git", "-c", "user.name=seed", "-c", "user.email=seed@example.com", "-c", "commit.gpgsign=false"]


def run(dst, *a):
    subprocess.run(GIT + list(a), cwd=dst, check=True, capture_output=True)


def build(dst, kind):
    run(dst, "init", "-q")
    src = os.path.join(dst, "app")
    os.makedirs(src)
    if kind == "mutant":  # whole file added then deleted, other provider
        open(src + "/notify.env", "w").write("SLACK_BOT_TOKEN=%s\nREGION=eu\n" % t.slack())
        run(dst, "add", "-A"); run(dst, "commit", "-qm", "add notifier")
        os.remove(src + "/notify.env")
    else:
        tok = t.gh() if kind == "vuln" else "placeholder"
        open(src + "/config.py", "w").write('API_TOKEN = "%s"\nTIMEOUT = 30\n' % tok)
        run(dst, "add", "-A"); run(dst, "commit", "-qm", "add config")
        open(src + "/config.py", "w").write('import os\n\nAPI_TOKEN = os.environ.get("API_TOKEN", "")\nTIMEOUT = 30\n')
    run(dst, "add", "-A"); run(dst, "commit", "-qm", "remove hard-coded secret")
