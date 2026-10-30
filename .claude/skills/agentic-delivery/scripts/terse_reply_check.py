#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=opt-in reply budget stated up front (never forces a rewrite), review=2027-01-30
"""Reply-budget hook (OPT-IN, `install.sh --with-terse-replies`): state the budget up front, never force a rewrite.

One script, three events (`hook_event_name` in the stdin JSON; absent means Stop):
- SessionStart: prints the budget (stdout becomes context), so the first draft fits.
- Stop: reads `last_assistant_message`. A violation is more than TERSE_MAX_LINES non-empty lines or TERSE_MAX_CHARS
  characters (defaults 3 and 500; 0 turns one off), or a filler/article/hedge share above TERSE_MAX_RATIO (default
  0.12; replies under TERSE_MIN_WORDS=25 words skip this). Fenced code blocks, inline code, `! ` lines (a command
  the user copies and runs with the host's `!` prefix), quoted/error lines and tables do not count (an unclosed fence is prose, and the whole
  reply may not pass 5 times TERSE_MAX_CHARS, so nothing hides in a fence). Default mode
  `remind` does NOT block the stop (a block makes the agent re-emit a shortened copy, so the user sees both and
  pays twice): it records the violation for this session_id under TERSE_STATE_DIR (default <tmp>/claude-terse-reply).
- UserPromptSubmit: if a violation is recorded, prints a one-line reminder (stdout becomes context for THIS turn)
  and clears the record (the file is emptied, never deleted).
Strict knob: TERSE_MODE=block makes Stop return the documented block response, {"decision": "block", "reason": ...},
which sends the same turn back for a rewrite (https://code.claude.com/docs/en/hooks); `stop_hook_active` true means
this turn is already a rewrite, so it allows (at most 1 rewrite per turn).

Any error fails open (exit 0). No voice text is vendored: for a chat-voice style see the public caveman repository,
https://github.com/JuliusBrussee/caveman. Deterministic, stdlib only.
Env: TERSE_MODE, TERSE_MAX_LINES, TERSE_MAX_CHARS, TERSE_MAX_RATIO, TERSE_MIN_WORDS, TERSE_STATE_DIR.
"""
import json
import os
import re
import sys
import tempfile

COPY_FACTOR = 5  # the whole reply, fenced code and `! ` lines included, may be at most this many times TERSE_MAX_CHARS

WORDS = set(
    "a an the just really basically actually simply very quite essentially literally "
    "perhaps maybe probably possibly might seems somewhat likely arguably generally "
    "also however additionally furthermore moreover please".split()
)
PHRASES = (
    "sure", "certainly", "of course", "happy to", "glad to", "great question",
    "i hope this helps", "let me know if", "feel free to", "no problem", "absolutely",
    "i'd be happy", "thanks for",
)
REASON = (
    "Reply over budget ({why}). Rewrite terser: drop articles, filler, hedges and pleasantries; keep every "
    "technical fact, code and error text exact."
)


def strip(text):
    text = re.sub(r"```.*?(```|\Z)", " ", text, flags=re.S)
    text = re.sub(r"`[^`\n]*`", " ", text)
    keep = [
        ln for ln in text.splitlines()
        if not re.match(r"\s*>|\s*\||! |(    |\t)", ln) and not re.search(r"\b(Error|Exception|Traceback|FAILED)\b|\berror:", ln)
    ]
    return re.sub(r"(?m)^\s*(?:[-*+]|\d+[.)])\s+", "", "\n".join(keep))


def ratio(text):
    low = strip(text).lower()
    words = re.findall(r"[a-z']+", low)
    if not words:
        return 0.0, 0
    hits = sum(w in WORDS for w in words)
    for p in PHRASES:
        hits += low.count(p) * len(p.split())
    return hits / len(words), len(words)


def _prose(msg):
    """Lines that count: all but closed fenced code blocks and lines starting with '! '. An unclosed fence is not a
    code block, so its lines count as prose; a one-line fence (an even number of ``` on it) toggles nothing."""
    kept, block, fenced = [], [], False
    for ln in msg.split("\n"):
        if ln.lstrip().startswith("```"):
            if ln.count("```") % 2 == 1:
                fenced, block = not fenced, []
        elif fenced:
            block.append(ln)
        elif not ln.startswith("! "):
            kept.append(ln)
    return kept + (block if fenced else [])


def _caps():
    return int(os.environ.get("TERSE_MAX_LINES", "3")), int(os.environ.get("TERSE_MAX_CHARS", "500"))


def budget():
    n, c = _caps()
    cap = " / ".join(x for x in (f"{n} lines" if n else "", f"{c} chars" if c else "") if x)
    return ("Reply budget: " + (f"at most {cap}" if cap else "short") + "; fenced code blocks and `! ` command lines are "
            "not counted. Drop articles, filler, hedges and pleasantries; keep every technical fact, code and error "
            "text exact. Write it to fit the first time: a rewrite is never needed.")


def violation(msg):
    """Why `msg` is over budget, or ""."""
    kept = [ln for ln in _prose(msg) if ln.strip()]
    chars = len("\n".join(kept))
    n, c = _caps()
    if (n and len(kept) > n) or (c and chars > c):
        return f"{len(kept)} lines / {chars} chars"
    if c and len(msg) > c * COPY_FACTOR:  # a deliverable or a wall of commands must not hide in a fence or `! ` lines
        return f"{len(msg)} chars in all, fenced code and `! ` lines included"
    r, words = ratio(msg)
    if words >= int(os.environ.get("TERSE_MIN_WORDS", "25")) and r > float(os.environ.get("TERSE_MAX_RATIO", "0.12")):
        return f"{r:.0%} filler/article/hedge words"
    return ""


def _state(data):
    d = os.environ.get("TERSE_STATE_DIR") or os.path.join(tempfile.gettempdir(), "claude-terse-reply")
    return os.path.join(d, re.sub(r"[^\w.-]", "_", str(data.get("session_id") or "unknown")))


def main():
    try:
        data = json.load(sys.stdin)
        event = data.get("hook_event_name") or "Stop"
        strict = os.environ.get("TERSE_MODE") == "block"
        if event == "SessionStart":
            print(budget())
        elif event == "UserPromptSubmit":
            p = _state(data)
            with open(p) as f:
                note = f.read().strip()
            if note:
                open(p, "w").close()
                print(f"Your previous reply was over budget ({note}). Keep this reply within the budget; do not repeat "
                      "or shorten the previous one.")
        elif not (strict and data.get("stop_hook_active")):
            why = violation(data.get("last_assistant_message") or "")
            if why and strict:
                print(json.dumps({"decision": "block", "reason": REASON.format(why=why)}))
            elif why:
                p = _state(data)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as f:
                    f.write(why)
    except Exception:  # fail open
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
