import json, os, re, sys
R = os.path.dirname(os.path.abspath(__file__))
cs = json.load(open(f"{R}/cases.json")); bad = []
ban = re.compile(r"vuln|insecure|safe|todo|fixme|exploit|flaw|idor|bola|owasp|api[0-9]", re.I)
pos = [c for c in cs if c["kind"] == "pos"]; neg = [c for c in cs if c["kind"] == "neg"]
if (len(cs), len(pos), len(neg)) != (30, 15, 15): bad.append("counts")
for c in cs:
    d = f"{R}/cases/{c['id']}"; fs = os.listdir(d); tot = 0
    if not 1 <= len(fs) <= 3: bad.append(f"{c['id']} files")
    for f in fs:
        t = open(f"{d}/{f}").read(); tot += len(t.splitlines())
        m = ban.search(t)
        if m: bad.append(f"{c['id']}/{f} banned {m.group()}")
        if "§" in t: bad.append(f"{c['id']} marker left")
    if not 15 <= tot <= 80: bad.append(f"{c['id']} lines {tot}")
    if c["kind"] == "pos":
        p = f"{R}/{c['truth_file']}"
        if not os.path.exists(p) or c["truth_line"] > len(open(p).read().splitlines()): bad.append(f"{c['id']} truth")
    elif "truth_file" in c: bad.append(f"{c['id']} neg truth")
for k in ("language", "framework"):
    print(k, {v: sum(1 for c in cs if c[k] == v) for v in sorted({c[k] for c in cs})})
print("pos", len(pos), "neg", len(neg), "BAD" if bad else "CLEAN", bad)
sys.exit(1 if bad else 0)
