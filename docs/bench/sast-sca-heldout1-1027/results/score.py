"""Scores raw/semgrep-{A,B,C}.json against ../ground-truth.json. Match: finding path == item file and line == item sink line.
Arms B-post/C-post: post-review rules (d9e6fbfbb); C-post reuses raw A. Usage: python3 score.py (from this dir). No network."""
import json, pathlib
H = pathlib.Path(__file__).resolve().parent
T = json.loads((H.parent / "ground-truth.json").read_text())
def score(tol, arm):
    rows = json.loads((H / f"raw/semgrep-{arm}.json").read_text())["results"]
    hit, un = set(), []
    for r in rows:
        m = [t["id"] for t in T if t["file"] == r["path"] and abs(t["line"] - r["start"]["line"]) <= tol]
        hit.update(m)
        if not m: un.append(f'{r["path"].split("/")[-1]}:{r["start"]["line"]} {r["check_id"].split(".")[-1]}')
    v = [t for t in T if t["label"] == "vuln"]; d = [t for t in T if t["label"] == "decoy"]
    tp = sorted(t["id"] for t in v if t["id"] in hit); fpd = sorted(t["id"] for t in d if t["id"] in hit)
    fn = sorted(t["id"] for t in v if t["id"] not in hit)
    return {"rows": len(rows), "TP": len(tp), "FP": len(fpd) + len(un), "FN": len(fn), "tp": tp, "fp_decoys": fpd, "fp_unmapped_rows": un, "fn": fn,
            "fn_by_class": {c: sum(t["class"] == c for t in v if t["id"] in fn) for c in sorted({t["class"] for t in v})}}
out = {"match_rule_primary": "same file, row start line == sink line", "arms": {a: score(0, a) for a in "ABC"},
       "sensitivity_line_tolerance_2": {a: {k: score(2, a)[k] for k in ("TP", "FP", "FN")} for a in "ABC"}}
for a in ("B-post", "C-post"): out["arms"][a] = score(0, a)
out["sensitivity_line_tolerance_2"].update({a: {k: score(2, a)[k] for k in ("TP", "FP", "FN")} for a in ("B-post", "C-post")})
(H / "results.json").write_text(json.dumps(out, indent=1) + "\n")
for a, x in out["arms"].items(): print(a, {k: x[k] for k in ("rows", "TP", "FP", "FN")}, "decoys", x["fp_decoys"], "fn", x["fn"])
print(out["sensitivity_line_tolerance_2"])
