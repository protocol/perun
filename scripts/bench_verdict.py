#!/usr/bin/env python3
"""Outcome-first verdict for a Perun-vs-rival comparison, plus the doc gate that enforces it.

verdict(spec) takes preference scores (per-item in [0, 1], or wins/ties/losses with a tie = 0.5), optional
cost per item for each arm, and an optional user-felt outcome metric. It returns one label:

  WIN                                          preference CI lower bound > 0.5, cost measured with Perun <= rival, outcome
                                               measured and not worse; OR a tie (lower bound <= 0.5) with the CI inside
                                               0.5 +/- equiv_margin (default 0.10, `--equiv-margin`), Perun strictly
                                               cheaper, and outcome diff_ci (perun minus rival) not worse beyond
                                               outcome.margin (default 0)
  PREFERENCE-ONLY WIN (cost/outcome unmeasured)  lower bound > 0.5 but cost or outcome missing
  WIN ON PROXY, OUTCOME WORSE                  lower bound > 0.5, outcome measured and worse
  WIN ON PROXY, COST HIGHER                    lower bound > 0.5, outcome fine, Perun costs more
  LOSS                                         CI upper bound < 0.5
  UNDERPOWERED                                 fewer than MIN_N (10) scored items: a bootstrap of 3 straight wins
                                               has a CI of [1, 1] and proves nothing
  PARITY                                       everything else

The CI is rival_eval.boot (percentile bootstrap of the mean, seed 1), reused so every bench shares one rule.
Edge cases: no items raises ValueError; cost_per_item/outcome need both arms as finite numbers (missing, string,
NaN or infinite count as unmeasured, never a Win).

`bench_verdict.py spec.json` prints the verdict JSON. `bench_verdict.py --check-doc docs/perun-vs-rivals.md`
exits 1 if a Verdict*/Result* cell claims a Win without `cost $A vs $B` (A <= B) plus
`outcome <name> X vs Y (higher|lower) is better` (X not worse than Y), or a
`bench: docs/bench/<dir>` whose verdict_spec.json recomputes to WIN, or labels a preference-only win without "unmeasured".
`bench_verdict.py --cost results.json` prints per-arm cost per item and the Perun/rival ratio (see cost_report). Exit codes:
0 Perun cost <= rival cost, 1 Perun costs more, 2 usage error (no file argument), 3 unmeasured (no usage, partial, mixed units). Reads files only.
"""
import functools
import json
import math
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from rival_eval import boot  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

_boot = functools.lru_cache(maxsize=None)(lambda vals: boot(list(vals)))  # 10,000 resamples; benches repeat inputs

PREF_ONLY = "PREFERENCE-ONLY WIN (cost/outcome unmeasured)"
MIN_N = 10


def _scores(spec):
    if "items" in spec:
        vals = [float(x) for x in spec["items"]]
    else:
        vals = [1.0] * spec["wins"] + [0.5] * spec["ties"] + [0.0] * spec["losses"]
    if not vals or any(not 0 <= v <= 1 for v in vals):
        raise ValueError("need at least one score, each in [0, 1]")
    return vals


def _num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def _pair(d):
    """True when d is a dict with finite numeric perun and rival values; anything else is unmeasured."""
    return isinstance(d, dict) and _num(d.get("perun")) and _num(d.get("rival"))


def _tie_win(cost, out, lo, hi, margin):
    """A parity tie counts as a win only if the CI sits inside +/-margin of 0.5, Perun costs strictly less,
    and the outcome is not worse: point estimate >= 0 and its diff_ci [lo, hi] (perun minus rival) lower
    end >= -out["margin"] (default 0). Without a diff_ci the outcome cannot be shown not worse."""
    ci = out.get("diff_ci")
    if not (lo >= 0.5 - margin and hi <= 0.5 + margin and cost["perun"] < cost["rival"]):
        return False
    if not (isinstance(ci, list) and len(ci) == 2 and all(_num(c) for c in ci)):
        return False
    sign = 1 if out.get("higher_is_better", True) else -1
    slack = out["margin"] if _num(out.get("margin")) else 0
    return sign * (out["perun"] - out["rival"]) >= 0 and min(sign * c for c in ci) >= -slack


def verdict(spec, equiv_margin=0.10):
    """Return {verdict, mean, lo, hi, n} for one comparison spec (see module docstring).

    cost_per_item and outcome with a missing, non-numeric, NaN or infinite perun/rival are unmeasured."""
    if not _num(equiv_margin) or equiv_margin < 0:
        raise ValueError("equiv_margin must be a finite number >= 0")
    vals = _scores(spec)
    lo, hi = _boot(tuple(vals))
    if len(vals) < MIN_N:
        return {"verdict": "UNDERPOWERED", "mean": sum(vals) / len(vals), "lo": lo, "hi": hi, "n": len(vals)}
    cost, out = spec.get("cost_per_item"), spec.get("outcome")
    measured = _pair(cost) and _pair(out) and cost["perun"] >= 0 and cost["rival"] >= 0
    if hi < 0.5:
        label = "LOSS"
    elif lo <= 0.5:
        label = "WIN" if measured and _tie_win(cost, out, lo, hi, equiv_margin) else "PARITY"
    elif not measured:
        label = PREF_ONLY
    elif (1 if out.get("higher_is_better", True) else -1) * (out["perun"] - out["rival"]) < 0:
        label = "WIN ON PROXY, OUTCOME WORSE"
    elif cost["perun"] > cost["rival"]:
        label = "WIN ON PROXY, COST HIGHER"
    else:
        label = "WIN"
    return {"verdict": label, "mean": sum(vals) / len(vals), "lo": lo, "hi": hi, "n": len(vals)}


_NOT_A_WIN = re.compile(r"(?i)\b(not a|no|not|never)\s+wins?\b|\bwins?\s+not\s+(?:replicated|confirmed|significant)\b|\bwin[ -]rates?\b|\bnon-wins?\b|\bpreference-only win\b")
_WIN = re.compile(r"(?i)\b(win|wins|won|winner|winners|winning)\b")
_COST = re.compile(r"(?i)\bcost \$(\d*\.?\d+) vs \$(\d*\.?\d+)")
_OUTCOME = re.compile(r"(?i)\boutcome\s+[a-z_][\w -]*?\s+(-?\d*\.?\d+)\s+vs\s+(-?\d*\.?\d+)\s+\((higher|lower) is better\)")
_BENCH = re.compile(r"(?i)\bbench: docs/bench/([\w-]+)")
_GATED = re.compile(r"(?i)(verdict|result)")
_SEP = re.compile(r"^\|?(\s*:?-{3,}:?\s*\|)+\s*:?-{0,}:?\s*$")


def _bench_wins(name, root):
    """True if docs/bench/<name>/verdict_spec.json exists and bench_verdict recomputes it as WIN."""
    try:
        return verdict(json.loads((root / "docs/bench" / name / "verdict_spec.json").read_text()))["verdict"] == "WIN"
    except (OSError, ValueError, KeyError, TypeError):
        return False


def _table_row(line):
    """The line as a table row ("|...") after any indent or blockquote markers, else ""."""
    row = re.sub(r"^[\s>]*", "", line)
    return row if row.startswith("|") else ""


@functools.lru_cache(maxsize=None)
def _bench_dirs(root):
    """Regex matching the name (and any path below it) of a directory that exists under root/docs/bench."""
    names = sorted((d.name for d in (root / "docs/bench").glob("*") if d.is_dir()), key=len, reverse=True)
    alt = "|".join(map(re.escape, names)) or r"(?!)"
    return re.compile(rf"(?:docs/bench/)?\b(?:{alt})\b(?:/[\w./-]*)?")


def _cell_ok(cell, root):
    if re.search(r"(?i)preference-only win", cell) and not re.search(r"(?i)unmeasured", cell):
        return False
    def real(m):  # drop a real bench dir name; keep a path below it unless that path exists
        path = m[0].removeprefix("docs/bench/").rstrip("/./")
        sub = path.partition("/")[2]
        return "" if not sub or (root / "docs/bench" / path).exists() else sub
    if not _WIN.search(_NOT_A_WIN.sub("", _bench_dirs(root).sub(real, cell))):  # real bench paths are not claims
        return True
    cost, out = _COST.search(cell), _OUTCOME.search(cell)
    if cost and out and float(cost[1]) <= float(cost[2]):
        sign = 1 if out[3].lower() == "higher" else -1
        return sign * (float(out[1]) - float(out[2])) >= 0
    return any(_bench_wins(n, root) for n in _BENCH.findall(cell))


def check_doc(text, root=REPO):
    """Return the table rows (as text) with a win claim in a Verdict*/Result* column and no structured evidence.

    A Win needs `cost $A vs $B` (Perun A <= rival B) and `outcome <name> X vs Y`, or `bench: docs/bench/<dir>`
    whose verdict_spec.json recomputes to WIN. "Preference-only win" must say unmeasured. Negated mentions
    ("not a win", "win not replicated") and "win rate" are ignored. root is the repo root for bench specs."""
    bad, cols, seen_sep = [], [], False
    lines = text.splitlines()
    for k, line in enumerate(lines):
        line = _table_row(line)
        if not line:
            cols, seen_sep = [], False
            continue
        if _SEP.match(line):
            seen_sep = True
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if not seen_sep and k + 1 < len(lines) and _SEP.match(_table_row(lines[k + 1])):  # header: row above the first separator
            cols = [i for i, c in enumerate(cells) if _GATED.search(c)]
            continue
        if any(i < len(cells) and not _cell_ok(cells[i], root) for i in cols):
            bad.append(line[:80])
    return bad


def cost_report(res):
    """Per-arm cost per item and the Perun/rival ratio from a rival_eval results.json `cost_per_arm`, plus the cost check
    (Perun <= rival). Unit is dollars when an arm has a positive spend_usd, else generator tokens (prompt + completion); arms
    whose units differ are unmeasured. Arms with no usage, or with only some items measured, are unmeasured: ok is None, never guessed."""
    arms = res.get("cost_per_arm") or {}
    per = {}
    for a in ("PERUN", "RIVAL"):
        c = arms.get(a) or {}
        if not c.get("n_measured") or c["n_measured"] != c.get("n_items"):
            return {"unit": None, "ok": None, "reason": f"{a} cost unmeasured"}
        per[a] = c
    units = {a: "usd" if (c.get("spend_usd") or 0) > 0 else "tokens" for a, c in per.items()}
    if len(set(units.values())) > 1:
        return {"unit": None, "ok": None, "reason": f"arm units differ: {units}"}
    unit = units["PERUN"]
    each = {a: (c["spend_usd"] if unit == "usd" else c["prompt_tokens"] + c["completion_tokens"]) / c["n_measured"] for a, c in per.items()}
    if not each["RIVAL"]:  # no ratio; Perun > 0 costs more, both zero means nothing was measured
        return {"unit": unit, "per_item": each, "ratio": None, "ok": False if each["PERUN"] else None, "reason": "RIVAL cost is zero"}
    return {"unit": unit, "per_item": each, "ratio": each["PERUN"] / each["RIVAL"], "ok": each["PERUN"] <= each["RIVAL"]}


def main(argv):
    if argv[:1] == ["--cost"]:
        if len(argv) != 2:
            print("usage: bench_verdict.py --cost results.json", file=sys.stderr)
            return 2
        try:
            rep = cost_report(json.loads(Path(argv[1]).read_text()))
        except (OSError, ValueError, AttributeError, KeyError, TypeError) as e:  # unreadable results: unmeasured, never "costs more"
            print(f"cost unmeasured: {type(e).__name__}: {e}", file=sys.stderr)
            return 3
        print(json.dumps(rep, indent=2))
        return 3 if rep["ok"] is None else 0 if rep["ok"] else 1
    if argv[:1] == ["--check-doc"]:
        bad = check_doc(Path(argv[1]).read_text())
        for row in bad:
            print("Win without structured cost and outcome evidence:", row)
        return 1 if bad else 0
    margin = 0.10
    if "--equiv-margin" in argv:
        i = argv.index("--equiv-margin")
        margin = float(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    print(json.dumps(verdict(json.loads(Path(argv[0]).read_text()), margin), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
