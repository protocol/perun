#!/usr/bin/env python3
"""board_post.py — compose one typed, capped, privacy-linted coordination post.

WHY THIS EXISTS (the failures it closes)
----------------------------------------
Free-text posting to a shared coordination issue fails in four recurring ways:
(1) chatter — status ticks, acks, "ready for you" pings — crowds out the posts
that change what another agent should do, and every one of them relays state
the forge already holds; (2) posts grow into multi-thousand-character state
documents nobody re-reads; (3) a body passed as a shell string gets
interpolated — one unquoted backtick runs a command and pastes its output
(emails, paths) into a shared thread; (4) "root cause found, fixed for good"
is asserted without a proof anyone can check, then recurs. This script is the
only write path: it builds the header itself, reads the body from a FILE, and
refuses a post that breaks a rule, before anything reaches the forge.

RULES (each rejection names the rule; exit 1)
---------------------------------------------
- TYPE must be one of CLAIM RELEASE DECISION HANDOFF BLOCKER FIX-CLAIM
  QUESTION ANSWER AUDIT. STATUS/ACK/READY/LANDED are rejected as chatter, except an ACK carrying `--token` (the explicit read receipt of a directive posted with `--token`, see peer_ack.py); a body
  that is only an acknowledgement ("ok", "thanks", "+1", ...) is rejected too.
- Header + body <= MAX_POST_CHARS (1000). Longer content belongs in a
  committed file or PR, linked from the post.
- The body comes from --body-file only; there is no --body flag, so nothing a
  shell could interpolate ever becomes post text. The body may not start with
  its own `[agent:` header (the script writes the only header).
- Privacy lint over header + body: email addresses, absolute home-directory
  paths, secret-shaped tokens (the same shapes this repo's committed
  `.banlist.txt` blocks), plus every pattern in a banlist file (`--banlist`,
  else `<git toplevel>/.banlist.txt` and its `.banlist.local.txt` sibling when
  present). Banlist patterns are `grep -E` syntax (POSIX classes, `\\<`/`\\>`),
  so they are matched by a `grep -E` subprocess exactly as
  `scripts/ci-gates.sh privacy` matches them, never by Python `re`. A hit
  reports the line number and rule name, never the match, so a secret is not
  echoed into a log. A pattern grep rejects, or a missing grep, fails closed
  (exit 2).
- FIX-CLAIM requires `--sha` and `--test`, and verifies both with git in
  --repo-dir: the SHA resolves to a commit that is an ancestor of the default
  branch (`--default-branch`, else `origin/HEAD`); the test path is a file
  (a blob, not a directory) at that SHA; and a `path::name` test id's name
  is defined there — after `def`/`function`/`func`/`fn`/`class` or as a
  whole quoted string, never a bare substring. A claim of "fixed" is thus
  pinned to a commit on the governing branch and a regression test that
  exists in it.
- RELEASE carries `rule:` from a closed set (earliest-claim, done,
  superseded, handoff). With no `--rule` the script reads the board: on a
  ref with a live crossed claim (you contested it, or a peer contests your
  hold) the RELEASE is rejected until it names one (a loser's stand-down
  cites `earliest-claim`, the verdict `claim_probe.py` prints as YIELD) —
  never yield on a peer's own "I stopped" message alone
  (`multi-session-coordination.md`); a holder's plain release gets
  `rule:done`. An unreadable board fails closed (exit 2). The requirement is
  post-time only: a RELEASE that predates `rule:` still frees its claim.
- AUDIT requires `--sha` and `--verdict gap|done|na`: one peer's measured
  verdict on each ref, taken at a commit that must be an ancestor of the
  default branch (the same check as FIX-CLAIM's sha). It is the shared
  backlog peers consume instead of re-measuring (`board_state.py --backlog`,
  `claim_probe.py`), so an audit of an unmerged tree is refused.
- REVIEW is a reviewed-attestation: an independent reviewer lane (its
  --agent id) records `--sha` (the FULL 40-char PR head it reviewed),
  `--branch`, `--verdict approve|changes`, and `--resolved N` (findings the
  author resolved), with refs naming the PR (`#<n>`). It is not checked
  against git here: `surface_check.py attested` reads it back and accepts it
  only for the PR's exact current head, from an id other than the author's,
  so any new push invalidates it.

OUTPUT
------
Writes the composed post (header line + body) to --out (default:
`<body-file>.post`) and prints the exact `gh issue comment ... --body-file`
command. With --post it runs that command instead (an external send: the
caller decides). Server time is authoritative, so the post carries no
hand-typed timestamp.

USAGE
-----
  board_post.py --repo O/N --issue N --agent ID --type CLAIM --refs '#12' \\
                --body-file note.md [--ttl 90] [--post]
  board_post.py ... --type FIX-CLAIM --refs '#12' --sha abc1234 \\
                --test tests/test_x.py::test_y [--topic ratchet] --body-file fix.md
  board_post.py ... --type AUDIT --refs '#12,web/cart' --sha abc1234 \\
                --verdict na --body-file audit.md
  board_post.py ... --agent reviewer-2 --type REVIEW --refs '#41' --sha <40-hex head> \\
                --branch lane/cart-fix --verdict approve --resolved 3 --body-file review.md
  board_post.py --selftest

Exit codes: 0 composed (and posted with --post); 1 rejected by a rule;
2 usage, git, forge, or banlist error.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys
import tempfile
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board_common as bc  # noqa: E402  (sibling module, path set above)
import board_state as bs  # noqa: E402

OK = 0
REJECTED = 1
ERROR = 2

MAX_POST_CHARS = 1000

# Secret shapes mirror the committed repo `.banlist.txt` so the lint works in a
# target repo that has no banlist; a present banlist ADDS to these.
BUILTIN_RULES = (
    ("email address", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    ("absolute home path", r"(?:/Users/|/home/|[A-Za-z]:\\Users\\)[^/\\\s]+"),
    ("cloud access key", r"(?:AKIA|ASIA)[0-9A-Z]{16}"),
    ("forge token", r"gh[pousr]_[A-Za-z0-9]{36,}"),
    ("chat token", r"xox[baprs]-[A-Za-z0-9-]{10,}"),
    ("api key", r"sk-[A-Za-z0-9]{20,}"),
    ("private key block", r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY-----"),
)
ACK_ONLY = {"ack", "acked", "ok", "okay", "thanks", "thank you", "ty", "+1", "noted", "roger", "ready", "done", "lgtm"}


class GitError(Exception):
    """A git query could not be answered (not a repo, bad ref, git missing)."""


def _grep_ere(pattern: str, text: str) -> tuple:
    """Run `grep -a -n -E -e PATTERN` over text on stdin; return (rc, stdout).

    Side-effects: spawns grep. `-a` keeps a NUL byte from collapsing the
    output to "Binary file matches" (which carries no line numbers); `-e`
    keeps a dash-leading pattern from parsing as an option. rc follows grep:
    0 match, 1 no match, >1 invalid pattern; a missing grep is rc 127.
    """
    try:
        proc = subprocess.run(["grep", "-a", "-n", "-E", "-e", pattern], input=text,
                              capture_output=True, text=True, timeout=30, check=False)
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    return proc.returncode, proc.stdout


def load_rules(banlist: str | None, repo_dir: str, runner) -> list:
    """Return (name, kind, pattern) rules: builtins (kind "re") plus banlist ("ere").

    Banlist patterns are `grep -E` syntax, so each is probed with grep on
    empty input and kept as an "ere" rule for `privacy_hits` to run through
    grep — Python `re` would silently misread `[[:space:]]` or `\\<`.
    Side-effects: reads banlist files; may run `git rev-parse` to find the
    repo top level; spawns one grep probe per pattern. Banlist patterns are
    named by file and ordinal only — a local banlist holds private
    identifiers, so its patterns are never echoed. Raises ValueError on an
    unreadable explicit banlist, a pattern grep rejects, or a missing grep
    (fail closed: an unchecked policy is not a passing one).
    """
    rules = [(name, "re", re.compile(rx)) for name, rx in BUILTIN_RULES]
    paths = []
    if banlist:
        if not os.path.isfile(banlist):
            raise ValueError(f"banlist not found: {banlist}")
        paths.append(banlist)
    else:
        rc, top, _ = runner(["git", "-C", repo_dir, "rev-parse", "--show-toplevel"])
        if rc == 0 and os.path.isfile(os.path.join(top.strip(), ".banlist.txt")):
            paths.append(os.path.join(top.strip(), ".banlist.txt"))
    for primary in list(paths):
        root, ext = os.path.splitext(primary)
        if os.path.isfile(f"{root}.local{ext}"):
            paths.append(f"{root}.local{ext}")
    for path in paths:
        with open(path, encoding="utf-8") as fh:
            actionable = [ln.strip() for ln in fh if ln.strip() and not ln.strip().startswith("#")]
        for i, pattern in enumerate(actionable, 1):
            name = f"{os.path.basename(path)} pattern #{i}"
            rc, _ = _grep_ere(pattern, "")
            if rc == 127:
                raise ValueError("grep not found; cannot apply the banlist (fail closed)")
            if rc > 1:
                raise ValueError(f"{name} is not a valid grep -E pattern (content withheld); failing closed")
            rules.append((name, "ere", pattern))
    return rules


def privacy_hits(text: str, rules: list) -> list:
    """Return 'line N: <rule name>' for every rule hit, never the matched text.

    Lines are split on newline only, the numbering grep uses, so a builtin
    ("re") hit and a banlist ("ere") hit on one line report the same N.
    Side-effects: one grep subprocess per "ere" rule. Raises ValueError when
    grep cannot answer (rc > 1), so a failed scan never reads as clean.
    """
    lines = text.split("\n")
    hit_lines = []
    for name, kind, pattern in rules:
        if kind == "re":
            hit_lines.append({n for n, line in enumerate(lines, 1) if pattern.search(line)})
            continue
        rc, out = _grep_ere(pattern, text)
        if rc > 1:
            raise ValueError(f"{name}: grep failed (rc {rc}); failing closed")
        hit_lines.append({int(row.split(":", 1)[0]) for row in out.splitlines() if row.split(":", 1)[0].isdigit()})
    return [f"line {n}: {rules[i][0]}" for n in range(1, len(lines) + 1)
            for i in range(len(rules)) if n in hit_lines[i]]


def _ere_escape(literal: str) -> str:
    """Backslash-escape every POSIX ERE metacharacter in literal. Pure."""
    return re.sub(r"([.\[\]\\(){}*+?^$|])", r"\\\1", literal)


def verify_on_default(sha: str, default_branch: str | None, repo_dir: str, runner) -> tuple:
    """Return `(violations, full_sha)`: is `sha` a commit reachable from the default branch?

    Shared by FIX-CLAIM and AUDIT. Side-effects: read-only git queries through
    `runner`. Raises GitError when git cannot answer at all (no repo, no
    resolvable default branch), which the caller turns into exit 2 — an
    unanswerable proof is not a passing proof.
    """
    def git(*args):
        return runner(["git", "-C", repo_dir, *args])

    ref = default_branch
    if ref and ref.startswith("-"):
        raise GitError(f"default branch {ref!r} looks like an option, not a ref")
    if not ref:
        rc, out, _ = git("symbolic-ref", "--quiet", "refs/remotes/origin/HEAD")
        if rc != 0:
            raise GitError("cannot resolve origin/HEAD; pass --default-branch")
        ref = out.strip()
    rc, _, _ = git("rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")
    if rc != 0:
        raise GitError(f"default branch {ref!r} does not resolve to a commit")
    rc, full, _ = git("rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if rc != 0:
        return [f"sha:{sha} is not a commit in this repository"], ""
    full = full.strip()
    rc, _, err = git("merge-base", "--is-ancestor", full, ref)
    if rc == 1:
        return [f"sha:{sha} is not reachable from the default branch {ref} (off the governing branch it proves nothing)"], ""
    if rc != 0:
        raise GitError(f"merge-base failed: {err.strip()[:200]}")
    return [], full


def verify_fix_claim(sha: str, test: str, default_branch: str | None, repo_dir: str, runner) -> list:
    """Return rule violations for a FIX-CLAIM's sha:/test: (empty = verified).

    Side-effects: read-only git queries through `runner`. Raises GitError when
    git cannot answer at all (see verify_on_default).
    """
    def git(*args):
        return runner(["git", "-C", repo_dir, *args])

    errors, full = verify_on_default(sha, default_branch, repo_dir, runner)
    if errors:
        return errors
    path, _, name = test.partition("::")
    rc, kind, _ = git("cat-file", "-t", f"{full}:{path}")
    if rc != 0:
        return [f"test:{test} — file {path} does not exist at sha:{sha}"]
    if kind.strip() != "blob":
        return [f"test:{test} — {path} is a {kind.strip()}, not a file, at sha:{sha}"]
    if name:
        lit = _ere_escape(name)
        definition = (f"(^|[^A-Za-z0-9_])(def|function|func|fn|class)[[:space:]]+{lit}([^A-Za-z0-9_]|$)"
                      f"|[\"'`]{lit}[\"'`]")
        rc, _, err = git("grep", "-q", "-E", "-e", definition, full, "--", path)
        if rc == 1:
            return [(f"test:{test} — no definition of {name!r} in {path} at sha:{sha} "
                     "(a bare substring, such as a prefix of another test's name, is not a match)")]
        if rc != 0:
            raise GitError(f"git grep failed: {err.strip()[:200]}")
    return []


def settle_release_rule(args, fields: dict, runner) -> list:
    """Decide a `--rule`-less RELEASE's `rule:` from the board; return violations.

    Reads and folds the board (`board_state.read_board` + `fold`): when any
    ref carries a live crossed claim (`board_state.release_rule_needed`) the
    RELEASE must name its rule and one violation per reason is returned;
    otherwise it is a plain release and `fields["rule"]` is set to `done`.
    Side-effects: two read-only `gh api` calls through `runner`; mutates
    `fields`. Raises bc.ForgeError on a failed, truncated, or unfoldable
    read, which the caller turns into exit 2 — an unread board is not an
    uncontested one.
    """
    _, comments = bs.read_board(args.repo, args.issue, runner)
    try:
        state = bs.fold(comments, datetime.now(timezone.utc))
    except (KeyError, TypeError, ValueError) as exc:
        raise bc.ForgeError(f"board comments could not be folded ({exc})") from exc
    refs = [r for r in args.refs.split(",") if r != "-"]
    reasons = bs.release_rule_needed(state, args.agent, refs)
    if reasons:
        return [f"RELEASE requires rule: here; {reason}" for reason in reasons]
    fields["rule"] = "done"
    return []


def compose(args, body: str, rules: list, runner) -> tuple:
    """Validate one post; return (violations, composed_text). Pure except git and the board read.

    Side-effects: only the read-only git queries a FIX-CLAIM or AUDIT needs,
    and, for a RELEASE with no --rule, the board read in settle_release_rule.
    """
    fields = {k: str(v) for k, v in (("sha", args.sha), ("branch", args.branch), ("test", args.test),
                                     ("verdict", args.verdict), ("resolved", args.resolved), ("topic", args.topic),
                                     ("ttl", args.ttl), ("to", args.to), ("of", args.of), ("gate", args.gate),
                                     ("rule", args.rule), ("token", args.token)) if v is not None}
    errors = []
    if not bc.validate_agent(args.agent):
        errors.append("--agent must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}")
    errors += bc.validate_post(args.type, args.refs, fields)
    stripped = body.strip()
    if not stripped:
        errors.append("body is empty: a post with nothing to say is chatter")
    elif stripped.lower().strip(" .!") in ACK_ONLY and not (args.type == "ACK" and "token" in fields):
        errors.append("body is only an acknowledgement: your board_sync.py cursor advance is the ack")
    if stripped.startswith("[agent:"):
        errors.append("body starts with its own [agent:] header; the script writes the only header")
    if args.type == "RELEASE" and "rule" not in fields and not errors:
        errors += settle_release_rule(args, fields, runner)
    header = bc.format_header(args.agent, args.type, args.refs, fields)
    text = f"{header}\n{body.rstrip()}\n"
    if len(text) > MAX_POST_CHARS:
        errors.append(f"post is {len(text)} chars, over the {MAX_POST_CHARS}-char cap; link a committed file or PR instead")
    errors += [f"privacy: {h}" for h in privacy_hits(text, rules)]
    if args.type == "FIX-CLAIM" and not errors:
        errors += verify_fix_claim(args.sha, args.test, args.default_branch, args.repo_dir, runner)
    if args.type == "AUDIT" and not errors:
        errors += verify_on_default(args.sha, args.default_branch, args.repo_dir, runner)[0]
    return errors, text


def build_parser() -> argparse.ArgumentParser:
    """The CLI parser. There is deliberately no --body option. Pure."""
    p = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0], allow_abbrev=False)
    p.add_argument("--repo")
    p.add_argument("--issue", type=int)
    p.add_argument("--agent", default="")
    p.add_argument("--type", default="")
    p.add_argument("--refs", default="-")
    p.add_argument("--body-file")
    p.add_argument("--sha")
    p.add_argument("--test")
    p.add_argument("--verdict", help="AUDIT: gap | done | na; REVIEW: approve | changes")
    p.add_argument("--branch", help="REVIEW only: the PR head branch the attested --sha was read from")
    p.add_argument("--resolved", type=int, help="REVIEW only: review findings resolved before the verdict")
    p.add_argument("--topic")
    p.add_argument("--ttl", type=int)
    p.add_argument("--to")
    p.add_argument("--of")
    p.add_argument("--gate")
    p.add_argument("--rule", help=f"RELEASE only: {' | '.join(bc.RELEASE_RULES)}; required on a contested ref, "
                                  "else defaults to done")
    p.add_argument("--token", help="read receipt: on a DECISION/HANDOFF/BLOCKER/QUESTION it asks for an ack; on an ACK it is the explicit token ack (peer_ack.py)")
    p.add_argument("--default-branch")
    p.add_argument("--repo-dir", default=".")
    p.add_argument("--banlist")
    p.add_argument("--out")
    p.add_argument("--post", action="store_true", help="send it (an external write); default prints the command")
    p.add_argument("--selftest", action="store_true")
    return p


def run(argv, runner, out=sys.stdout) -> int:
    """Parse, validate, write the composed post, then print or send. Returns an exit code.

    Side-effects: reads the body file and banlist, git queries, writes --out,
    and with --post runs `gh issue comment` through `runner`.
    """
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return ERROR if exc.code else OK
    if args.selftest:
        return _selftest()
    if not (args.repo and bc.validate_repo(args.repo) and args.issue and args.issue > 0 and args.body_file):
        print("board_post: --repo OWNER/NAME, --issue N (>0) and --body-file are required", file=sys.stderr)
        return ERROR
    try:
        with open(args.body_file, encoding="utf-8") as fh:
            body = fh.read()
        rules = load_rules(args.banlist, args.repo_dir, runner)
        errors, text = compose(args, body, rules, runner)
    except (OSError, ValueError, GitError, bc.ForgeError) as exc:
        print(f"board_post: {exc}", file=sys.stderr)
        return ERROR
    if errors:
        print("board_post: REJECTED", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return REJECTED
    dest = args.out or f"{args.body_file}.post"
    with open(dest, "w", encoding="utf-8") as fh:
        fh.write(text)
    cmd = ["gh", "issue", "comment", str(args.issue), "--repo", args.repo, "--body-file", dest]
    if not args.post:
        out.write(" ".join(shlex.quote(c) for c in cmd) + "\n")
        return OK
    rc, stdout, err = runner(cmd)
    if rc != 0:
        print(f"board_post: gh issue comment failed (rc {rc}): {err.strip()[:300]}", file=sys.stderr)
        return ERROR
    out.write(stdout)
    return OK


# --------------------------------------------------------------------------
# selftest
# --------------------------------------------------------------------------


def _git_repo(tmp: str) -> dict:
    """A throwaway repo: main has the regression test; side has an unmerged commit."""
    repo = os.path.join(tmp, "repo")
    os.makedirs(os.path.join(repo, "tests"))
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_SYSTEM=os.devnull)

    def git(*a):
        return subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, text=True, env=env).stdout.strip()

    git("init", "-q", "-b", "main")
    git("config", "user.email", "jane@example.com")
    git("config", "user.name", "Jane Smith")
    with open(os.path.join(repo, "tests", "test_ratchet.py"), "w") as fh:
        fh.write("def test_allowlist_pin():\n    assert True\n")
    git("add", ".")
    git("commit", "-q", "-m", "fix: pin allowlist")
    on_main = git("rev-parse", "HEAD")
    git("checkout", "-q", "-b", "side")
    git("commit", "-q", "--allow-empty", "-m", "unmerged work")
    off_main = git("rev-parse", "HEAD")
    git("checkout", "-q", "main")
    return {"repo": repo, "on": on_main[:10], "off": off_main[:10]}


def _selftest() -> int:
    tmp = tempfile.mkdtemp(prefix="board-post-selftest-")
    g = _git_repo(tmp)
    banlist = os.path.join(tmp, "banlist.txt")
    with open(banlist, "w") as fh:
        fh.write("# fixture policy\nAcme Capital\n\\<Jane\\>\nJane[[:space:]]Smith\n")
    bad_banlist = os.path.join(tmp, "bad-banlist.txt")
    with open(bad_banlist, "w") as fh:
        fh.write("Acme[\n")

    def attempt(body, *extra, post=False, board=(), outage=False):
        path = os.path.join(tmp, f"body-{len(os.listdir(tmp))}.md")
        with open(path, "w") as fh:
            fh.write(body)
        gh = bc.FakeGh([bc.make_comment(i, text, "2026-01-05T10:00:00Z") for i, text in enumerate(board, 1)])
        gh.fail = outage
        runner = lambda a, cwd=None: gh(a, cwd) if a[0] == "gh" else bc.default_runner(a, cwd)  # noqa: E731
        argv = ["--repo", "acme/board", "--issue", "7", "--agent", "alpha", "--body-file", path,
                "--repo-dir", g["repo"], "--default-branch", "main", "--banlist", banlist, *extra]
        if post:
            argv.append("--post")
        result, stderr = _capture_stderr(lambda buf: run(argv, runner, buf))
        return result, stderr, gh, path

    def expect(code_want, body, *extra, needle="", post=False, absent="", board=(), outage=False):
        (rc, stdout), stderr, gh, path = attempt(body, *extra, post=post, board=board, outage=outage)
        ok = rc == code_want and needle in (stderr + stdout) and not (absent and absent in stderr + stdout)
        return ok, f"rc={rc} want={code_want} out={stdout!r} err={stderr!r}"

    fix = ["--type", "FIX-CLAIM", "--refs", "#12", "--topic", "ratchet"]
    review = ["--type", "REVIEW", "--refs", "#12", "--sha", "a" * 40, "--branch", "lane/cart-fix"]
    token = "gh" + "p_" + "A1b2" * 10  # built at runtime so no token-shaped literal is committed

    def review_accepted():
        (rc, _), stderr, _, path = attempt("Reviewed the full diff; 3 findings fixed and re-checked.", *review,
                                           "--verdict", "approve", "--resolved", "3")
        posted = open(path + ".post").read() if rc == OK else ""
        want = f"[agent:alpha] REVIEW refs:#12 sha:{'a' * 40} branch:lane/cart-fix verdict:approve resolved:3\n"
        return rc == OK and posted.startswith(want), f"{rc} {stderr!r} {posted!r}"

    def valid_claim():
        (rc, stdout), _, gh, path = attempt("Taking the ratchet gate.", "--type", "CLAIM", "--refs", "#12", "--ttl", "90")
        posted = open(path + ".post").read()
        ok = (rc == OK and posted.startswith("[agent:alpha] CLAIM refs:#12 ttl:90\n")
              and "gh issue comment 7 --repo acme/board --body-file" in stdout and gh.calls == [])
        return ok, f"{rc} {stdout!r} {posted!r}"

    def post_sends_via_body_file():
        (rc, _), _, gh, path = attempt("Handing #12 over.", "--type", "HANDOFF", "--refs", "#12", "--to", "beta", post=True)
        call = gh.calls[-1] if gh.calls else []
        return rc == OK and call[:3] == ["gh", "issue", "comment"] and call[-1] == path + ".post", str(gh.calls)

    def no_body_flag():
        argv = ["--repo", "acme/board", "--issue", "7", "--agent", "a", "--type", "CLAIM", "--body", "x"]
        (rc, _), stderr = _capture_stderr(lambda buf: run(argv, bc.FakeGh(), buf))
        return rc == ERROR and "unrecognized arguments: --body" in stderr, f"rc={rc} {stderr!r}"

    def exact_cap_accepted():
        header = "[agent:alpha] QUESTION refs:-\n"
        body = "q" * (1000 - len(header) - 1)  # literal 1000: the cap is pinned, not read back
        return expect(OK, body, "--type", "QUESTION")

    def release_plain_holder_defaults_done():
        # A holder releasing an uncontested claim needs no --rule: the script
        # reads the board and writes `rule:done` into the header itself.
        (rc, stdout), stderr, _, path = attempt("Shipped; releasing.", "--type", "RELEASE", "--refs", "#12",
                                                board=("[agent:alpha] CLAIM refs:#12\ntaking it",))
        posted = open(path + ".post").read() if rc == OK else ""
        return rc == OK and posted.startswith("[agent:alpha] RELEASE refs:#12 rule:done\n"), f"{rc} {stderr!r} {posted!r}"

    def token_not_echoed():
        (rc, _), stderr, _, _ = attempt(f"use {token}", "--type", "QUESTION")
        return rc == REJECTED and "forge token" in stderr and token not in stderr, stderr

    cases = [
        ("valid-claim-composed-not-sent", valid_claim),
        ("post-sends-via-body-file", post_sends_via_body_file),
        ("status-chatter-rejected", lambda: expect(REJECTED, "still on it", "--type", "STATUS", needle="chatter")),
        ("ack-chatter-rejected", lambda: expect(REJECTED, "x", "--type", "ACK", needle="chatter")),
        ("ready-chatter-rejected", lambda: expect(REJECTED, "x", "--type", "READY", needle="chatter")),
        ("ack-only-body-rejected", lambda: expect(REJECTED, "Thanks!", "--type", "ANSWER", "--of", "123", needle="acknowledgement")),
        ("unknown-type-rejected", lambda: expect(REJECTED, "x", "--type", "PING", needle="unknown TYPE")),
        ("oversize-rejected", lambda: expect(REJECTED, "x" * 1000, "--type", "DECISION", needle="1000-char cap")),
        ("exact-cap-accepted", exact_cap_accepted),
        ("no-body-flag-exists", no_body_flag),
        ("forged-body-header-rejected", lambda: expect(REJECTED, "[agent:beta] DECISION refs:-\nx", "--type", "QUESTION", needle="own [agent:]")),
        ("email-rejected", lambda: expect(REJECTED, "ping jane@example.com", "--type", "QUESTION", needle="email address")),
        ("home-path-rejected", lambda: expect(REJECTED, "see /Users/jsmith/x.log", "--type", "QUESTION", needle="home path")),
        ("token-rejected-not-echoed", token_not_echoed),
        ("banlist-pattern-rejected", lambda: expect(REJECTED, "for Acme Capital", "--type", "QUESTION", needle="banlist.txt pattern #1")),
        ("banlist-ere-word-boundary-matches", lambda: expect(REJECTED, "ask\nJane first", "--type", "QUESTION", needle="line 3: banlist.txt pattern #2")),
        ("banlist-ere-posix-class-matches", lambda: expect(REJECTED, "cc Jane Smith", "--type", "QUESTION", needle="banlist.txt pattern #3")),
        ("banlist-ere-word-boundary-not-substring", lambda: expect(OK, "ask Janet first", "--type", "QUESTION")),
        ("banlist-invalid-ere-fails-closed", lambda: expect(ERROR, "x y", "--type", "QUESTION", "--banlist", bad_banlist, needle="not a valid grep -E pattern", absent="Acme[")),
        ("zero-ttl-rejected", lambda: expect(REJECTED, "taking it", "--type", "CLAIM", "--refs", "#12", "--ttl", "0", needle="ttl must be")),
        ("release-plain-holder-defaults-done", release_plain_holder_defaults_done),
        ("release-by-loser-without-rule-rejected", lambda: expect(
            REJECTED, "standing down", "--type", "RELEASE", "--refs", "#12", needle="earliest-claim",
            board=("[agent:beta] CLAIM refs:#12\nx", "[agent:alpha] CLAIM refs:#12\ncrossed"))),
        ("release-of-contested-hold-without-rule-rejected", lambda: expect(
            REJECTED, "done here", "--type", "RELEASE", "--refs", "#12", needle="agent:beta contests",
            board=("[agent:alpha] CLAIM refs:#12\nx", "[agent:beta] CLAIM refs:#12\ncrossed"))),
        ("release-by-loser-with-rule-accepted", lambda: expect(
            OK, "standing down: beta claimed first.", "--type", "RELEASE", "--refs", "#12", "--rule", "earliest-claim",
            board=("[agent:beta] CLAIM refs:#12\nx", "[agent:alpha] CLAIM refs:#12\ncrossed"))),
        ("release-rule-outside-closed-set-rejected", lambda: expect(
            REJECTED, "standing down", "--type", "RELEASE", "--refs", "#12", "--rule", "because", needle="rule: has a malformed")),
        ("release-board-unreadable-fails-closed", lambda: expect(
            ERROR, "done here", "--type", "RELEASE", "--refs", "#12", needle="simulated outage", outage=True)),
        ("release-with-rule-accepted", lambda: expect(OK, "standing down: peer claimed first.", "--type", "RELEASE", "--refs", "#12", "--rule", "earliest-claim")),
        ("claim-without-refs-rejected", lambda: expect(REJECTED, "taking it", "--type", "CLAIM", needle="must name the item")),
        ("bad-agent-id-rejected", lambda: expect(REJECTED, "x y", "--type", "QUESTION", "--agent", "a b", needle="--agent")),
        ("fix-claim-without-sha-rejected", lambda: expect(REJECTED, "fixed", *fix, "--test", "tests/test_ratchet.py", needle="requires sha:")),
        ("fix-claim-without-test-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["on"], needle="requires test:")),
        ("fix-claim-off-default-branch-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["off"], "--test", "tests/test_ratchet.py", needle="not reachable")),
        ("fix-claim-unknown-sha-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", "deadbeef12", "--test", "tests/test_ratchet.py", needle="not a commit")),
        ("fix-claim-missing-test-file-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["on"], "--test", "tests/test_nope.py", needle="does not exist")),
        ("fix-claim-missing-test-name-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["on"], "--test", "tests/test_ratchet.py::test_other", needle="no definition")),
        ("fix-claim-directory-path-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["on"], "--test", "tests", needle="is a tree, not a file")),
        ("fix-claim-trivial-substring-name-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["on"], "--test", "tests/test_ratchet.py::test", needle="no definition")),
        ("fix-claim-prefix-name-rejected", lambda: expect(REJECTED, "fixed", *fix, "--sha", g["on"], "--test", "tests/test_ratchet.py::test_allowlist", needle="no definition")),        ("fix-claim-verified-accepted", lambda: expect(OK, "Pinned allowlist; regression test added.", *fix, "--sha", g["on"], "--test", "tests/test_ratchet.py::test_allowlist_pin")),
        ("audit-without-verdict-rejected", lambda: expect(REJECTED, "measured", "--type", "AUDIT", "--refs", "#12", "--sha", g["on"], needle="requires verdict:")),
        ("audit-bad-verdict-rejected", lambda: expect(REJECTED, "measured", "--type", "AUDIT", "--refs", "#12", "--sha", g["on"], "--verdict", "maybe", needle="verdict: has a malformed")),
        ("audit-off-default-branch-rejected", lambda: expect(REJECTED, "measured", "--type", "AUDIT", "--refs", "#12", "--sha", g["off"], "--verdict", "gap", needle="not reachable")),
        ("audit-verified-accepted", lambda: expect(OK, "Measured at mainline: no counterpart module.", "--type", "AUDIT", "--refs", "#12,web/cart", "--sha", g["on"], "--verdict", "na")),
        ("review-attestation-accepted", review_accepted),
        ("review-short-sha-rejected", lambda: expect(REJECTED, "reviewed", "--type", "REVIEW", "--refs", "#12", "--sha", "a" * 12, "--branch", "lane/cart-fix", "--verdict", "approve", "--resolved", "0", needle="full 40-char head sha")),
        ("review-without-branch-rejected", lambda: expect(REJECTED, "reviewed", "--type", "REVIEW", "--refs", "#12", "--sha", "a" * 40, "--verdict", "approve", "--resolved", "0", needle="requires branch:")),
        ("review-without-resolved-rejected", lambda: expect(REJECTED, "reviewed", *review, "--verdict", "approve", needle="requires resolved:")),
        ("review-audit-verdict-rejected", lambda: expect(REJECTED, "reviewed", *review, "--verdict", "gap", "--resolved", "0", needle="verdict: has a malformed")),
        ("audit-review-verdict-rejected", lambda: expect(REJECTED, "measured", "--type", "AUDIT", "--refs", "#12", "--sha", g["on"], "--verdict", "approve", needle="verdict: has a malformed")),
        ("fix-claim-option-shaped-branch-errors", lambda: expect(ERROR, "fixed", *fix, "--sha", g["on"], "--test", "tests/test_ratchet.py", "--default-branch=--output=x", needle="looks like an option")),
        ("fix-claim-bad-default-branch-errors", lambda: expect(ERROR, "fixed", *fix, "--sha", g["on"], "--test", "tests/test_ratchet.py", "--default-branch", "nope", needle="does not resolve")),
    ]
    return bc.run_checks("board_post", cases)


def _capture_stderr(fn):
    """Run fn(stdout_buffer) with stderr captured; return ((rc, stdout), stderr)."""
    import io

    out, err, saved = io.StringIO(), io.StringIO(), sys.stderr
    sys.stderr = err
    try:
        rc = fn(out)
    finally:
        sys.stderr = saved
    return (rc, out.getvalue()), err.getvalue()


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:], bc.default_runner))
