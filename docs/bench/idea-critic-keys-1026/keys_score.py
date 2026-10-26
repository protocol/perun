#!/usr/bin/env python3
"""Deterministic answer keys and scorer for the idea-critic bench (no LLM judge, no network, stdlib only).

  keys_score.py keys               derive keys.json from the landed idea-critic-r9-1018 held scenarios (read-only)
  keys_score.py score KEYS OUTDIR  grade saved outputs (OUTDIR/<scenario-id>.txt) against KEYS, print JSON

The r9 prompts ask a plan-review question (recommendation, failure modes, a stop trigger, sometimes a
devil's-advocate answer). They do not fix a HOLD/REVISE/PASS verdict, so no verdict is keyed (unchecked rather
than guessed). Per-scenario key, rule-derived from the prompt text only (never from an output):
  kill       true when the prompt asks for a stop trigger (pull the plug, walk away, kill metric, ...): the output
             must name a stop action (stop, kill, walk away, halt, abandon, terminate, cancel, pull the plug,
             exit) with a digit within 200 characters after it, i.e. a numeric threshold, not "if it goes badly".
  recommend  true when the prompt asks for a recommendation or decision: the output must state one
             (recommend, proceed, do not, don't, hold, pause, sign, decline, reject, defer, delay, approve, no-go).
  mind       true when the prompt asks what would change the answer (devil's advocate, change your mind): the
             output must say what would change it (change my mind, would change, reverse, flip, devil, overturn).
A scenario passes when every asked check is met. Empty or missing output = fail. Score is 1 or 0 per scenario;
the aggregate is the pass rate.
"""
import json, re, sys
from pathlib import Path

D = Path(__file__).resolve().parent
SRC = D.parent / "idea-critic-r9-1018"
ASK_KILL = re.compile(r"pull the plug|walk away|kill (?:criteri|metric|switch|trigger|rule)|stop[- ](?:loss|rule|trigger|signal)|(?:when|where|what|which|exact|specific)\b.{0,40}\b(?:stop|abandon|cancel|exit)|tripwire|abandon", re.I)
ASK_REC = re.compile(r"recommend|go/no-go|verdict|should we (?:sign|proceed|go|move|launch|roll|adopt|buy)", re.I)
ASK_MIND = re.compile(r"devil|change your mind|make you change|would change", re.I)
KILL = re.compile(r"pull[- ]the[- ]plug|\bkill|walk[- ]away|\bstop|\bhalt|abandon|terminat|cancel|\bexit", re.I)
REC = re.compile(r"recommend|proceed|do not|don't|\bhold\b|pause|\bsign\b|decline|reject|defer|delay|approve|no-go", re.I)
MIND = re.compile(r"change my mind|would change|reverse|flip|devil|overturn", re.I)


def derive(prompt):
    """Key for one prompt: kill, recommend, mind (each true only when the prompt asks for it)."""
    return {"kill": bool(ASK_KILL.search(prompt)), "recommend": bool(ASK_REC.search(prompt)),
            "mind": bool(ASK_MIND.search(prompt))}


def grade(key, text):
    """Grade one output text against one key: {"pass": bool, "why": [failure codes]}."""
    if not text.strip():
        return {"pass": False, "why": ["empty"]}
    why = []
    if key["kill"] and not any(re.search(r"\d", text[m.end():m.end() + 200]) for m in KILL.finditer(text)):
        why.append("no-numeric-kill")
    if key["recommend"] and not REC.search(text):
        why.append("no-recommendation")
    if key["mind"] and not MIND.search(text):
        why.append("no-change-my-mind")
    return {"pass": not why, "why": why}


def build():
    """Keys for every held scenario of the landed idea-critic-r9-1018 bench."""
    return {s["id"]: derive(s["prompt"]) for s in json.loads((SRC / "scenarios9-held.json").read_text())}


def score(keys, outdir):
    """Grade OUTDIR/<id>.txt for every key; a missing file fails."""
    res = {}
    for sid, key in keys.items():
        f = Path(outdir) / f"{sid}.txt"
        res[sid] = grade(key, f.read_text() if f.exists() else "")
    return {"n": len(res), "pass_rate": sum(r["pass"] for r in res.values()) / max(len(res), 1), "scenarios": res}


if __name__ == "__main__":
    if sys.argv[1:2] == ["keys"]:
        (D / "keys.json").write_text(json.dumps(build(), indent=1, sort_keys=True) + "\n")
    elif sys.argv[1:2] == ["score"] and len(sys.argv) == 4:
        print(json.dumps(score(json.loads(Path(sys.argv[2]).read_text()), sys.argv[3]), indent=1))
    else:
        sys.exit(__doc__)
