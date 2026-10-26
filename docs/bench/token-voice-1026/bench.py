#!/usr/bin/env python3
"""Token-voice bench: does a voice/terse system prompt cut completion tokens on the hidden-test bug-fix tasks without losing passes?

  bench.py prompts   build prompts/<arm>.txt from the installed rival plugin copies and Perun's shipped text (freeze these)
  bench.py run       [--samples K] [--jobs N] call PCSS (free) for the frozen prompts; resumes from runs.jsonl (needs PCSS_KEY or PCSS_ENV_FILE)

Reuses scripts/hidden_test_bench.py (tickets, scorer, chat call). Task set: all 40 easy tickets plus the first 20 hard ones (file order) = 60.
"""
import argparse, concurrent.futures as cf, json, sys, threading
from pathlib import Path

D = Path(__file__).resolve().parent
ROOT = D.parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / ".claude/skills/agentic-delivery/scripts"))
import hidden_test_bench as H  # noqa: E402

ARMS = ("none", "caveman", "ponytail", "perun")
PLUG = Path.home() / ".claude/plugins/cache"
SRC = {"caveman": PLUG / "caveman/caveman/655b7d9c5431/skills/caveman/SKILL.md",
       "ponytail": PLUG / "ponytail/ponytail/4.10.0/skills/ponytail/SKILL.md"}
# Appended so the caveman arm runs the ultra level its SKILL.md defines (its default is full).
CAVE_LEVEL = "\n\nActive intensity level: ultra.\n"


def tasks():
    """The fixed 60-task set, in file order: 40 easy + the first 20 hard."""
    tk = H.load_tickets()
    return [t for t in tk if t["split"] == "easy"] + [t for t in tk if t["split"] == "hard"][:20]


def perun_voice():
    """Perun's shipped voice/token levers as text: the reply-budget line terse_reply_check.py prints at SessionStart, plus the
    lane preamble's zero-chat rule. Perun ships no voice skill by design, so this is all of it."""
    import terse_reply_check as T
    pre = (ROOT / ".claude/skills/agentic-delivery/templates/lane-preamble.md").read_text()
    zero = next(l for l in pre.splitlines() if l.startswith("- Zero chat between tool calls"))
    return T.budget() + "\n\n" + zero + "\n"


def build_prompts():
    for a in ARMS:
        body = "" if a == "none" else perun_voice() if a == "perun" else SRC[a].read_text() + (CAVE_LEVEL if a == "caveman" else "")
        (D / "prompts" / f"{a}.txt").write_text(H.BASE + ("\n\n" + body if body else ""))


def run(a):
    sysm = {x: (D / "prompts" / f"{x}.txt").read_text() for x in ARMS}
    log = D / "runs.jsonl"
    done = {(r["arm"], r["id"], r["sample"]) for r in map(json.loads, log.read_text().splitlines())} if log.exists() else set()
    todo = [(x, t, k) for k in range(a.samples) for t in tasks() for x in ARMS if (x, t["id"], k) not in done]
    lock = threading.Lock()

    def one(j):
        x, t, k = j
        try:
            reply, ct, pt, fin = H.chat(H.MODEL, sysm[x], H.user_prompt(t), seed=20261026 + k)
        except RuntimeError as e:
            print(f"skip {x}/{t['id']}/{k}: {e}", file=sys.stderr)
            return
        ok, why = H.run_hidden(H.extract_code(reply), t["test"])
        rec = {"arm": x, "id": t["id"], "sample": k, "pass": ok, "why": why, "completion_tokens": ct, "prompt_tokens": pt, "finish": fin, "reply": reply}
        with lock, log.open("a") as f:
            f.write(json.dumps(rec) + "\n")

    with cf.ThreadPoolExecutor(a.jobs) as ex:
        list(ex.map(one, todo))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("cmd", choices=["prompts", "run"])
    p.add_argument("--samples", type=int, default=2)
    p.add_argument("--jobs", type=int, default=6)
    a = p.parse_args()
    build_prompts() if a.cmd == "prompts" else run(a)
