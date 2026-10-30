#!/usr/bin/env python3
"""Council bench: score idea-critic council verdicts (veche.py) on the evil-twin corpus. Offline by default; commits no result.

Each case of an evil-twin corpus (default docs/bench/evil-twin-r2-1021/cases.txt: 24 proposals that hide one fatal flaw, 12 sound controls) goes to
veche.py as a numbered packet under a throwaway --root with a constant claim, so seats can cite packet lines and the critique round can verify them.
The hidden KEY never reaches a seat: the packet holds only the proposal, and veche.py runs with the throwaway dir as its cwd, so a tool-using seat sees
only proposal.txt (write absolute paths in --cmd; this is not a sandbox, a seat given absolute-path file access can still read the repo). Only the
optional judge sees the key. One --records dir holds one configuration's result: <id>.json is the veche record of a case, <id>.judge.txt the judge's
answer. A dir that holds every record replays offline and gives the same numbers every time.

Scores (rates over all cases of the kind; intervals are the case-level percentile bootstrap of evil_twin_bench.boot):
  flawed_blocked    flawed cases the council did not wave through (verdict HOLD or REVISE; PASS_TO_USER passes the proposal on)
  flawed_held       flawed cases with verdict HOLD
  control_blocked   sound controls with verdict HOLD or REVISE
  control_held      sound controls with verdict HOLD (a false hold)
  recall            with --judge: flawed cases whose council deliverable names the keyed flaw and treats it as serious (FLAW_CAUGHT)
  false_kill        with --judge: controls whose deliverable recommends abandoning the proposal (KILLED)
The judge uses the R2 prompt, parser and 0/1 definitions (scripts/evil_twin_bench_r2.py), so its numbers read like R2's arms. It reads the
council's HOLD as SKILL.md words it ("do not recommend it"), so control_held is the unambiguous false-hold rate and false_kill the R2-comparable one.
An unparsed judge answer counts 0 and is reported. A council that did not decide (COULD_NOT_DECIDE, NOT_CONVENED, DRY_RUN) is neither blocked nor
held, is not judged and is listed under undecided.

Limits: verdict scores are a floor (a council can block for the wrong reason). The judge sees only the deliverable the record carries (verdict, basis,
pre-mortems, kill criteria, the dissenting seats' answers, the twin's dissent), not every seat's claims. This prints rates only: there is no WIN or
REVERT rule and no self-consistency-3 arm (the keep rule in references/council.md), so a keep decision needs both preregistered first. The R2 corpus
has already scored three arms, so a prompt edit tuned on it needs a fresh corpus. Put no number from here in the scoreboard without a committed
records dir behind it.

  council_bench.py --records DIR [--cases FILE]            score DIR offline (add --judge saved for the judge scores)
  council_bench.py --records DIR --cmd 'claude -p' --veche='--twin' --max-calls 7 --cap-calls 250 [--judge CMD]
                                                           live: convene the cases that have no record, save each at once, resume on rerun
Spend: --cap-calls is required with --cmd or a judge command. It is checked before every council (which reserves --max-calls, refunded when
the council ends early) and every judge call, so a run never starts more calls than the cap. Records are saved as they finish.
"""
import argparse
import concurrent.futures as cf
import json
import re
import shlex
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
VECHE = ROOT / ".claude/skills/idea-critic/scripts/veche.py"
sys.path[:0] = [str(Path(__file__).resolve().parent), str(VECHE.parent)]
import evil_twin_bench as E  # noqa: E402  (parse_cases, mean, boot, JUDGE_SYSTEM)
import evil_twin_bench_r2 as R  # noqa: E402  (D, judge_prompt, parse_judge)
import veche as V  # noqa: E402  (VERDICTS)

CASES = R.D / "cases.txt"
CLAIM = "Approve the proposal in the packet as written."
STEELMAN = "The proposer's own case, as stated in the packet."
BOOT = 10000  # bootstrap resamples; the tests lower it
GLOSS = {"HOLD": "do not recommend it", "REVISE": "incorporate and re-run; do not show the original",  # SKILL.md, "How to run" step 6
         "PASS_TO_USER": "show rec and dissent ledger"}
STATS = (("flawed_blocked", "blocked", "flawed"), ("flawed_held", "held", "flawed"), ("control_blocked", "blocked", "control"),
         ("control_held", "held", "control"), ("recall", "caught", "flawed"), ("false_kill", "killed", "control"))  # (name, row field, case kind)


def load_cases(path):
    """Parse an evil-twin cases file -> [{id, kind, proposal, key}].
    ValueError: a malformed case, an id outside [A-Za-z0-9_-] (ids name files), or a corpus without both kinds."""
    cases = E.parse_cases(Path(path).read_text())
    if not all(re.fullmatch(r"[A-Za-z0-9_-]+", c["id"]) for c in cases) or {c["kind"] for c in cases} != {"flawed", "control"}:
        raise ValueError("case ids must match [A-Za-z0-9_-]+ and the corpus needs flawed and control cases")
    return cases


def convene(case, cmds, flags, per):
    """Run veche.py on one case -> its JSON record. The proposal is the packet in a temp dir that is both --root and cwd (the seats inherit it; the key stays out).
    `flags` come first and the harness's own last, so the harness wins; `per` is veche's --max-calls. SystemExit when veche prints no record (a usage error)."""
    with tempfile.TemporaryDirectory() as d:
        pkt = Path(d) / "proposal.txt"
        pkt.write_text(case["proposal"] + "\n")
        argv = [sys.executable, str(VECHE), *flags, "--claim", CLAIM, "--steelman", STEELMAN, "--packet", str(pkt), "--root", d,
                *[x for c in cmds for x in ("--cmd", c)], "--max-calls", str(per)]
        p = subprocess.run(argv, capture_output=True, text=True, cwd=d)
    try:
        return json.loads(p.stdout)
    except ValueError:
        raise SystemExit(f"veche printed no record for {case['id']} (exit {p.returncode}): {p.stderr.strip()[-300:]}")


def render(rec):
    """The council deliverable as the 'reviewer response' the judge grades: verdict and basis, pre-mortems, kill criteria, what would change it, dissent, twin."""
    lines = [f"COUNCIL VERDICT: {rec['verdict']} ({GLOSS[rec['verdict']]})", f"Basis: {rec.get('verdict_basis', '')}"]
    lines += ["Pre-mortem: " + (p["text"] if isinstance(p, dict) else p) for p in rec.get("premortems", [])]
    lines += ["Kill criterion: " + k for k in rec.get("kill_criteria", [])]
    lines += ["What would change it: " + w for w in rec.get("what_would_change_it", [])]
    lines += ["Dissenting seat answer: " + d for d in rec.get("dissent", [])]
    twin = (rec.get("minority_report") or {}).get("twin")
    return "\n".join(lines + (["Evil twin dissent: " + twin["dissent"]] if twin else []))


def main(argv=None):
    """CLI entry: score one records dir, first convening its missing cases when --cmd is given. Prints the rates; returns the results dict."""
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--records", required=True, help="dir with one <case id>.json veche record per case (and <id>.judge.txt); one dir per configuration")
    ap.add_argument("--cases", default=str(CASES), help="evil-twin cases file (default: the R2 corpus)")
    ap.add_argument("--cmd", action="append", help="seat command template for veche.py (repeat for mixed models); convenes the cases with no record")
    ap.add_argument("--veche", default="", help="extra veche.py flags as one string, e.g. --veche='--twin --lenses cpo,cto,cfo,ciso,user-advocate' "
                    "(write the =: argparse reads a bare --twin as its own flag)")
    ap.add_argument("--judge", help="judge command template (prompt on stdin, answer on stdout), or 'saved' to read only the <id>.judge.txt files")
    ap.add_argument("--cap-calls", type=int, help="most model calls (seats and judge) this run may start; required with --cmd or a judge command")
    ap.add_argument("--max-calls", type=int, default=12, help="veche --max-calls per case, reserved against --cap-calls before each council")
    ap.add_argument("--timeout", type=int, default=300, help="seconds per judge call")
    ap.add_argument("--jobs", type=int, default=2)
    a = ap.parse_args(argv)
    if (a.cmd or a.judge not in (None, "saved")) and a.cap_calls is None:
        ap.error("--cap-calls is required with --cmd or a judge command: a live run spends model calls")
    try:
        cases = load_cases(a.cases)
    except (OSError, ValueError) as e:
        ap.error(f"--cases: {e}")
    recs, judged, used, lock = Path(a.records), a.judge is not None, [0], threading.Lock()
    if a.cmd:
        recs.mkdir(parents=True, exist_ok=True)

    def spend(n):
        """Charge n calls to the cap before they are made (negative n refunds). SystemExit when that would pass --cap-calls."""
        with lock:
            if n > 0 and used[0] + n > a.cap_calls:
                raise SystemExit(f"cap reached: {used[0]} of {a.cap_calls} calls spent, the next step needs {n}; "
                                 "saved work is kept, rerun with a higher --cap-calls to resume")
            used[0] += n

    def judge(case, rec):
        """The judge's answer for one decided case: the saved <id>.judge.txt, else one paid call (saved at once)."""
        f = recs / f"{case['id']}.judge.txt"
        if f.exists():
            return f.read_text()
        if a.judge == "saved":
            raise SystemExit(f"missing judge output {f}")
        spend(1)
        try:
            p = subprocess.run(shlex.split(a.judge), input=f"{E.JUDGE_SYSTEM}\n\n{R.judge_prompt(case, render(rec))}", capture_output=True, text=True, timeout=a.timeout)
        except subprocess.TimeoutExpired:
            raise SystemExit(f"judge timed out on {case['id']}; saved work is kept, rerun to resume")
        if p.returncode:
            raise SystemExit(f"judge exit {p.returncode} on {case['id']}; saved work is kept, rerun to resume")
        f.write_text(p.stdout)
        return p.stdout

    def one(case):
        """One case -> its score row: load or convene its record, then judge it when asked.
        A saved record is reused as is, COULD_NOT_DECIDE included: resume never retries it (delete its <id>.json to run that case again)."""
        f = recs / f"{case['id']}.json"
        if f.exists():
            try:
                rec = json.loads(f.read_text())
                rec["verdict"], rec["cost"]["calls"], rec["cost"]["chars"]  # the fields read below
            except (ValueError, KeyError, TypeError) as e:
                raise SystemExit(f"bad record {f}: {e!r}")
        elif a.cmd:
            spend(a.max_calls)
            rec = convene(case, a.cmd, shlex.split(a.veche), a.max_calls)
            spend(rec["cost"]["calls"] - a.max_calls)
            f.write_text(json.dumps(rec, indent=1))
        else:
            raise SystemExit(f"missing record {f}: pass --cmd to convene it, or point --records at a finished run")
        v = rec["verdict"]
        j = R.parse_judge(judge(case, rec)) if judged and v in V.VERDICTS else None
        return {"id": case["id"], "kind": case["kind"], "verdict": v, "blocked": int(v in ("HOLD", "REVISE")), "held": int(v == "HOLD"),
                "caught": j[0] if j else 0, "killed": j[1] if j else 0, "unparsed": int(judged and v in V.VERDICTS and j is None),
                "calls": rec["cost"]["calls"], "chars": rec["cost"]["chars"]}

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        rows = list(ex.map(one, cases))
    res = {"n": len(rows), "flawed": sum(r["kind"] == "flawed" for r in rows), "undecided": [r["id"] for r in rows if r["verdict"] not in V.VERDICTS],
           "calls": sum(r["calls"] for r in rows), "chars": sum(r["chars"] for r in rows), "stats": {}}
    res["control"] = res["n"] - res["flawed"]
    if judged:
        res["unparsed"] = sum(r["unparsed"] for r in rows)
    for name, field, kind in STATS:
        if judged or field not in ("caught", "killed"):
            res["stats"][name] = {"rate": E.mean(rows, field, kind), "ci": E.boot({"c": rows}, lambda x: E.mean(x["c"], field, kind), BOOT)}
    print(f"n {res['n']} ({res['flawed']} flawed, {res['control']} control)  undecided {len(res['undecided'])} {res['undecided']}  "
          f"seat calls {res['calls']}  chars {res['chars']}" + (f"  unparsed {res['unparsed']}" if judged else ""))
    for k, s in res["stats"].items():
        print(f"{k:16s} {s['rate']:.3f} ({s['ci'][0]:.3f}, {s['ci'][1]:.3f})")
    return res


if __name__ == "__main__":
    main()
