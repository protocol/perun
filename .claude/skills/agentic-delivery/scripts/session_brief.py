#!/usr/bin/env python3
"""session_brief.py — SessionStart hook: at most 3 lines of fleet hygiene, report-only.

WHY: fleets ran stale Perun versions, piled up 130+ finished worktrees and leftover dev servers,
and left ranked P0s unpulled, because the checks existed but nothing surfaced them at start.

Lines (each skipped when its input is missing; nothing is fetched from the network):
  1. `perun <installed> < <origin/main>`: the installed .claude/skills/deep-code-review/VERSION vs
     the Perun checkout's local origin/main ref, plus the update command. The checkout path comes
     from $PERUN_SOURCE, else `<cache>/perun/source` (written by install.sh). Silent when current.
  2. worktrees whose branch is merged into origin/main (`git branch --merged`; a squash-merged
     branch is not seen as merged) and dev servers listening with a cwd inside this repo's
     worktrees (lsof, skipped when missing or denied), each with a copy-paste report/cleanup
     command that points at clean_finished.sh / reap_own.sh. This hook removes and stops nothing.
  3. the top-ranked item in PRIORITIES.md (queue_guard.ranked_ids; claim status not checked
     offline).
Time: all subprocess calls share a 5s budget (BUDGET); once spent, the rest are skipped.
Output: one JSON object with `systemMessage` (shown to the user) and `additionalContext`.
Any error ends the hook silently with exit 0.
"""
import json
import os
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))


BUDGET = 5.0  # seconds, shared by every subprocess call in one brief
_deadline = [float("inf")]


def _run(cmd, timeout):
    """subprocess.run capped by the remaining shared budget; TimeoutExpired once it is spent."""
    left = _deadline[0] - time.monotonic()
    if left <= 0:
        raise subprocess.TimeoutExpired(cmd, 0)
    return subprocess.run(cmd, capture_output=True, text=True, timeout=min(timeout, left))


def _git(repo, *args, timeout=3):
    try:
        r = _run(["git", "-C", str(repo), *args], timeout)
        return r.stdout if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def _vtuple(v):
    return tuple(int(x) for x in v.strip().split(".") if x.isdigit())


def version_line(repo: Path):
    installed = repo / ".claude/skills/deep-code-review/VERSION"
    src = os.environ.get("PERUN_SOURCE")
    if not src:
        f = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "perun" / "source"
        src = f.read_text().strip() if f.is_file() else ""
    if not (src and installed.is_file()):
        return None
    latest = _git(src, "show", "origin/main:.claude/skills/deep-code-review/VERSION")
    have = installed.read_text().strip()
    if not latest or _vtuple(latest) <= _vtuple(have):
        return None
    return f"perun {have} < {latest.strip()} on origin/main; update: bash {src}/scripts/update-installed.sh {repo}"


def worktrees(repo: Path):
    """`[(path, branch)]` from `git worktree list --porcelain` (detached worktrees have branch None)."""
    out, cur = [], None
    for line in (_git(repo, "worktree", "list", "--porcelain") or "").splitlines():
        if line.startswith("worktree "):
            cur = [line[9:], None]
            out.append(cur)
        elif line.startswith("branch refs/heads/") and cur:
            cur[1] = line[18:]
    return [tuple(w) for w in out]


def dev_servers(paths):
    """Pids listening on TCP whose cwd is inside one of `paths`; None when lsof is unusable."""
    try:
        r = _run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-Fp"], 2)
        pids = sorted({l[1:] for l in r.stdout.splitlines() if l.startswith("p")})
        if not pids:
            return [] if r.returncode in (0, 1) else None
        r = _run(["lsof", "-a", "-d", "cwd", "-p", ",".join(pids), "-Fpn"], 2)
    except (OSError, subprocess.SubprocessError):
        return None
    hits, pid = [], None
    for l in r.stdout.splitlines():
        if l.startswith("p"):
            pid = l[1:]
        elif l.startswith("n") and pid and any(l[1:] == p or l[1:].startswith(p.rstrip("/") + "/") for p in paths):
            hits.append(pid)
    return hits


def hygiene_line(repo: Path):
    wts = worktrees(repo)
    if not wts:
        return None
    main_wt = wts[0][0]
    merged = set()
    if _git(repo, "rev-parse", "-q", "--verify", "origin/main"):
        merged = {b.strip() for b in (_git(repo, "branch", "--merged", "origin/main", "--format=%(refname:short)") or "").splitlines()}
    done = [p for p, b in wts[1:] if b and b in merged]
    servers = dev_servers([p for p, _ in wts])
    parts, sc = [], ".claude/skills/agentic-delivery/scripts"
    parent = os.path.commonpath([os.path.dirname(p) for p in done]) if done else ""
    if done:
        parts.append(f"{len(done)} worktree(s) merged into origin/main; review+clean: cd {main_wt} && ROOT={parent} bash {sc}/clean_finished.sh")
    if servers:
        parts.append(f"{len(servers)} dev server(s) listening from this repo's worktrees (pids {' '.join(servers[:5])}); "
                     f"list: bash {main_wt}/{sc}/reap_own.sh --report")
    return "; ".join(parts) or None


def priority_line(repo: Path):
    f = repo / "PRIORITIES.md"
    if not f.is_file():
        return None
    import queue_guard
    text = f.read_text()
    ids = queue_guard.ranked_ids(text)
    if not ids:
        return None
    title = next((l.strip() for l in text.splitlines() if queue_guard.LIST_LINE.match(l)), "")
    return f"top ranked in PRIORITIES.md: {title[:120]} (claim status not checked offline)"


def merge_line(repo: Path):
    """One resume line when `merge_checkpoint.sh save` left .git/perun-merge-state (a stalled merge)."""
    if not (repo / ".git" / "perun-merge-state").is_file():
        return None
    r = subprocess.run(["bash", str(HERE / "merge_checkpoint.sh"), "status"], cwd=repo,
                       capture_output=True, text=True, timeout=3)
    return r.stdout.strip() or None


def brief(repo: Path) -> list:
    """The ≤3 report lines for `repo`; each section is independent and fails silent."""
    lines = []
    _deadline[0] = time.monotonic() + BUDGET
    for fn in (merge_line, version_line, hygiene_line, priority_line):
        if time.monotonic() >= _deadline[0]:
            break  # budget spent: skip the remaining sections
        try:
            l = fn(repo)
        except Exception:
            l = None
        if l:
            lines.append(l)
    return lines[:3]


def main() -> int:
    try:
        try:
            cwd = json.load(sys.stdin).get("cwd")
        except Exception:
            cwd = None
        repo = Path(os.environ.get("CLAUDE_PROJECT_DIR") or cwd or os.getcwd())
        lines = brief(repo)
        if lines:
            text = "\n".join(lines)
            print(json.dumps({"systemMessage": text,
                              "hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": text}}))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
