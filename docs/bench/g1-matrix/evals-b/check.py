import json, os, re, sys
root = os.path.dirname(os.path.abspath(__file__))
ev = json.load(open(os.path.join(root, "evals.json")))
banned = re.compile(r"vuln|insecure|unsafe|safe|todo|flaw|fixme|exploit", re.I)
err = []
for e in ev:
    d = os.path.join(root, e["dir"])
    if not os.path.isdir(d):
        err.append(f"missing dir {d}"); continue
    files = [f for f in os.listdir(d)]
    if not 1 <= len(files) <= 3: err.append(f"{e['id']}: file count")
    for f in files:
        txt = open(os.path.join(d, f)).read()
        if len(txt.splitlines()) > 60: err.append(f"{e['id']}/{f}: >60 lines")
        if banned.search(txt) or banned.search(f): err.append(f"{e['id']}/{f}: banned word")
    if (e["kind"] == "pos") != bool(e.get("truth")): err.append(f"{e['id']}: truth/kind")
    for t in e.get("truth", []):
        p = os.path.join(d, t["file"])
        if not os.path.isfile(p): err.append(f"{e['id']}: no file {t['file']}"); continue
        ls = open(p).read().splitlines()
        if not 1 <= t["line"] <= len(ls) or not ls[t["line"] - 1].strip(): err.append(f"{e['id']}: bad line {t['line']}")
for it in sorted({e["item"] for e in ev}):
    k = [e["kind"] for e in ev if e["item"] == it]
    if k.count("pos") < 2 or k.count("neg") < 1: err.append(f"{it}: need >=2 pos, >=1 neg")
print("FAIL" if err else "OK", *err, sep="\n" if err else " ")
print(len(ev), "fixtures")
sys.exit(1 if err else 0)
