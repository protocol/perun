#!/usr/bin/env python3
"""agent_workflow_injection.py - lead-finder for AI-agent steps in GitHub Actions workflows that attacker text can steer.

Usage: python3 -I agent_workflow_injection.py < paths   (workflow paths on stdin, one per line)

An agent step is a `uses:` of a known AI-agent action (Claude Code, Codex, Gemini CLI, Copilot) or a `run:` that starts one of those CLIs
(`claude -p`, `codex exec`, `gemini -p`, `copilot -p`). Rows, TSV `file<TAB>line<TAB>rule<TAB>message`, report-only, stdlib only:
- agent-untrusted-input: the agent step's `with:`/`env:`/`run:` interpolates text an outsider writes (issue, PR or comment title/body,
  head branch name, head commit message). That text becomes part of the agent's prompt. The message says whether the job holds write
  permissions, has no `permissions:` block (default token) or has secrets in scope: the blast radius if the agent is steered.
- agent-head-checkout: a job with an agent step checks out the pull-request head (or refs/pull/...) in a workflow triggered by
  pull_request_target, issue_comment or workflow_run: attacker files (CLAUDE.md, AGENTS.md, config) then steer a privileged agent.
- agent-broad-tools: the agent step turns off its sandbox or approval (--dangerously-skip-permissions, --yolo, danger-full-access,
  safety-strategy unsafe), allows an unrestricted Bash tool, or lets any user or bot trigger it (allowed_non_write_users / allowed_bots "*").
- not-checked: a file that could not be read.
Not covered: text the agent fetches itself at run time (gh issue view, MCP tools), reusable workflows and composite actions, YAML anchors.
Line-based, not a YAML parser: a lead, confirm it in the file. zizmor covers generic script injection and pull_request_target; this adds the agent view.
"""
import re
import sys

AGENT_USES = re.compile(r"uses:\s*['\"]?(anthropics/claude-code(-base)?-action|anthropics/claude-code-security-review|openai/codex-action|"
                        r"google-github-actions/run-gemini-cli|github/copilot[\w./-]*)", re.I)
AGENT_RUN = re.compile(r"\b(claude(-code)?\s+(-p|--print)\b|codex\s+exec\b|gemini\s+(-p|--prompt)\b|copilot\s+(-p|--prompt)\b)")
UNTRUSTED = re.compile(r"\$\{\{[^}]*(github\.event\.(issue|pull_request|comment|review|review_comment|discussion)\.(\w+\.)*(title|body|ref|label)\b|"
                       r"github\.head_ref|github\.event\.head_commit\.message|github\.event\.pull_request\.head\.\w+)[^}]*\}\}")
BROAD = re.compile(r"--dangerously-skip-permissions|--dangerously-bypass-approvals-and-sandbox|--yolo\b|danger-full-access|safety-strategy:\s*['\"]?unsafe|"
                   r"\bBash\(\*{1,2}(:\*)?\)|(allowed_?tools|allowedTools)[^\n]*[\s:=,'\"]Bash(?![\w(])|"
                   r"allowed_(non_write_users|bots):\s*['\"]?\*", re.I)
TRIGGER = re.compile(r"\b(pull_request_target|issue_comment|workflow_run)\b")
HEAD_REF = re.compile(r"ref:\s*['\"]?[^\n]*(pull_request\.head|head_ref|refs/pull/|workflow_run\.head)")
WRITE = re.compile(r"(^|\s)(permissions:\s*write-all|[\w-]+:\s*write)\s*$", re.M)
SECRET = re.compile(r"secrets\.(?!GITHUB_TOKEN\b)\w+")


def indent(s):
    return len(s) - len(s.lstrip())


def blocks(lines, start, end, key_re):
    """Sub-blocks of lines[start:end]: each begins at a line matching key_re at the first matching indent and runs to the next one."""
    out, ind, cur = [], None, None
    for i in range(start, end):
        s = lines[i]
        if not s.strip() or s.lstrip().startswith("#"):
            continue
        m = key_re.match(s)
        if m and (ind is None or indent(s) == ind):
            ind = indent(s)
            cur = [i, i + 1]
            out.append(cur)
        elif cur and indent(s) > (ind if ind is not None else 0):
            cur[1] = i + 1
        elif cur and ind is not None and indent(s) <= ind:
            cur = None
    return out


def scan(path, text):
    lines = text.splitlines()
    rows = []
    jobs_at = next((i for i, s in enumerate(lines) if re.match(r"jobs:\s*$", s)), None)
    if jobs_at is None:
        return rows
    head = "\n".join(lines[:jobs_at])
    risky = bool(TRIGGER.search(head))
    wf_write = bool(WRITE.search(head))
    has_perms = bool(re.search(r"^permissions:", head, re.M))
    for js, je in blocks(lines, jobs_at + 1, len(lines), re.compile(r"\s*[\w-]+:\s*$")):
        job = "\n".join(lines[js:je])
        steps_at = next((i for i in range(js, je) if re.match(r"\s*steps:\s*$", lines[i])), None)
        if steps_at is None:
            continue
        steps = [(a, b) for a, b in blocks(lines, steps_at + 1, je, re.compile(r"\s*-\s"))]
        body = lambda a, b: "\n".join(l for l in lines[a:b] if not l.lstrip().startswith("#"))  # noqa: E731
        agents = [(a, b) for a, b in steps if AGENT_USES.search(body(a, b)) or AGENT_RUN.search(body(a, b))]
        if not agents:
            continue
        jperm = re.search(r"^\s*permissions:", "\n".join(lines[js:steps_at]), re.M)
        if WRITE.search("\n".join(lines[js:steps_at])) or (not jperm and wf_write):
            reach = "the job holds write permissions"
        elif not jperm and not has_perms:
            reach = "the job has no permissions block (default token)"
        else:
            reach = "the job's token is read-only"
        if SECRET.search(job):
            reach += " and secrets are in scope"
        for a, b in agents:
            t = body(a, b)
            for i in range(a, b):
                m = UNTRUSTED.search(lines[i])
                if m and not lines[i].lstrip().startswith("#"):
                    rows.append((path, i + 1, "agent-untrusted-input", f"outsider-written text `{m.group(0)[:60]}` reaches an AI-agent step; {reach}. "
                                 "Pass it as data (file or env) the prompt names, never inline, and cut the token and secrets to what the agent needs"))
                m = BROAD.search(lines[i])
                if m and not lines[i].lstrip().startswith("#"):
                    rows.append((path, i + 1, "agent-broad-tools", f"agent step uses `{m.group(0)[:50]}`: sandbox or approval off, or an unrestricted tool or trigger; {reach}. "
                                 "Allow named tools only and keep the trigger to repo writers"))
        if risky:
            for a, b in steps:
                if re.search(r"uses:\s*['\"]?actions/checkout", body(a, b)):
                    for i in range(a, b):
                        if HEAD_REF.search(lines[i]) and not lines[i].lstrip().startswith("#"):
                            rows.append((path, i + 1, "agent-head-checkout", "pull-request head checked out in a pull_request_target/issue_comment/workflow_run "
                                         f"job that runs an AI-agent step; {reach}. Attacker files (CLAUDE.md, AGENTS.md, config) steer the agent: check out the base, or run the agent unprivileged"))
    return rows


def main():
    for path in (p.rstrip("\n") for p in sys.stdin if p.strip()):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = scan(path, f.read())
        except OSError as e:
            rows = [(path, 0, "not-checked", f"could not read: {e.strerror}")]
        for r in rows:
            print("\t".join(map(str, r)), flush=True)


if __name__ == "__main__":
    main()
