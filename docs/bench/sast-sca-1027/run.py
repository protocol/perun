"""Scores raw scanner output against ground-truth.json; no network, no spend. Usage: python3 run.py (from this dir).
Arms: semgrep raw | Perun security_verify over semgrep | osv querybatch raw | Perun supply_chain_check gate."""
import hashlib, json, pathlib, subprocess, sys, re
H = pathlib.Path(__file__).resolve().parent
SV = H.parents[2] / ".claude/skills/deep-code-review/scripts/security_verify.py"
for ln in (H / "SHA256-frozen.txt").read_text().splitlines():
    h, p = ln.split(None, 1)
    assert hashlib.sha256((H / p.strip()).read_bytes()).hexdigest() == h, "frozen file drifted: " + p
T = json.loads((H / "ground-truth.json").read_text())
code = [t for t in T if t["kind"] == "code"]; deps = [t for t in T if t["kind"] == "dep"]

def score(items, hit_ids, unmapped=0):
    tp = sorted(i["id"] for i in items if i["vulnerable"] and i["id"] in hit_ids)
    fp = sorted(i["id"] for i in items if not i["vulnerable"] and i["id"] in hit_ids)
    fn = sorted(i["id"] for i in items if i["vulnerable"] and i["id"] not in hit_ids)
    return {"TP": len(tp), "FP": len(fp) + unmapped, "FN": len(fn), "tp": tp, "fp_decoys": fp, "fp_unmapped_rows": unmapped, "fn": fn}

def hits(rows):  # rows: dicts with path,line -> (item ids, unmapped count)
    ids, un = set(), 0
    for r in rows:
        m = [t["id"] for t in code if t["file"] == r["path"] and t["lines"][0] <= r["line"] <= t["lines"][1]]
        ids.update(m); un += not m
    return ids, un

sg = json.loads((H / "raw/semgrep.json").read_text())["results"]
rows = [{"path": r["path"], "line": r["start"]["line"], "rule": r["check_id"], "sev": r["extra"]["severity"],
         "tr": r["extra"].get("dataflow_trace")} for r in sg]
out = {"semgrep_raw": score(code, *hits(rows)), "semgrep_raw_rows": len(rows)}
# Perun deterministic layer: map each row to a security_verify row. source only if semgrep gave a taint trace.
sevmap = {"ERROR": "high", "WARNING": "medium", "INFO": "low"}
def loc(n): return "%s:%d" % (n["location"]["path"], n["location"]["start"]["line"])
fr = []
for r in rows:
    f = {"severity": sevmap[r["sev"]], "sink": "%s:%d" % (r["path"], r["line"]), "rule": r["rule"]}
    if r["tr"] and r["tr"].get("taint_source"):
        f["source"] = loc(r["tr"]["taint_source"][1]) if isinstance(r["tr"]["taint_source"], list) else None
    fr.append(f)
v = json.loads(subprocess.run([sys.executable, str(SV), "-", "/dev/null"], input=json.dumps(fr), capture_output=True, text=True, check=True).stdout)
st = {}
for x in v["rows"]: st[x["status"]] = st.get(x["status"], 0) + 1
keep = [{"path": x["sink"].rsplit(":", 1)[0], "line": int(x["sink"].rsplit(":", 1)[1])} for x in v["rows"] if x["status"] in ("confirmed", "needs-evidence")]
out["perun_sast_status_counts"] = st
out["semgrep_rows_with_dataflow_trace"] = sum(bool(r["tr"]) for r in rows)
out["perun_sast_reported_as_findings"] = score(code, *hits(keep))
# SCA
q = json.loads((H / "raw/osv-query.json").read_text())["queries"]; res = json.loads((H / "raw/osv-querybatch.json").read_text())["results"]
flag = {q[i]["package"]["name"] for i, r in enumerate(res) if r.get("vulns")}
out["osv_raw"] = score(deps, {d["id"] for d in deps if d["package"] in flag})
# supply_chain_check.sh prints every advisory at any --fail-on and only sets the exit code, so the level filter below
# is a SIMULATION of its threshold rule (unknown fails closed) over the saved output of a real run at each level.
def sca(lvl, items):
    ok = {"critical": {"critical", "unknown"}, "high": {"critical", "high", "unknown"}}[lvl]
    lines = [l.split() for l in (H / ("raw/supply_chain_%s.txt" % lvl)).read_text().splitlines() if re.match(r"\s+(critical|high|moderate|unknown) ", l)]
    pk = {l[1].split("@")[0] for l in lines if l[0] in ok}
    return score(items, {d["id"] for d in items if d["package"] in pk})
for lvl in ("critical", "high"):
    out["perun_sca_simulated_fail_on_" + lvl] = sca(lvl, deps)
# Relabel: requests 2.32.4 (D16) and js-yaml 4.1.0 (D18) carry real OSV advisories, so they are not safe decoys.
rel = [d for d in deps if d["id"] not in ("D16", "D18")]
out["results_relabeled"] = {"osv_raw": score(rel, {d["id"] for d in rel if d["package"] in flag}),
    **{"perun_sca_simulated_fail_on_" + l: sca(l, rel) for l in ("critical", "high")}}
(H / "results.json").write_text(json.dumps(out, indent=1) + "\n")
def show(o, p=""):
    for k, x in o.items():
        if isinstance(x, dict) and "TP" not in x: show(x, p + k + ".")
        else: print(p + k, {a: b for a, b in x.items() if a in ("TP", "FP", "FN")} if isinstance(x, dict) else x)
show(out)
