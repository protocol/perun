#!/usr/bin/env python3
"""G1 pilot ablation for the status (b) items (API1, API3, API5, API10). Protocol: ABLATION.md in this directory.

  ablate.py freeze                 fill the "Frozen inputs" section of ABLATION.md (no model calls)
  ablate.py run --out DIR [--cap]  stripped arm, step arm, confirmation; raw answers, spend and utilization go to DIR
  ablate.py score TEXT_FILE ID     score one saved answer against fixture ID (prints pass/fail)

Exit codes for run: 0 finished, 2 infrastructure fault (attempt void), 3 stopped by cap or quota (open items stay unstatused).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import rival_eval as R  # noqa: E402  (claude_call, State, Stop, CLAUDE_MODEL, QUOTA_STOP)
R.CLAUDE_MODEL = "sonnet"  # fixed before any call: the project's default lane model; rival_eval's haiku default would weaken the stripped arm and favor (b)

SKILL = ROOT / ".claude/skills/deep-code-review/SKILL.md"
REF = ROOT / ".claude/skills/deep-code-review/references/security-api.md"
EVALS = HERE / "evals-b/evals.json"
ABLATION = HERE / "ABLATION.md"
LEADS = ("**API1 + API5", "**API3", "**API10")
CAP = 15.0
S, T = "stripped", "step"
INSTRUCTION = ("Review the files above for security flaws that fall under the OWASP API Security Top 10:2023 classes listed. "
               "Write a short review, then end your answer with exactly one fenced ```json block holding a list of findings, "
               'each {"file": "<file name>", "line": <number>, "owasp_api_2023": "<label, API1 to API10>"}. '
               "Use an empty list when you find none.")


def stripped(ref):
    """The reference with the three item paragraphs (bold lead to the next blank line) removed; nothing else changes."""
    return "\n\n".join(p for p in ref.split("\n\n") if not p.startswith(LEADS))


def system_prompt(arm):
    ref = REF.read_text()
    return SKILL.read_text() + "\n\n" + (stripped(ref) if arm == S else ref)


def labels():
    d = json.loads((ROOT / "docs/bench/g1-matrix/items.json").read_text())["lists"]["OWASP-API-Top10-2023"]["items"]
    return "\n".join(f"API{i['id'].split(':')[0][3:]}: {i['title']}" for i in d)


def user_prompt(ev):
    d = HERE / "evals-b" / ev["dir"]
    files = "\n\n".join(f"### {f.name}\n```\n{f.read_text()}\n```" for f in sorted(d.iterdir()))
    return f"{files}\n\nClasses:\n{labels()}\n\n{INSTRUCTION}"


def label(v):
    m = re.match(r"\s*API\s*0*(\d+)\b", str(v))
    return f"API{m.group(1)}" if m else None


def findings(txt):
    """Findings of the last fenced block; unparseable output is no findings (never re-asked)."""
    blocks = re.findall(r"```(?:json)?\s*(\[.*?\])\s*```", txt or "", re.S)
    try:
        out = json.loads(blocks[-1])
        return [f for f in out if isinstance(f, dict)] if isinstance(out, list) else []
    except (IndexError, ValueError):
        return []


def score(txt, ev):
    """True when a positive names a finding with the truth file and the item label, or a negative has no finding with the label."""
    hits = [f for f in findings(txt) if label(f.get("owasp_api_2023")) == ev["item"]]
    if ev["kind"] == "neg":
        return not hits
    return any(os.path.basename(str(f.get("file"))) == t["file"] for f in hits for t in ev["truth"])


def decide(call, evals):
    """Protocol order and stop rule. call(arm, ev, n) -> bool pass. Raises R.Stop; partial results are in `res`."""
    res = {}

    def run(arm, ev, n=1):
        res.setdefault((arm, ev["id"]), [])
        while len(res[(arm, ev["id"])]) < n:
            res[(arm, ev["id"])].append(call(arm, ev, len(res[(arm, ev["id"])])))
        return res[(arm, ev["id"])]
    maj = lambda v: sum(v) * 2 > len(v)  # noqa: E731
    verdict = {}
    try:
        for ev in evals:
            run(S, ev)
        for it in dict.fromkeys(e["item"] for e in evals):
            fx = [e for e in evals if e["item"] == it]
            if all(res[(S, e["id"])][0] for e in fx):
                verdict[it] = "not_b: stripped arm passes every fixture"
                continue
            verdict[it] = "undecided"
            for e in fx:
                run(T, e)
            cand = [e for e in fx if res[(T, e["id"])][0] and not res[(S, e["id"])][0]]
            for e in cand:
                run(T, e, 3)
                run(S, e, 3)
            disc = [e["id"] for e in cand if maj(res[(T, e["id"])]) and not maj(res[(S, e["id"])])]
            ok = all(maj(res[(T, e["id"])]) for e in fx)
            verdict[it] = "b" if ok and disc else "not_b: " + ("step arm fails a fixture" if not ok else "no discriminating fixture")
    except R.Stop:
        verdict.update({it: "undecided" for it in dict.fromkeys(e["item"] for e in evals) if it not in verdict or verdict[it] == "undecided"})
        raise
    finally:
        decide.last = ({f"{a}/{i}": v for (a, i), v in res.items()}, verdict)
    return decide.last[1]


def reserve_for(sysm, usr):
    return max(0.30, round(0.1 + (len(sysm) + len(usr)) / 4 * 2e-5, 2))


def run_cmd(a):
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        sys.exit("refusing: --out is not empty (one attempt only)")
    (out / "answers").mkdir(parents=True, exist_ok=True)
    evals = json.loads(EVALS.read_text())
    st = R.State(a.cap)
    log = []

    def flush(code, verdict=None, note=""):
        passes = getattr(decide, "last", ({}, {}))[0]
        (out / "result.json").write_text(json.dumps(
            {"model": R.CLAUDE_MODEL, "cap": a.cap, "spent": st.spent, "util": st.util, "exit": code, "note": note,
             "verdict": verdict or getattr(decide, "last", ({}, {}))[1], "passes": passes, "calls": log}, indent=1))

    def call(arm, ev, n):
        sysm, usr = system_prompt(arm), user_prompt(ev)
        txt = R.claude_call(sysm, usr, st, reserve_for(sysm, usr))
        name = f"{arm}-{ev['id']}-{n}.txt"
        (out / "answers" / name).write_text(txt)
        ok = score(txt, ev)
        log.append({"arm": arm, "id": ev["id"], "n": n, "pass": ok, "spent": st.spent, "util": st.util, "file": name})
        return ok
    try:
        R.claude_call("Reply with the word OK.", "OK", st, 0.30)  # quota reading before the first real call; fails closed
        v = decide(call, evals)
        flush(0, v)
    except R.Stop as e:
        flush(3, note=str(e))
        print("stopped:", e)
        return 3
    except Exception as e:  # infrastructure fault voids the attempt
        flush(2, note=f"{type(e).__name__}: {e}")
        print("infrastructure fault:", e)
        return 2
    print(json.dumps(v, indent=1), f"spent ${st.spent:.3f}")
    return 0


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def freeze():
    blob = lambda p: subprocess.check_output(["git", "hash-object", str(p)], text=True).strip()  # noqa: E731
    rows = [("model", f"`{R.CLAUDE_MODEL}`"), ("`SKILL.md` git blob", blob(SKILL)), ("`security-api.md` git blob", blob(REF)),
            ("`evals.json` sha256", sha(EVALS)), ("`ablate.py` sha256", sha(__file__))]
    rows += [(f"fixture `{p.relative_to(HERE / 'evals-b')}` sha256", sha(p)) for p in sorted((HERE / "evals-b/fixtures").rglob("*")) if p.is_file()]
    table = "| Input | Value |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows) + "\n"
    s = ABLATION.read_text()
    head = s[: s.index("## Frozen inputs")]
    ABLATION.write_text(head + "## Frozen inputs\n" + table)
    print("froze", len(rows), "inputs")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("freeze")
    r = sub.add_parser("run")
    r.add_argument("--out", required=True)
    r.add_argument("--cap", type=float, default=CAP)
    s = sub.add_parser("score")
    s.add_argument("text_file")
    s.add_argument("fixture_id")
    a = ap.parse_args(argv)
    if a.cmd == "freeze":
        return freeze()
    if a.cmd == "run":
        return run_cmd(a)
    ev = next(e for e in json.loads(EVALS.read_text()) if e["id"] == a.fixture_id)
    print("pass" if score(Path(a.text_file).read_text(), ev) else "fail")


if __name__ == "__main__":
    sys.exit(main())
