import json, os, re
R = os.path.dirname(os.path.abspath(__file__))
cs = json.load(open(os.path.join(R, "cases.json")))
BAN = re.compile(r"vuln|insecure|unsafe|safe|todo|fixme|exploit|flaw|idor|bola|owasp|\bapi\d", re.I)
err = []
pos = [c for c in cs if c["kind"] == "pos"]; neg = [c for c in cs if c["kind"] == "neg"]
if len(cs) != 30 or len(pos) != 15 or len(neg) != 15: err.append("counts")
for c in cs:
    d = os.path.join(R, "cases", c["id"])
    fs = sorted(os.listdir(d))
    if not 1 <= len(fs) <= 3: err.append(f"{c['id']} files {len(fs)}")
    tot = 0
    for f in fs:
        t = open(os.path.join(d, f)).read(); n = len(t.splitlines()); tot += n
        if BAN.search(t): err.append(f"{c['id']}/{f} banned {BAN.search(t).group()}")
        if "§" in t: err.append(f"{c['id']}/{f} marker")
        if re.search(r"verify\s*=\s*False|rejectUnauthorized:\s*false|TLS_REJECT_UNAUTHORIZED", t) and c["kind"] == "neg": err.append(f"{c['id']} neg TLS off")
    if not 15 <= tot <= 80: err.append(f"{c['id']} lines {tot}")
    if c["kind"] == "pos":
        p = os.path.join(R, c["truth_file"])
        L = open(p).read().splitlines()
        if not os.path.exists(p) or not 1 <= c["truth_line"] <= len(L): err.append(f"{c['id']} truth missing")
    elif "truth_line" in c: err.append(f"{c['id']} neg has truth")
from collections import Counter
print(Counter((c["kind"], c["language"]) for c in cs))
print("ERRORS" if err else "CLEAN", err)
