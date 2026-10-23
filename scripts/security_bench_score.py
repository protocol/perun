#!/usr/bin/env python3
"""Score security-review arms on the seeded-vulnerability fixtures (offline; no model is called).

usage: security_bench_score.py ARM=DIR [ARM=DIR ...] [--keys PATH] [--tol N]

Contract: each ARM dir holds one `<diff-id>.json` per diff in keys.json: a JSON list of findings
`{"file": str, "line": int, "cwe": "CWE-89" | "89" | 89 (optional)}`. An empty list means the arm reviewed that diff and
found nothing. A SARIF or tool report must be converted to this shape first (file = artifact path, line = region
startLine, cwe = the CWE tag if the tool gives one).
Matching: file by normalized suffix (a leading ./, a/ or b/ and absolute prefixes are ignored); CWE by integer id, equal to
the key's or to one of its `equiv` ids (parent/child pairs); line within --tol (default 1) of the key. A finding with no
cwe is scored on file+line only and the arm result carries `cwe_missing` (its count). Findings on the same file with the
same CWE within --tol of each other are collapsed before precision (`dup_findings` counts the collapsed ones). Per arm:
precision (TP / findings, null with none), recall (matched keys / seeded keys) with the bootstrap 95% CI from
rival_eval.boot, decoy_fp (decoy diffs with any finding / decoy diffs). Fails closed (exit 2): missing arm dir or
per-diff file, malformed findings (a bool or non-int line included), invalid keys, negative --tol, duplicate arm names.
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rival_eval import boot  # noqa: E402

KEYS = Path(__file__).resolve().parent / "eval-fixtures/security-seeded/keys.json"


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(2)


def cwe_id(x):
    """Integer CWE id from 'CWE-89', ' cwe-89', '89' or 89; None when absent or unparseable (bool is not an id)."""
    if isinstance(x, int) and not isinstance(x, bool):
        return x
    m = re.search(r"\d+", x) if isinstance(x, str) else None
    return int(m.group()) if m else None


def norm_path(p):
    p = re.sub(r"^(\./|[ab]/)+", "", p.strip().replace("\\", "/"))
    return p.lstrip("/")


def same_file(a, b):
    a, b = norm_path(a), norm_path(b)
    return a == b or a.endswith("/" + b) or b.endswith("/" + a)


def is_line(x):
    return isinstance(x, int) and not isinstance(x, bool)


def check_keys(keys):
    if not isinstance(keys, dict) or not keys:
        die("invalid keys: empty or not an object")
    for i, k in keys.items():
        if not isinstance(k, dict) or "cwe" not in k:
            die(f"invalid keys: {i} lacks cwe")
        if k["cwe"] is None:
            continue
        if cwe_id(k["cwe"]) is None or not isinstance(k.get("file"), str) or not is_line(k.get("line")):
            die(f"invalid keys: {i} needs a CWE id, file and int line")
        if not all(cwe_id(e) is not None for e in k.get("equiv", [])):
            die(f"invalid keys: {i} has a bad equiv")
    if all(k["cwe"] is None for k in keys.values()):
        die("invalid keys: no seeded vulnerability")


def load(arm_dir, ids):
    """Return {diff-id: findings}; exit 2 if the dir or any diff's file is missing or malformed."""
    d = Path(arm_dir)
    if not d.is_dir():
        die(f"missing arm dir: {d}")
    out = {}
    for i in ids:
        try:
            f = json.loads((d / f"{i}.json").read_text())
            assert isinstance(f, list)
            for x in f:
                assert isinstance(x, dict) and isinstance(x.get("file"), str) and is_line(x.get("line"))
                assert x.get("cwe") is None or isinstance(x["cwe"], (str, int))
        except (OSError, ValueError, AssertionError):
            die(f"missing or malformed findings for {i} in {d}")
        out[i] = f
    return out


def dedup(fs, tol):
    kept = []
    for f in fs:
        if not any(same_file(f["file"], g["file"]) and cwe_id(f.get("cwe")) == cwe_id(g.get("cwe"))
                   and abs(f["line"] - g["line"]) <= tol for g in kept):
            kept.append(f)
    return kept


def score(keys, found, tol=1):
    check_keys(keys)
    tp = n = dups = decoys = decoy_fp = nocwe = 0
    hits = []
    for i, k in keys.items():
        raw = found[i]
        fs = dedup(raw, tol)
        dups += len(raw) - len(fs)
        n += len(fs)
        nocwe += sum(cwe_id(f.get("cwe")) is None for f in fs)
        if k["cwe"] is None:
            decoys += 1
            decoy_fp += bool(fs)
            continue
        ok = {cwe_id(k["cwe"])} | {cwe_id(e) for e in k.get("equiv", [])}
        hit = any(same_file(f["file"], k["file"]) and cwe_id(f.get("cwe")) in ok | {None}
                  and abs(f["line"] - k["line"]) <= tol for f in fs)
        tp += hit
        hits.append(float(hit))
    lo, hi = boot(hits)
    r = {"precision": tp / n if n else None, "recall": tp / len(hits), "recall_ci95": [lo, hi], "findings": n,
         "dup_findings": dups, "true_positives": tp, "decoy_fp": f"{decoy_fp}/{decoys}"}
    if nocwe:
        r["cwe_missing"] = nocwe
    return r


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("arms", nargs="+", metavar="ARM=DIR")
    ap.add_argument("--keys", default=str(KEYS))
    ap.add_argument("--tol", type=int, default=1)
    a = ap.parse_args(argv)
    if a.tol < 0:
        die("--tol must be >= 0")
    try:
        keys = json.loads(Path(a.keys).read_text())
    except (OSError, ValueError) as e:
        die(f"unreadable keys: {e}")
    check_keys(keys)
    res = {}
    for spec in a.arms:
        name, _, d = spec.partition("=")
        if not d:
            die(f"bad arm spec (want ARM=DIR): {spec}")
        if name in res:
            die(f"duplicate arm name: {name}")
        res[name] = score(keys, load(d, keys), a.tol)
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
