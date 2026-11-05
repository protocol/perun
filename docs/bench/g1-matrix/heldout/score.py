#!/usr/bin/env python3
"""Score a G1 held-out set (heldout/RULES.md, "Run and score"). Deterministic, no model calls.

Usage: score_heldout.py ITEM REPO SHA SETDIR OUT.json
ITEM is api1, api3, api5 or api10. The detector is taken from REPO at SHA by `git archive`, so the working tree can't leak in.
Each case dir is scanned on its own in one pass. A positive is a TP when a report names the truth file within 3
lines of the truth line (at most one TP per case); every other report is an FP, in-window duplicates included.
"""
import hashlib, io, json, os, subprocess, sys, tarfile, tempfile
from pathlib import Path

SK = ".claude/skills/deep-code-review"


def run(*a, **k):
    return subprocess.run(a, capture_output=True, text=True, timeout=300, **k)


def env():
    h = tempfile.mkdtemp(prefix="hs-home-")
    return {**os.environ, "HOME": h, "XDG_CACHE_HOME": h, "SEMGREP_USER_HOME": h}


def semgrep_rows(tools, case, suffixes):
    rows = []
    for cfg in ("js.yml", "py.yml"):
        r = run("semgrep", "--config", str(tools / "templates/semgrep-taint" / cfg), "--metrics=off",
                "--disable-version-check", "--json", "-q", str(case), env=env())
        assert r.returncode in (0, 1), r.stderr
        rows += [(Path(x["path"]).resolve().relative_to(case.resolve()).as_posix(), x["start"]["line"])
                 for x in json.loads(r.stdout)["results"] if x["check_id"].endswith(suffixes)]
    return sorted(set(rows))


def api3(tools, case):
    return semgrep_rows(tools, case, ("mass-assignment",))


def api10(tools, case):
    return semgrep_rows(tools, case, ("unsafe-api-consumption", "tls-verify-off"))


def api1(tools, case):
    r = run(sys.executable, "-I", str(tools / "scripts/ownership_sibling_check.py"), ".", cwd=case)
    assert r.returncode == 0, r.stderr
    return sorted({(norm(l.split(":")[0], case.name), int(l.split(":")[1])) for l in r.stdout.splitlines() if ": OWNERSHIP: " in l})


def api5(tools, case):
    r = run(sys.executable, "-I", str(tools / "scripts/route_auth_map.py"), "--privileged", str(case))
    assert r.returncode == 0, r.stderr
    return sorted({(l.split(":")[0], int(l.split(":")[1])) for l in r.stdout.splitlines() if ": PRIV: " in l})


def norm(p, cid):
    p = p.removeprefix("./")
    return p.split(f"{cid}/", 1)[-1]


def main(item, repo, sha, setdir, out):
    setdir = Path(setdir)
    tools = Path(tempfile.mkdtemp(prefix="hs-tools-")) / SK
    tar = subprocess.run(["git", "-C", repo, "archive", sha, f"{SK}/scripts", f"{SK}/templates/semgrep-taint"],
                         capture_output=True, check=True).stdout
    tarfile.open(fileobj=io.BytesIO(tar)).extractall(tools.parents[2], filter="data")
    det = {"api1": api1, "api3": api3, "api5": api5, "api10": api10}[item]
    cases = json.loads((setdir / "cases.json").read_text())
    tp, reports, per = 0, 0, []
    for c in cases:
        rows = det(tools, setdir / "cases" / c["id"])
        hit = None
        if c["kind"] == "pos":
            tf = norm(c["truth_file"], c["id"])
            hit = next((r for r in rows if r[0] == tf and abs(r[1] - c["truth_line"]) <= 3), None)
        tp += hit is not None
        reports += len(rows)
        per.append({"id": c["id"], "kind": c["kind"], "tp": hit is not None,
                    "fp": [list(r) for r in rows if r != hit], "reports": [list(r) for r in rows]})
    npos = sum(c["kind"] == "pos" for c in cases)
    files = sorted(p for p in (setdir / "cases").rglob("*") if p.is_file())
    sv = run("semgrep", "--version", env=env()).stdout.strip() if item in ("api3", "api10") else None
    res = {"item": item, "detector_sha": sha, "semgrep": sv, "cases": len(cases), "positives": npos,
           "tp": tp, "reports": reports, "precision": round(tp / reports, 3) if reports else None,
           "recall": round(tp / npos, 3), "kill": bool(reports) and tp / reports < 0.7,
           "set_sha256": {p.relative_to(setdir).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                          for p in [setdir / "cases.json", *files]},
           "per_case": per}
    Path(out).write_text(json.dumps(res, indent=1) + "\n")
    print(item, "tp", tp, "reports", reports, "precision", res["precision"], "recall", res["recall"], "kill", res["kill"])


if __name__ == "__main__":
    main(*sys.argv[1:])
