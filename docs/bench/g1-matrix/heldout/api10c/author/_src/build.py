import json, os, sys
sys.path.insert(0, os.path.dirname(__file__))
import b1
import b2
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
out = []
for i, (kind, lang, fw, files) in enumerate(b1.C, 1):
    cid = f"h10c-{i:02d}"
    tf = tl = None
    for name, text in files.items():
        lines = []
        for n, ln in enumerate(text.rstrip("\n").split("\n"), 1):
            if "§T" in ln:
                tf, tl = f"{name}", n
                ln = ln.replace("§T", "").rstrip()
            lines.append(ln)
        d = os.path.join(root, "cases", cid)
        os.makedirs(d, exist_ok=True)
        open(os.path.join(d, name), "w").write("\n".join(lines) + "\n")
    e = {"id": cid, "kind": kind, "language": lang, "framework": fw}
    if kind == "pos":
        e["truth_file"] = f"cases/{cid}/{tf}"; e["truth_line"] = tl
    out.append(e)
json.dump(out, open(os.path.join(root, "cases.json"), "w"), indent=1)
print(len(out))
