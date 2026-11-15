#!/usr/bin/env python3
"""Tests for the bundled semgrep rule perun.py.path-traversal (templates/semgrep-taint/py.yml): a Flask request value reaching send_file,
open, os.path.join, pathlib.Path(...).open/read_text/read_bytes or shutil copy/move. send_from_directory, secure_filename,
os.path.basename and safe_join are safe.

Fixtures are annotated like semgrep's own tests: `# ruleid: <id>` marks the NEXT line as a required finding, `# ok: <id>` marks the
next line as one that must stay clean, and every unannotated line must stay clean too. All names and values are fictional. RULES=<dir>
checks another copy of the rules. The live check needs semgrep and prints SKIP without it; the offline pins always run. Plain asserts."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
ID = "perun.py.path-traversal"

PY = '''
import os, pathlib, shutil
from pathlib import Path
from flask import request, send_file, send_from_directory
from werkzeug.utils import secure_filename
from werkzeug.security import safe_join

def concat():
    # ruleid: perun.py.path-traversal
    return send_file("/srv/files/" + request.args["name"])

def joined():
    # ruleid: perun.py.path-traversal
    return send_file(os.path.join("/srv/files", request.args.get("name")))

def form_open():
    # ruleid: perun.py.path-traversal
    return open("/srv/files/" + request.form["name"]).read()

def values_open():
    # ruleid: perun.py.path-traversal
    return open(request.values["p"]).read()

def json_open():
    # ruleid: perun.py.path-traversal
    return open(request.json["p"]).read()

def view_args_send(name):
    # ruleid: perun.py.path-traversal
    return send_file("/srv/files/" + request.view_args["name"])

def file_name():
    # ruleid: perun.py.path-traversal
    return send_file("/srv/up/" + request.files["doc"].filename)

def path_read_text():
    n = request.args["n"]
    # ruleid: perun.py.path-traversal
    return Path("/srv/files/" + n).read_text()

def path_open():
    # ruleid: perun.py.path-traversal
    return pathlib.Path(request.args["n"]).open()

def path_read_bytes():
    # ruleid: perun.py.path-traversal
    return pathlib.Path(request.args["n"]).read_bytes()

def copy_src():
    # ruleid: perun.py.path-traversal
    shutil.copy(request.json["src"], "/srv/out")

def move_src():
    # ruleid: perun.py.path-traversal
    shutil.move(request.form["src"], "/srv/out")

def copy_dst():
    # ruleid: perun.py.path-traversal
    shutil.copy("/srv/in.txt", "/srv/out/" + request.args["n"])

def move_dst():
    # ruleid: perun.py.path-traversal
    shutil.move("/srv/in.txt", request.form["dst"])

def copytree_src():
    # ruleid: perun.py.path-traversal
    shutil.copytree(request.json["src"], "/srv/out")

def copytree_dst():
    # ruleid: perun.py.path-traversal
    shutil.copytree("/srv/in", request.json["dst"])

def rmtree_path():
    # ruleid: perun.py.path-traversal
    shutil.rmtree("/srv/" + request.args["n"])

def path_write_text():
    # ruleid: perun.py.path-traversal
    Path(request.args["n"]).write_text("x")

def path_write_bytes():
    # ruleid: perun.py.path-traversal
    pathlib.Path(request.args["n"]).write_bytes(b"x")

def path_unlink():
    # ruleid: perun.py.path-traversal
    Path("/srv/" + request.args["n"]).unlink()

def tainted_base_dir():
    # ruleid: perun.py.path-traversal
    return send_from_directory(request.args["d"], "report.pdf")

def guarded_path_read(ALLOW):
    n = request.args["n"]
    if n not in ALLOW:
        raise ValueError(n)
    # ok: perun.py.path-traversal
    return Path("/srv/files/" + n).read_text()

def guarded_copy(ALLOW):
    n = request.args["n"]
    if n not in ALLOW:
        return "no"
    # ok: perun.py.path-traversal
    shutil.copy("/srv/in.txt", "/srv/out/" + n)
    return "ok"

def guarded_base_dir(ALLOW):
    d = request.args["d"]
    if d not in ALLOW:
        raise ValueError(d)
    # ok: perun.py.path-traversal
    return send_from_directory(d, "report.pdf")

def safe_dir():
    # ok: perun.py.path-traversal
    return send_from_directory("/srv/files", request.args["name"])

def safe_secure_filename():
    # ok: perun.py.path-traversal
    return send_file("/srv/files/" + secure_filename(request.args["name"]))

def safe_basename():
    # ok: perun.py.path-traversal
    return open(os.path.join("/srv/files", os.path.basename(request.args["name"]))).read()

def safe_join_open():
    # ok: perun.py.path-traversal
    return open(safe_join("/srv/files", request.args["name"])).read()

def constant_path():
    # ok: perun.py.path-traversal
    return send_file("/srv/files/report.pdf")
'''


def annotated(body, kind):
    """Return {line number of the annotated NEXT line} for `# ruleid:`/`# ok:` comments naming ID."""
    return {i + 2 for i, l in enumerate(body.splitlines()) if re.match(rf"\s*# {kind}: {re.escape(ID)}$", l)}


want, ok = annotated(PY, "ruleid"), annotated(PY, "ok")
assert len(want) >= 20 and len(ok) >= 7, (len(want), len(ok))

# Offline pins: the rule keeps its sinks and sanitizers, and send_from_directory is never a sink.
rule = open(os.path.join(RULES, "py.yml")).read()
blk = rule[rule.index(f"- id: {ID}"):].split("\n- id: ")[0]
for s in ("send_file($S", "open($S", "os.path.join($B, $S)", "Path($S, ...).read_text", "Path($S, ...).open", "shutil.copy($S",
          "shutil.move($S", "secure_filename(...)", "os.path.basename(...)", "safe_join(...)"):
    assert s in blk, s
for s in ("shutil.copy($B, $S", "shutil.move($B, $S", "shutil.copytree($S", "shutil.rmtree($S", "Path($S, ...).write_text", "Path($S, ...).unlink"):
    assert s in blk, s
# send_from_directory is a sink on its first (base directory) argument only, never on the file name.
sinks = re.findall(r"- pattern: (send_from_directory\(.*\))", blk.split("pattern-sanitizers")[0].split("pattern-not-inside")[0])
assert sinks == ["send_from_directory($S, ...)"], sinks

if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "app.py"), "w").write(PY)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", "app.py"],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    got = {x["start"]["line"] for x in r["results"] if x["check_id"].endswith(ID)}
    assert got == want, ("unexpected", sorted(got - want), "missed", sorted(want - got))
    print("semgrep-py-pathtrav: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-py-pathtrav: ok")
