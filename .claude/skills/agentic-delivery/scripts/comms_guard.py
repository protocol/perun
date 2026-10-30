#!/usr/bin/env python3
"""comms_guard.py — PreToolUse hook: lint a PR or tracker write against its artifact template and WARN, never block.

WHY: agents post PR bodies, status updates and comments that bury the lead, pad with filler and repeat a wrong
weekday, and nothing checked them before they went out. This hook runs communication-structure's comms_lint.py on the
body of the write and, when the draft is below the bar, adds the exact fix per failing rule to Claude's context; the
write itself always goes ahead (the hook cannot make an agent invent an owner or date the input never had).

Covers: Linear MCP `save_status_update` (kind status) and `save_comment` (message) from any server whose name contains
"linear"; Bash `gh pr create|edit` (pr), `gh pr comment` and `gh issue create|edit|comment` (message), `gh release
create|edit` (release); `curl` or `gh api` calls to repos/<owner>/<repo>/pulls (pr) or /issues (message) with a
`body`. The body is read from `--body`/`-b`/`--notes`, a heredoc, `$(cat FILE)`, `--body-file`/`-F FILE`, `-d` JSON,
`-d @FILE`, `--input FILE` or `-f body=...`. A command with no readable body is allowed. A `gh pr create|edit` whose
`--title` says audit, security or harden is checked as kind `audit-pr` (required sections, and for `create` without
`--head` that the diff against `--base` is named under "Changes by area", read in the directory of a `cd` ahead of `gh`; no
repo or base: sections only).

Output: a JSON `hookSpecificOutput.additionalContext` (the lint report); never a `permissionDecision`, never exit 2.
Register it as `python3 ".../comms_guard.py" || true`. Fail open: bad stdin, a missing communication-structure skill,
an unreadable file or any error prints nothing. Opt out for a session or a project with `PERUN_COMMS_GUARD=off`
(settings `env`). Side effects: none (reads the body file and, for an audit PR, runs a read-only `git diff --name-only`;
no network). Test: scripts/test_comms_guard.py, scripts/test_audit_pr_body.py.
"""
import json
import os
import re
import sys
from pathlib import Path

LINT_DIR = Path(__file__).resolve().parent.parent.parent / "communication-structure" / "scripts"
MCP = re.compile(r"^mcp__.*linear.*__(save_status_update|save_comment)$", re.I)
GH = re.compile(r"\bgh\s+(pr|issue|release)\s+(create|edit|comment)\b")
REST = re.compile(r"(?:\bcurl\b|\bgh\s+api\b)[\s\S]{0,600}?\brepos/[^/\s'\"]+/[^/\s'\"]+/(pulls|issues)((?:/\d+)?(?:/(?:comments|reviews))?)(?=[\s'\"?]|$)")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)(\w+)\1[ \t]*\n(.*?)\n[ \t]*\2[ \t]*(?=\n|\)|\"|'|$)", re.S)
VALUE = re.compile(r"\"((?:[^\"\\]|\\.)*)\"|'([^']*)'|(\S+)", re.S)


def _flags(tail, names):
    """Yield the raw text after each occurrence of a flag in `names` (regex alternation), `--flag value` or `--flag=value`."""
    for m in re.finditer(rf"(?:^|\s)(?:{names})(?:=|[ \t]+)", tail):
        yield tail[m.end():]


def _read(path, cwd):
    p = Path(os.path.expandvars(os.path.expanduser(path)))
    return (p if p.is_absolute() else Path(cwd or ".") / p).read_text(encoding="utf-8")[:200_000]


def _stdin(tail):
    h = HEREDOC.search(tail)
    return h.group(3) if h else None


def _value(rest, cwd):
    """The string a shell value stands for: heredoc, `$(cat FILE)`, a quoted string or a bare word; None if unreadable."""
    if re.match(r"\"?\$\(\s*cat\s*<<", rest):
        return _stdin(rest)
    c = re.match(r"\"?\$\(\s*cat\s+([^\s)\"']+)\s*\)", rest)
    if c:
        return _read(c.group(1), cwd)
    m = VALUE.match(rest)
    if not m:
        return None
    if m.group(1) is not None:
        return re.sub(r"\\([\"\\$`])", r"\1", m.group(1))
    return m.group(2) if m.group(2) is not None else m.group(3)


def _file(name, cwd, tail):
    """File text for a name; `-` and `@-` mean the heredoc on stdin."""
    return _stdin(tail) if name in ("-", "@-") else _read(name.lstrip("@"), cwd)


def _gh_body(tail, noun, cwd):
    names, files = (r"--notes|-n", r"--notes-file|-F") if noun == "release" else (r"--body|-b", r"--body-file|-F")
    for rest in _flags(tail, names):
        return _value(rest, cwd)
    for rest in _flags(tail, files):
        name = _value(rest, cwd)
        return _file(name, cwd, tail) if name else None
    return None


def _rest_body(tail, cwd):
    for rest in _flags(tail, r"-f|-F|--field|--raw-field"):  # gh api -f body=TEXT, -f 'body=TEXT', -F body=@FILE
        q = re.match(r"([\"'])body=", rest)
        if q:
            return _value(q.group(1) + rest[q.end():], cwd)
        if rest.startswith("body="):
            return _file(rest[5:], cwd, tail) if rest[5:].startswith("@") else _value(rest[5:], cwd)
    for rest in _flags(tail, r"-d|--data|--data-raw|--data-binary"):  # curl -d '{"body": ...}' or -d @FILE
        raw = _value(rest, cwd)
        raw = _file(raw, cwd, tail) if raw and (raw.startswith("@") or raw == "-") else raw
        return json.loads(raw).get("body") if raw else None
    for rest in _flags(tail, r"--input"):  # gh api --input FILE
        name = _value(rest, cwd)
        raw = _file(name, cwd, tail) if name else None
        return json.loads(raw).get("body") if raw else None
    return None


def extract(tool_name, tool_input, cwd=""):
    """(kind, body) for a PR or tracker write this hook covers, else None. Never raises on a malformed command."""
    if MCP.match(tool_name or ""):
        body = (tool_input or {}).get("body")
        return ("status" if tool_name.lower().endswith("save_status_update") else "message", body) if isinstance(body, str) else None
    cmd = (tool_input or {}).get("command")
    if tool_name != "Bash" or not isinstance(cmd, str) or not re.search(r"\b(?:gh|curl)\b", cmd):
        return None
    try:
        m = GH.search(cmd)
        if m:
            noun, verb = m.group(1), m.group(2)
            kind = "release" if noun == "release" else "pr" if noun == "pr" and verb != "comment" else "message"
            body = _gh_body(cmd[m.start():], noun, cwd)
        elif (m := REST.search(cmd)):
            kind = "pr" if m.group(1) == "pulls" and not m.group(2).endswith(("comments", "reviews")) else "message"
            body = _rest_body(cmd[m.start():], cwd)
        else:
            return None
    except (OSError, ValueError, AttributeError):  # unreadable file, non-JSON data: nothing to lint
        return None
    return (kind, body) if isinstance(body, str) and body.strip() else None


def audit(kind, cmd, cwd, lint):
    """(kind, lint kwargs): a PR written by `gh pr create|edit` with a --title that names an audit, security or hardening
    change is linted as `audit-pr`; `create` without --head also gets the paths changed against --base (default origin/HEAD)
    so coverage is checked (read in the directory of a `cd` ahead of gh, else `cwd`), and without a repo or base only the
    headings are. Anything else, or an old comms_lint, keeps `kind`."""
    try:
        m = GH.search(cmd)
        tail = cmd[m.start():] if m else ""
        title = next((_value(r, cwd) for r in _flags(tail, r"--title|-t")), None)
        if kind != "pr" or not title or not lint.AUDIT_TITLE.search(title):
            return kind, {}
        if m.group(2) != "create" or any(_flags(tail, r"--head|-H")):
            return "audit-pr", {}
        for d in re.findall(r"\b(?:cd|pushd)\s+(?:--\s+)?(\"[^\"]*\"|'[^']*'|[^\s;&|]+)", cmd[:m.start()]):  # a `cd` ahead of gh: that directory is the PR's checkout
            cwd = os.path.join(cwd or ".", os.path.expandvars(os.path.expanduser(d.strip("\"'"))))
        base = next((_value(r, cwd) for r in _flags(tail, r"--base|-B")), None)
        base = base if not base or base.startswith("origin/") else "origin/" + base
        try:
            return "audit-pr", {"files": lint.changed_files(base or "origin/HEAD", cwd or None)}
        except (OSError, ValueError):
            return "audit-pr", {}
    except (AttributeError, OSError, ValueError):
        return kind, {}


def main():
    if os.environ.get("PERUN_COMMS_GUARD", "").lower() in ("off", "0", "false"):
        return 0
    try:
        data = json.load(sys.stdin)
        tool_input, cwd = data.get("tool_input") or {}, str(data.get("cwd") or "")
        got = extract(data.get("tool_name") or "", tool_input, cwd)
        if not got:
            return 0
        sys.path.insert(0, str(LINT_DIR))
        import comms_lint
        kind, extra = audit(got[0], str(tool_input.get("command") or ""), cwd, comms_lint)
        res = comms_lint.lint(kind, got[1], **extra)
        if res["ok"]:
            return 0
        lines = comms_lint.render(res).splitlines()
        report = "\n".join([ln for ln in lines[:-1] if ln.startswith("FAIL")][:8] + lines[-1:])
        note = (f"Comms check on the {res['kind']} you just sent (advisory, the write went ahead):\n{report}\n"
                "Fix the text if you edit it again; template: .claude/skills/communication-structure/references/artifact-templates.md. "
                "Add nothing the source lacks, and never write a stand-in for an owner or date the input does not give.")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext": note}}))
    except Exception:  # fail open: a broken quality hook must never block work
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
