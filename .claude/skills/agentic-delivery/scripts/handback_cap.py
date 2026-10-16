#!/usr/bin/env python3
"""SubagentStop hook: enforce a minimal, fields-only subagent handback.

Caps CHAT NARRATION only — a subagent's final chat message to its caller.
Deliverables (code, reports, long findings) belong in FILES, which are
uncapped by this hook; a compliant handback names the file path instead of
pasting its content into chat. Blocks (exit 2) a message longer than
MAX_CHARS or MAX_LINES; stderr carries the rewrite instruction. Per the
official docs (https://code.claude.com/docs/en/hooks, "Exit code 2 behavior
per event"), exit code 2 on SubagentStop "prevents the subagent from
stopping, continues the subagent" — so a block does not lose the subagent's
work, it sends the same turn back to compose a shorter handback.

WHAT COUNTS. Fenced code blocks (the fence lines included) and lines that start
with `! ` (a command the owner copies and runs with the host's `!` prefix) are
not counted toward MAX_CHARS or MAX_LINES, so a copy-paste command for the user
never forces a rewrite. To keep a long deliverable from hiding in a fence, the
whole message (those lines included) may not pass COPY_FACTOR (5) times
MAX_CHARS; past that it is blocked like any over-long handback, and the fix is
the same: put it in a file. An unclosed fence hides the rest of the message
from the line and char counts, and only that total limit then applies.

EXEMPTION IS A NAME LIST, NOT A TOOL CHECK. A subagent is exempt (never
capped, at any length) iff its `agent_type` is listed in the comma-separated
HANDBACK_EXEMPT_TYPES env var. The default list is four built-in agent types
whose chat answer is itself the deliverable: `Explore`, `Plan`,
`claude-code-guide`, `statusline-setup`. This hook does NOT inspect an
agent's tools — it cannot tell whether a type has a Write tool. Do NOT add a
custom read-only review lane's type here: exempt means uncapped, which
reopens the cost problem on a harness with no report file. Instead raise
MAX_CHARS/MAX_LINES for that type only via a second, matcher-scoped
SubagentStop entry with env overrides (agentic-delivery/references/
host-enforcement.md). Setting HANDBACK_EXEMPT_TYPES REPLACES the default
list, so repeat the defaults you still want.

After MAX_BLOCKS blocks for one agent_id, this hook lets the stop through
unconditionally, so a subagent that cannot comply never loops forever. Block
counters live in per-agent_id state files under a temp dir (sanitized id;
directory overridable via HANDBACK_STATE_DIR, e.g. for isolated tests).

STATUS TOKEN (opt-in: HANDBACK_REQUIRE_STATUS=1). When on, a non-exempt
handback must also carry a status: a line that starts (case-insensitive,
optionally after `status=` or `status:`) with `verified` or `unverified` as a
whole word, or the host style `status | evidence | next` whose status field
is `done`, `verified`, or `unverified`. The caller counts only verified work
as done; a lane stopped by its tool-call cap (lane_cap.py) hands back
UNVERIFIED with the remaining work. A handback with no status is blocked like
an over-long one (same MAX_BLOCKS release valve). Off by default so an
existing install's handbacks are not suddenly rejected; exempt types always
skip it.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import time

MAX_CHARS = int(os.environ.get("HANDBACK_MAX_CHARS", "800"))
MAX_LINES = int(os.environ.get("HANDBACK_MAX_LINES", "10"))
MAX_BLOCKS = 3
COPY_FACTOR = 5  # whole message, fenced code and `! ` lines included, may be at most this many times MAX_CHARS
# Default exempt agent-type NAMES (chat IS their deliverable). Matched by name
# only; override/extend via HANDBACK_EXEMPT_TYPES (replaces this list).
DEFAULT_EXEMPT_TYPES = "Explore,Plan,claude-code-guide,statusline-setup"
STATE_DIR = os.environ.get(
    "HANDBACK_STATE_DIR", os.path.join(tempfile.gettempdir(), "claude-handback-cap")
)


STATUS_RE = re.compile(
    r"^\W*(?:status\s*[=:]\s*)?(?:(?:un)?verified\b|done\s*\|)", re.MULTILINE | re.IGNORECASE
)


def _require_status():
    return os.environ.get("HANDBACK_REQUIRE_STATUS", "0") == "1"


def _exempt_types():
    return set(filter(None, os.environ.get("HANDBACK_EXEMPT_TYPES", DEFAULT_EXEMPT_TYPES).split(",")))


def _state_path(agent_id):
    safe = "".join(c for c in agent_id if c.isalnum() or c in "-_") or "unknown"
    return os.path.join(STATE_DIR, safe)


def _read_blocks(path):
    try:
        with open(path) as fh:
            return int(fh.read().strip() or 0)
    except (OSError, ValueError):
        return 0


# `git [-c k=v] [-C dir | -C "dir w/ space"] [--opt] push`; group 2/3 = the -C dir (quoted or bare)
PUSH_RE = re.compile(r"""\bgit\b((?:\s+-C\s+(?:"([^"]*)"|'([^']*)'|(\S+))|\s+-c\s+\S+|\s+-\S+)*)\s+push\b""")
PUSH_MAX_S = int(os.environ.get("HANDBACK_PUSH_MAX_S", "1800"))  # keep blocking while the push is live, at most this long


def _inside(p, root):
    p = os.path.realpath(p)
    return p == root or p.startswith(root.rstrip("/") + "/")


def _push_running(cwd):
    """True/False: is a `git push` (also `git -C <dir> push`) live with its cwd or -C dir inside `cwd`?
    None = could not check (no cwd, ps/lsof denied or failed): the hook stays advisory and fails open, but says so."""
    if not cwd or not os.path.isdir(cwd):
        return None
    try:
        r = subprocess.run(["ps", "-axo", "pid=,command="], capture_output=True, text=True, timeout=10)
        if r.returncode != 0 or not r.stdout.strip():
            return None
        root = os.path.realpath(cwd)
        for ln in r.stdout.splitlines():
            pid, _, cmd = ln.strip().partition(" ")
            m = PUSH_RE.search(cmd)
            if not m or not pid.isdigit() or int(pid) == os.getpid():
                continue
            cdir = m.group(2) or m.group(3) or m.group(4)
            if cdir and _inside(cdir, root):
                return True
            out = subprocess.run(["lsof", "-a", "-d", "cwd", "-p", pid, "-Fn"], capture_output=True, text=True, timeout=10)
            if out.returncode > 1:
                return None
            if any(n.startswith("n") and _inside(n[1:], root) for n in out.stdout.splitlines()):
                return True
        return False
    except (OSError, subprocess.SubprocessError):
        return None


def _counted(msg):
    """Lines of `msg` that count toward the cap: all but fenced code blocks (fence lines included) and
    lines starting with '! '. A one-line fence (an even number of ``` on a line starting with one) toggles
    nothing; an unclosed fence hides the rest of the message."""
    kept, fenced = [], False
    for ln in msg.split("\n"):
        if ln.lstrip().startswith("```"):
            fenced ^= ln.count("```") % 2 == 1
        elif not fenced and not ln.startswith("! "):
            kept.append(ln)
    return kept


def check(data):
    """Return the hook exit code (0 pass, 2 block) for one hook-input dict."""
    if str(data.get("agent_type") or "") in _exempt_types():
        return 0
    running = _push_running(data.get("cwd"))
    if running is None and data.get("cwd"):
        sys.stderr.write("COULD_NOT_CHECK: cannot tell whether a git push from this worktree is still running (ps/lsof unavailable).\n")
    if running:
        os.makedirs(STATE_DIR, exist_ok=True)
        path = _state_path(str(data.get("agent_id") or "unknown")) + ".push"
        try:  # file mtime = first block; keep blocking while the push is live, released after PUSH_MAX_S
            first = os.path.getmtime(path)
        except OSError:
            first = time.time()
            open(path, "w").close()
        if time.time() - first < PUSH_MAX_S:
            sys.stderr.write(
                "A git push from this worktree is still running (its pre-push hook may take 15+ minutes). "
                "You own it until it exits: wait with lane_guard.py wait --pid <pid> --timeout <s>, then hand back.\n"
            )
            return 2
    msg = data.get("last_assistant_message") or ""
    agent_id = str(data.get("agent_id") or "unknown")
    kept = _counted(msg) if msg else []
    chars, lines = len("\n".join(kept)), len(kept)
    too_long = chars > MAX_CHARS or lines > MAX_LINES or len(msg) > MAX_CHARS * COPY_FACTOR
    no_status = _require_status() and not STATUS_RE.search(msg)
    if not too_long and not no_status:
        return 0
    os.makedirs(STATE_DIR, exist_ok=True)
    path = _state_path(agent_id)
    blocks = _read_blocks(path)
    if blocks >= MAX_BLOCKS:
        return 0
    with open(path, "w") as fh:
        fh.write(str(blocks + 1))
    if not too_long:
        sys.stderr.write(
            "Handback has no status token. Start a line with VERIFIED (a green gate or a "
            "confirmed effect at the exact SHA) or UNVERIFIED (anything else, with the "
            "remaining work named), e.g. 'VERIFIED | <sha> | <gates>'.\n"
        )
        return 2
    sys.stderr.write(
        f"Handback too long ({chars} chars, {lines} lines; cap {MAX_CHARS} chars / "
        f"{MAX_LINES} lines, not counting fenced code or '! ' lines; whole message {len(msg)} chars, "
        f"limit {MAX_CHARS * COPY_FACTOR}). Rewrite your final message as a fields-only handback: "
        "key=value lines only (verdict, branch/sha, file paths, gate results, open issues). "
        "No prose, no progress narration. Put any long content in a file and give its path. "
        "Start a line with VERIFIED or UNVERIFIED.\n"
    )
    return 2


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return 0  # unparseable input: never wedge a subagent
    return check(data)


# ---------------------------------------------------------------------------
# --selftest — exercises check() directly (no subprocess, no real stdin) so
# the state dir and env overrides are trivially isolated per case.
# ---------------------------------------------------------------------------
def _selftest():
    import shutil

    global STATE_DIR
    tmp = tempfile.mkdtemp(prefix="handback-cap-selftest-")
    STATE_DIR = tmp
    passed = 0
    failed = 0

    def case(name, got, want):
        nonlocal passed, failed
        if got == want:
            passed += 1
            print(f"PASS  {name} (rc={got})")
        else:
            failed += 1
            print(f"FAIL  {name} (got rc={got}, want rc={want})")

    global _push_running
    real_push = _push_running
    _push_running = lambda cwd: {"/live": True, "/idle": False}.get(cwd)
    case("push-running-blocks", check({"agent_id": "p1", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 2)
    case("push-not-running-passes", check({"agent_id": "p2", "cwd": "/idle", "last_assistant_message": "VERIFIED"}), 0)
    case("push-unknown-passes-with-COULD_NOT_CHECK", check({"agent_id": "p5", "cwd": "/denied", "last_assistant_message": "VERIFIED"}), 0)
    case("push-exempt-type-passes", check({"agent_id": "p3", "agent_type": "Explore", "cwd": "/live", "last_assistant_message": "x"}), 0)
    for _ in range(MAX_BLOCKS + 5):  # many stop attempts while the push is live: still blocked
        rc = check({"agent_id": "p4", "cwd": "/live", "last_assistant_message": "VERIFIED"})
    case("push-live-keeps-blocking", rc, 2)
    os.utime(_state_path("p4") + ".push", (0, 0))  # first block long ago (> PUSH_MAX_S): released
    case("push-block-releases-after-max-age", check({"agent_id": "p4", "cwd": "/live", "last_assistant_message": "VERIFIED"}), 0)
    _push_running = real_push
    case("push-check-no-cwd-is-unknown", _push_running(""), None)
    real_run = subprocess.run
    def _deny(*a, **k):
        raise PermissionError("ps denied")
    subprocess.run = _deny
    try:
        case("ps-denied-is-unknown-not-false", _push_running(tmp), None)
    finally:
        subprocess.run = real_run
    def cd(c):
        m = PUSH_RE.search(c)
        return m and (m.group(2) or m.group(3) or m.group(4))
    case("git-dash-C-push-matches", cd("git -C /w/x push -q origin main"), "/w/x")
    case("git-dash-C-quoted-space-matches", cd('git -C "/w/dir w/ space" push'), "/w/dir w/ space")
    case("git-dash-c-kv-push-matches", bool(PUSH_RE.search("git -c core.x=1 push origin main")), True)
    case("git-dash-c-then-C-matches", cd("git -c a=b -C /w/y push"), "/w/y")
    case("plain-git-push-matches", bool(PUSH_RE.search("git push origin")), True)
    case("git-status-does-not-match", bool(PUSH_RE.search("git status --push")), False)

    # short message passes
    case("short-passes", check({"agent_id": "a1", "last_assistant_message": "VERIFIED | verdict=ok"}), 0)

    # status token is opt-in: off by default, a status-less short handback passes
    case("status-check-off-by-default", check({"agent_id": "s0", "last_assistant_message": "verdict=ok"}), 0)
    saved_req = os.environ.get("HANDBACK_REQUIRE_STATUS")
    os.environ["HANDBACK_REQUIRE_STATUS"] = "1"
    case("no-status-blocks-when-on", check({"agent_id": "s1", "last_assistant_message": "verdict=ok"}), 2)
    case("host-style-done-passes", check({"agent_id": "s8", "last_assistant_message": "done | 4b2765b | next=merge"}), 0)
    case("mixed-case-verified-passes", check({"agent_id": "s9", "last_assistant_message": "Verified | sha=abc"}), 0)
    case("done-in-prose-blocks", check({"agent_id": "s10", "last_assistant_message": "done with it, sha=abc"}), 2)
    case("unverified-passes", check({"agent_id": "s2", "last_assistant_message": "UNVERIFIED | todo=tests"}), 0)
    case("status-key-passes", check({"agent_id": "s3", "last_assistant_message": "sha=abc\nstatus=VERIFIED"}), 0)
    case("lowercase-verified-in-prose-blocks",
         check({"agent_id": "s4", "last_assistant_message": "all verified, sha=abc"}), 2)
    case("status-block-releases-after-max-blocks",
         [check({"agent_id": "s5", "last_assistant_message": "ok"}) for _ in range(MAX_BLOCKS + 1)][-1], 0)
    case("exempt-type-needs-no-status",
         check({"agent_id": "s6", "agent_type": "Explore", "last_assistant_message": "ok"}), 0)
    os.environ["HANDBACK_REQUIRE_STATUS"] = "0"
    try:
        case("status-check-off-via-env", check({"agent_id": "s7", "last_assistant_message": "ok"}), 0)
    finally:
        if saved_req is None:
            os.environ.pop("HANDBACK_REQUIRE_STATUS", None)
        else:
            os.environ["HANDBACK_REQUIRE_STATUS"] = saved_req

    # long message (chars) blocks MAX_BLOCKS times then releases
    long_msg = "x" * 900
    for i in range(MAX_BLOCKS):
        case(f"long-blocks-{i+1}", check({"agent_id": "a2", "last_assistant_message": long_msg}), 2)
    case("long-releases-after-max-blocks", check({"agent_id": "a2", "last_assistant_message": long_msg}), 0)

    # >10 lines but <800 chars still blocks
    many_lines = "\n".join(["line"] * 15)
    case("many-lines-blocks", check({"agent_id": "a3", "last_assistant_message": many_lines}), 2)

    # garbage stdin (simulated: main() catches JSON errors; check() only takes dicts,
    # so exercise main()'s parse-failure path via a broken stdin stand-in)
    class _BadStdin:
        def read(self):
            return "not json"

    real_stdin = sys.stdin
    sys.stdin = _BadStdin()
    try:
        case("garbage-stdin-passes", main(), 0)
    finally:
        sys.stdin = real_stdin

    # per-agent_id counters are independent: a4 fresh, still blocks despite a2 exhausted
    case("independent-agent-id-still-blocks", check({"agent_id": "a4", "last_assistant_message": long_msg}), 2)

    # exempt type: 5000-char message always passes, no state file, no block count spent
    huge_msg = "y" * 5000
    case(
        "exempt-type-huge-message-passes",
        check({"agent_id": "a5", "agent_type": "Explore", "last_assistant_message": huge_msg}),
        0,
    )
    # same huge message, non-exempt type: blocks
    case(
        "non-exempt-type-huge-message-blocks",
        check({"agent_id": "a6", "agent_type": "builder", "last_assistant_message": huge_msg}),
        2,
    )

    # exemption is by listed NAME: a custom review-lane type is capped by
    # default, and exempt once added via HANDBACK_EXEMPT_TYPES.
    lane = {"agent_id": "a7", "agent_type": "security-reviewer", "last_assistant_message": huge_msg}
    case("custom-type-capped-by-default", check(dict(lane)), 2)
    saved = os.environ.get("HANDBACK_EXEMPT_TYPES")
    os.environ["HANDBACK_EXEMPT_TYPES"] = DEFAULT_EXEMPT_TYPES + ",security-reviewer"
    try:
        case("custom-type-exempt-via-env", check(dict(lane, agent_id="a8")), 0)
    finally:
        if saved is None:
            os.environ.pop("HANDBACK_EXEMPT_TYPES", None)
        else:
            os.environ["HANDBACK_EXEMPT_TYPES"] = saved

    # matcher-scoped env override raises the cap for one agent type (the
    # host-enforcement.md fix for a report-file-less review lane) — must be a
    # real subprocess: MAX_LINES/MAX_CHARS are read from os.environ at import,
    # so an in-process check() call can never see a per-invocation override.

    twenty_lines = "\n".join(["VERIFIED"] + ["ok"] * 19)  # 20 lines, well under 800 chars

    def run_subproc(agent_id, extra_env):
        env = dict(os.environ, HANDBACK_STATE_DIR=tmp)
        if "HANDBACK_MAX_LINES" not in extra_env:
            env.pop("HANDBACK_MAX_LINES", None)
        env.update(extra_env)
        payload = json.dumps({"agent_id": agent_id, "last_assistant_message": twenty_lines})
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            input=payload, capture_output=True, text=True, env=env,
        )
        return proc.returncode

    case(
        "env-override-raises-cap-for-type",
        run_subproc("sub1", {"HANDBACK_MAX_LINES": "25"}),
        0,
    )
    case(
        "same-message-default-cap-blocks",
        run_subproc("sub2", {}),
        2,
    )

    shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main())
