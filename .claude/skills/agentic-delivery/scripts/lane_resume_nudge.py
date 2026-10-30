#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=advise resuming an earlier same-domain lane over a costly new one, review=2027-01-30
"""lane_resume_nudge.py — PreToolUse(Agent|Task) hook: advise resuming an earlier same-domain lane.

Spawning a new lane costs a 30-60k-token startup that re-reads the same code an earlier lane already read. This
hook compares the new lane's `description` with the descriptions in this session's subagent meta files
(`<transcript dir>/<session>/subagents/agent-<id>.meta.json`, found from the hook's `transcript_path`). When the
keyword overlap (Jaccard over words of 3+ letters/digits minus stopwords) is at least 0.5 and shares 2+ words, it
prints a PreToolUse `additionalContext` advisory naming the earlier lane to continue with SendMessage. Advisory only:
it never denies. A missing field, directory or unreadable meta file exits 0 silently.

Run `lane_resume_nudge.py --selftest` to check it.
"""
import io
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

STOP = {"the", "and", "for", "with", "from", "into", "this", "that", "run", "fix", "add", "new"}


def words(text):
    return set(re.findall(r"[a-z0-9]{3,}", str(text).lower())) - STOP


def check(payload):
    """The advisory line for this PreToolUse payload, or None."""
    new = words((payload.get("tool_input") or {}).get("description") or "")
    tp = Path(payload["transcript_path"])
    best = (0.0, None, "")
    for meta in (tp.parent / tp.stem / "subagents").glob("*.meta.json"):
        try:
            desc = json.loads(meta.read_text()).get("description") or ""
        except (OSError, ValueError):
            continue
        old = words(desc)
        shared = len(new & old)
        score = shared / len(new | old) if new | old else 0.0
        if shared >= 2 and score >= 0.5 and score > best[0]:
            best = (score, meta.name.removesuffix(".meta.json").removeprefix("agent-"), desc)
    if best[1] is None:
        return None
    return (f"Earlier lane agent {best[1]} (\"{best[2]}\") covers the same area: resume it with SendMessage instead "
            "of spawning a new one, to skip the startup re-read. Its tool-call cap does not reset on resume, so a fresh lane is better "
            "for a large remainder. Spawn new if it is finished and unrelated.")


def main():
    try:
        line = check(json.load(sys.stdin))
    except Exception:
        return 0  # fail open
    if line:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": line}}))
    return 0


def _run(payload):
    real_in, real_out = sys.stdin, sys.stdout
    sys.stdin, sys.stdout = io.StringIO(json.dumps(payload)), io.StringIO()
    try:
        rc = main()
        return rc, sys.stdout.getvalue()
    finally:
        sys.stdin, sys.stdout = real_in, real_out


def _selftest():
    tmp = Path(tempfile.mkdtemp(prefix="lane-resume-"))
    res = []
    try:
        sub = tmp / "sess" / "subagents"
        sub.mkdir(parents=True)
        (sub / "agent-abc123.meta.json").write_text(json.dumps({"description": "Release for issues 1272-1274"}))
        (sub / "agent-bad.meta.json").write_text("{")
        tp = str(tmp / "sess.jsonl")
        pl = {"transcript_path": tp, "tool_input": {"description": "Release issues 1272 1275"}}
        res.append(("overlap-names-earlier-lane-skipping-bad-meta", "abc123" in (check(pl) or "")))
        pl["tool_input"]["description"] = "Write docs for the cache"
        res.append(("unrelated-silent", check(pl) is None))
        res.append(("missing-description-silent", check({"transcript_path": tp}) is None))
        other = {"transcript_path": str(tmp / "x.jsonl"), "tool_input": {"description": "Release issues 1272"}}
        res.append(("no-subagents-dir-silent", check(other) is None))
        res.append(("missing-fields-exit-0-silent", _run({}) == (0, "")))
        pl["tool_input"]["description"] = "Release for issues 1272-1274"
        rc, out = _run(pl)
        ctx = json.loads(out)["hookSpecificOutput"]
        res.append(("advisory-json-never-denies", rc == 0 and ctx["hookEventName"] == "PreToolUse"
                    and "permissionDecision" not in ctx))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    for n, ok in res:
        print(f"{'PASS' if ok else 'FAIL'}  {n}")
    print(f"\nselftest: {sum(ok for _, ok in res)}/{len(res)} passed")
    return 0 if all(ok for _, ok in res) else 1


if __name__ == "__main__":
    sys.exit(_selftest() if "--selftest" in sys.argv else main())
