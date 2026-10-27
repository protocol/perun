"""Writes ground-truth.json from the frozen fixture. Each code item is a function/handler block: [lo, hi] lines.
Run once BEFORE any scanner; run.py re-checks fixture SHA256 against SHA256-frozen.txt."""
import json, pathlib, re
F = pathlib.Path(__file__).parent / "fixture"
# (id, file, snippet identifying the block, vulnerable?, class)
CODE = [
 ("V01","py/db_routes.py","def find_user_by_name",1,"sqli"),
 ("V02","py/db_routes.py","def find_orders_by_status",1,"sqli"),
 ("V03","py/ops_routes.py","def ping_host",1,"command-injection"),
 ("V04","py/ops_routes.py","def archive_report",1,"command-injection"),
 ("V05","py/ops_routes.py","def read_report(",1,"path-traversal"),
 ("V06","py/ops_routes.py","def fetch_remote",1,"ssrf"),
 ("V07","py/ops_routes.py","def load_session",1,"unsafe-deserialize"),
 ("V08","py/ops_routes.py","def load_settings_text",1,"unsafe-deserialize"),
 ("V09","js/server.js",'app.get("/user",',1,"sqli"),
 ("V10","js/server.js",'app.get("/convert"',1,"command-injection"),
 ("V11","js/server.js",'app.get("/doc"',1,"path-traversal"),
 ("V12","js/server.js",'app.get("/proxy",',1,"ssrf"),
 ("V13","js/server.js",'app.get("/calc"',1,"code-injection"),
 ("D01","py/db_routes.py","def find_user_by_id",0,"parameterized-query"),
 ("D02","py/db_routes.py","def find_orders_by_customer",0,"parameterized-query"),
 ("D03","py/db_routes.py","def count_orders",0,"constant-concat"),
 ("D04","py/ops_routes.py","def disk_usage",0,"constant-shell"),
 ("D05","py/ops_routes.py","def list_reports",0,"constant-argv"),
 ("D06","py/ops_routes.py","def read_named_report",0,"allowlisted-path"),
 ("D07","py/ops_routes.py","def fetch_status",0,"constant-url"),
 ("D08","py/ops_routes.py","def fetch_allowed",0,"allowlisted-host"),
 ("D09","py/ops_routes.py","def load_settings_safe",0,"safe-loader"),
 ("D10","js/server.js",'app.get("/user-safe"',0,"parameterized-query"),
 ("D11","js/server.js",'app.get("/version"',0,"constant-argv"),
 ("D12","js/server.js",'app.get("/legal"',0,"allowlisted-path"),
 ("D13","js/server.js",'app.get("/proxy-safe"',0,"allowlisted-host"),
 ("D14","js/server.js",'app.get("/config"',0,"json-parse-not-eval"),
]
DEPS = [("V14","pyyaml","5.3","PyPI",1),("V15","jinja2","2.11.2","PyPI",1),("V16","lodash","4.17.15","npm",1),
        ("V17","minimist","1.2.0","npm",1),("D15","markupsafe","2.1.5","PyPI",0),("D16","requests","2.32.4","PyPI",0),
        ("D17","semver","7.5.4","npm",0),("D18","js-yaml","4.1.0","npm",0)]
items = []
for i, f, snip, vuln, cls in CODE:
    L = (F / f).read_text().split("\n")
    n = next(k for k, s in enumerate(L, 1) if snip in s)
    lo = n
    while lo > 1 and L[lo - 2].strip(): lo -= 1
    hi = n
    while hi < len(L) and L[hi].strip(): hi += 1
    items.append({"id": i, "kind": "code", "file": f, "lines": [lo, hi], "vulnerable": bool(vuln), "class": cls})
for i, name, ver, eco, vuln in DEPS:
    items.append({"id": i, "kind": "dep", "package": name, "version": ver, "ecosystem": eco, "vulnerable": bool(vuln)})
(pathlib.Path(__file__).parent / "ground-truth.json").write_text(json.dumps(items, indent=1) + "\n")
print(len(items), sum(x["vulnerable"] for x in items))
