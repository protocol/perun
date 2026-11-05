#!/usr/bin/env python3
# rail: owner=deep-code-review, why=block a whole-app audit report that fails the report contract once, review=2027-02-05
"""Plugin Stop hook: lint a whole-app security audit's final report and block delivery once when it fails.

Purpose: about half of agentic whole-app audits skip the template in references/whole-project-report.md and the
report_contract_lint.py check, and hand-write a free-form table that loses findings. Prose did not fix it, so this
hook runs the same lint on the final message and, on violations, asks the model to redo the report.
Usage: `--mark` reads PostToolUse JSON and creates $TMPDIR/perun-audit-mode-<session_id> when the mode file was Read (Bash does not count) (fallback for runs whose transcript file is never written); otherwise stdin is the Claude Code Stop hook JSON (last_assistant_message, transcript_path, cwd, stop_hook_active).
Output: nothing (allow the stop), or `{"decision":"block","reason":...}` on stdout; always exit 0.
Edge cases: malformed stdin or stop_hook_active true -> allow (the block is bounded to one extra turn). A message with
fewer than 5 `path.ext:line` cites is not an audit report -> allow, without reading the transcript. A session whose
transcript shows no Read of this skill's references/security-review-mode.md since the last human prompt did not run the audit mode -> allow. Any exception (lint crash,
unreadable file) fails open with one stderr line.
Side effects: reads the transcript and files under cwd; --mark creates, and Stop removes, the empty marker file. Stdlib only.
"""
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.dirname(HERE)
CITE = re.compile(r"[\w./-]+\.\w+:\d+")


def last_text(path):
    """Last assistant text block of a transcript JSONL, or ''."""
    out = ""
    with open(path, errors="replace") as f:
        for line in f:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if m.get("type") != "assistant":
                continue
            c = (m.get("message") or {}).get("content")
            if isinstance(c, str):
                out = c
            elif isinstance(c, list):
                t = "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text")
                out = t or out
    return out


def mode_read(path):
    """True when, after the last human prompt, the session Read this skill's references/security-review-mode.md."""
    hit = False
    with open(path, errors="replace") as f:
        for line in f:
            try:
                m = json.loads(line)
            except ValueError:
                continue
            if not isinstance(m, dict) or not isinstance(m.get("message"), dict):
                continue
            c = m["message"].get("content")
            if m.get("type") == "user" and not m.get("isMeta"):
                txt = c if isinstance(c, str) else "\n".join(b.get("text", "") for b in c if isinstance(b, dict) and b.get("type") == "text") if isinstance(c, list) else ""
                if txt and not txt.startswith("Stop hook feedback"):
                    hit = False  # new human prompt: earlier reads do not count
            elif m.get("type") == "assistant" and isinstance(c, list):
                for b in c:
                    i = b.get("input") if isinstance(b, dict) and b.get("type") == "tool_use" else None
                    if is_mode_use(b.get("name"), i):
                        hit = True
    return hit


def marker(d):
    """Marker path for this session's mode read, or None without a usable session_id."""
    sid = re.sub(r"[^A-Za-z0-9_-]", "", str(d.get("session_id") or ""))
    return os.path.join(tempfile.gettempdir(), "perun-audit-mode-" + sid) if sid else None


def is_mode_use(name, i):
    """True for a Read of this hook's own installed references/security-review-mode.md (not a repo copy, not Bash)."""
    if name != "Read" or not isinstance(i, dict) or not isinstance(i.get("file_path"), str):
        return False
    return os.path.realpath(i["file_path"]) == os.path.realpath(os.path.join(SKILL, "references", "security-review-mode.md"))


def mark():
    """PostToolUse: drop the session marker when the mode file was read (for runs with no transcript file)."""
    try:
        d = json.load(sys.stdin)
        mk = marker(d)
        if mk and is_mode_use(d.get("tool_name"), d.get("tool_input")):
            os.close(os.open(mk, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600))
    except BaseException as e:
        print(f"audit_report_gate: mark skipped ({type(e).__name__}: {e})", file=sys.stderr)


def reason(viol, root):
    s = SKILL
    return (
        "Your final report did not pass the audit report contract, so it is not deliverable. Violations (first 20):\n"
        + "\n".join(viol[:20])
        + "\n\nNext steps:\n"
        "(1) Run each shell command alone: no `;`, `&&`, for-loops or `$(...)`.\n"
        f"(2) If you have not yet run it, run `bash {s}/scripts/review_checks.sh --full`.\n"
        f"(3) Read `{s}/references/whole-project-report.md` and rewrite the WHOLE report in its headings and tables.\n"
        f"(4) Check it with `python3 -I {s}/scripts/report_contract_lint.py --part N --root {root}` chunks, then `--done`.\n"
        "(5) Output the draft that printed ok, verbatim."
    )


def main():
    try:
        d = json.load(sys.stdin)
        if not isinstance(d, dict) or d.get("stop_hook_active"):
            return
        tp = d.get("transcript_path")
        msg = d.get("last_assistant_message")
        if not isinstance(msg, str) or not msg:
            msg = last_text(tp) if tp and os.path.isfile(tp) else ""
        if len(CITE.findall(msg)) < 5:
            return
        mk = marker(d)
        if tp and os.path.isfile(tp):  # claude -p --no-session-persistence gives a path but never writes it: use the marker
            with open(tp, "rb") as f:
                if b"security-review-mode.md" not in f.read() or not mode_read(tp):
                    return
        elif not (mk and os.path.exists(mk)):
            return
        root = d.get("cwd")
        if not (isinstance(root, str) and os.path.isdir(root)):
            return
        sys.path.insert(0, HERE)
        import report_contract_lint

        viol = report_contract_lint.lint("-", root, text=msg)
        if mk and os.path.exists(mk):
            os.remove(mk)
        if viol:
            print(json.dumps({"decision": "block", "reason": reason(viol, root)}))
    except BaseException as e:  # fail open: a gate bug must never trap the session
        print(f"audit_report_gate: skipped ({type(e).__name__}: {e})", file=sys.stderr)


if __name__ == "__main__":
    mark() if "--mark" in sys.argv[1:] else main()
