#!/usr/bin/env python3
"""Where do review tokens go? Splits tool-result and model-output size (chars/4, an estimate) by source for every
Claude Code transcript that invoked the deep-code-review skill, from that first invocation onward.

Sources: skill_refs (Skill result, or Read of a path under a `skills/deep-code-review/` directory), read, grep_glob,
bash, other_tools, model_output (assistant text, thinking and tool-call input).

Usage: review_token_sources.py [TRANSCRIPT_OR_DIR ...]   default ~/.claude/projects (searched recursively for *.jsonl)
Prints one line per source with its share, plus the session count. Read-only; prints no transcript content or paths.
Limits: a Bash command counts as grep_glob by its first token only (`cd x && grep` or a pipe counts as bash);
sidechain (subagent) transcripts are separate files and count as separate sessions; "active" starts at the first
invocation and never resets, so later non-review work in the same session is included.
Counts result size, not billed tokens (no cache or per-turn re-read weighting), so shares rank drivers, not dollars.
"""
import json
import sys
from collections import Counter
from pathlib import Path

SKILL = "deep-code-review"


def blocks(msg):
    c = msg.get("content") if isinstance(msg, dict) else None
    return c if isinstance(c, list) else []


def size(x):
    return len(x if isinstance(x, str) else json.dumps(x, ensure_ascii=False))


def classify(name, inp):
    if name == "Skill":
        return "skill_refs"
    if name == "Read":
        p = str(inp.get("file_path", ""))
        return "skill_refs" if f"skills/{SKILL}/" in p else "read"
    if name in ("Grep", "Glob"):
        return "grep_glob"
    if name == "Bash":
        first = str(inp.get("command", "")).split(None, 1)
        return "grep_glob" if first and first[0] in ("grep", "rg", "find") else "bash"
    return "other_tools"


def session(path):
    """Return Counter of chars by source, or None if the session never invoked the skill."""
    out, tools, active = Counter(), {}, False
    try:
        lines = path.read_text(errors="replace").splitlines()
    except OSError:  # broken symlink, permissions
        return None
    for line in lines:
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if d.get("type") not in ("assistant", "user"):
            continue
        for b in blocks(d.get("message")):
            t = b.get("type")
            if t == "tool_use":
                inp = b.get("input") or {}
                if b.get("name") == "Skill" and SKILL in str(inp.get("skill", "")):
                    active = True
                tools[b.get("id")] = classify(b.get("name"), inp)
                if active:
                    out["model_output"] += size(inp)
            elif t in ("text", "thinking") and d["type"] == "assistant" and active:
                out["model_output"] += size(b.get("text") or b.get("thinking") or "")
            elif t == "tool_result" and active:
                out[tools.get(b.get("tool_use_id"), "other_tools")] += size(b.get("content", ""))
    return out if active else None


def main(args):
    roots = [Path(a) for a in args] or [Path.home() / ".claude/projects"]
    files = [f for r in roots for f in ([r] if r.is_file() else sorted(r.rglob("*.jsonl")))]
    total, n = Counter(), 0
    for f in files:
        s = session(f)
        if s is not None:
            total.update(s)
            n += 1
    grand = sum(total.values()) or 1
    print(f"sessions: {n}")
    for k, v in total.most_common():
        print(f"{k:<14}{v // 4:>12} tok-est{100 * v / grand:>7.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
