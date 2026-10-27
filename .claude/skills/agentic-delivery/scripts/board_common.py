#!/usr/bin/env python3
"""board_common.py — shared post grammar and forge I/O for the board_* scripts.

WHY THIS EXISTS
---------------
`board_sync.py` (read), `board_post.py` (write), and `board_state.py` (render)
all speak ONE typed-post grammar over ONE forge channel (a GitHub issue's
comment stream). Keeping the grammar, the field rules, and the `gh api`
plumbing here means the three scripts can never disagree about what a valid
post is: a post `board_post.py` accepts is exactly a post `board_state.py`
folds into state, and a post it rejects is exactly one the state ignores —
save one deliberate exception: RELEASE's `rule:` is required at post time
only (see TYPE_REQUIRED), so a RELEASE that predates it still folds.

THE POST GRAMMAR (first line of every coordination comment)
-----------------------------------------------------------
    [agent:<id>] <TYPE> refs:<refs>[ <key>:<value>]...

  <id>     stable per-agent id, distinct from the shared forge account:
           [A-Za-z0-9][A-Za-z0-9._-]{0,63}
  <TYPE>   one of TYPES below. CHATTER_TYPES (STATUS/ACK/READY/LANDED) are
           recognised only so they can be REJECTED on write and collapsed on
           read: they are forge-derivable (the forge already holds CI, merge,
           and PR state) and an acknowledgement is the reader's cursor advance.
  <refs>   `-` (none) or a comma list of `#<n>` / path / label tokens.
  fields   space-separated key:value pairs, keys from FIELD_ORDER, each key at
           most once, values validated by FIELD_RULES. Which keys a TYPE may
           carry, and which it must carry, is in TYPE_FIELDS / TYPE_REQUIRED.

Everything after the first line is the free-text body. The grammar is
deliberately whitespace-free inside every value so a value can never smuggle
a second header, a newline, or markup into a rendered state record.

RUNNER INJECTION
----------------
Every forge or git call goes through a `runner(args, cwd=None) -> (rc, out,
err)` callable. Production uses `default_runner` (subprocess, no shell);
selftests pass `FakeGh`, an in-memory issue that answers the exact `gh api`
calls these scripts make — including `--paginate` output split into
100-comment pages and the `since=` filter — so no selftest touches the
network.

Pure module: importing it performs no I/O. Run `--selftest` to exercise the
grammar and the fake forge on their own.
"""
from __future__ import annotations

import json
import re
import subprocess
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402  (curl fallback for gh's macOS-sandbox TLS failure)
import sys
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlsplit

TYPES = ("CLAIM", "RELEASE", "DECISION", "HANDOFF", "BLOCKER", "FIX-CLAIM", "QUESTION", "ANSWER", "AUDIT", "REVIEW")
CHATTER_TYPES = ("STATUS", "ACK", "READY", "LANDED")

FIELD_ORDER = ("sha", "branch", "test", "verdict", "resolved", "topic", "ttl", "to", "of", "gate", "rule", "token")

AGENT_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}"
_AGENT_RE = re.compile(rf"^{AGENT_PATTERN}$")
_REFS_RE = re.compile(r"^(?:-|[A-Za-z0-9#._/-]+(?:,[A-Za-z0-9#._/-]+)*)$")
_HEADER_RE = re.compile(rf"^\[agent:(?P<agent>{AGENT_PATTERN})\] (?P<type>[A-Z][A-Z-]*)(?P<rest>(?: \S+)*)\s*$")
_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

MAX_TTL_MINUTES = 7 * 24 * 60  # a claim older than a week is abandoned, not "held"
DEFAULT_TTL_MINUTES = 120

# The closed set a RELEASE's `rule:` names: `earliest-claim` (the loser of a
# crossed claim stands down; claim_probe.py's YIELD), `done` (the work is
# finished; a holder's plain release gets it by default), `superseded` (the
# item no longer needs doing), `handoff` (released for a named peer to claim).
RELEASE_RULES = ("earliest-claim", "done", "superseded", "handoff")

FIELD_RULES = {
    "sha": re.compile(r"^[0-9a-f]{7,40}$"),
    "test": re.compile(r"^[A-Za-z0-9._/-]+(?:::[A-Za-z0-9_.-]+)?$"),
    "topic": re.compile(r"^[a-z0-9][a-z0-9._-]{0,63}$"),
    "ttl": re.compile(r"^[0-9]{1,5}$"),
    "to": _AGENT_RE,
    "of": re.compile(r"^[0-9]{1,20}$"),
    "gate": re.compile(r"^owner$"),
    # Read receipt (peer_ack.py): a directive carries `token:`, the recipient's ACK echoes it. An ACK is chatter only without one.
    "token": re.compile(r"^[0-9a-f]{8}$"),
    # The union of every TYPE's verdicts; VERDICTS below narrows it per TYPE.
    "verdict": re.compile(r"^(?:gap|done|na|approve|changes)$"),
    # REVIEW: the PR head branch the attested sha was read from, and how many
    # review findings the author resolved before the verdict.
    "branch": re.compile(r"^[A-Za-z0-9_][A-Za-z0-9._/-]{0,199}$"),
    "resolved": re.compile(r"^[0-9]{1,5}$"),
    # Why a RELEASE stands down, from RELEASE_RULES only: never a free-text
    # excuse. Optional in the grammar, so a RELEASE posted before `rule:`
    # existed still frees its claim on read; board_post.py requires it at
    # post time on a contested ref (multi-session-coordination.md: never
    # yield on a peer's own stand-down message alone).
    "rule": re.compile(rf"^(?:{'|'.join(map(re.escape, RELEASE_RULES))})$"),
}

# Per-TYPE verdicts. AUDIT: a real gap to build, already done, or not
# applicable (only `gap` is dispatchable work). REVIEW: an independent
# reviewer lane's verdict on one exact PR head (surface_check.py attested).
VERDICTS = {"AUDIT": ("gap", "done", "na"), "REVIEW": ("approve", "changes")}

# Which optional fields each TYPE may carry. A field outside its TYPE's set is
# a grammar error, so e.g. a CLAIM cannot carry `sha:` and look like a fix.
TYPE_FIELDS = {
    "CLAIM": {"ttl"},
    "RELEASE": {"rule"},
    "HANDOFF": {"to", "ttl", "token"},
    "ACK": {"token"},
    "DECISION": {"of", "topic", "token"},
    "BLOCKER": {"topic", "gate", "token"},
    "FIX-CLAIM": {"sha", "test", "topic"},
    "QUESTION": {"gate", "token"},
    "ANSWER": {"of"},
    "AUDIT": {"sha", "verdict", "topic"},
    "REVIEW": {"sha", "branch", "verdict", "resolved"},
}
# Required on read and write alike. RELEASE's `rule` is deliberately absent:
# it is a post-time requirement (board_post.py), not a grammar one.
TYPE_REQUIRED = {
    "HANDOFF": {"to"},
    "ACK": {"token"},
    "FIX-CLAIM": {"sha", "test"},
    "ANSWER": {"of"},
    "AUDIT": {"sha", "verdict"},
    "REVIEW": {"sha", "branch", "verdict", "resolved"},
}
# Types that act on a specific item and therefore cannot use `refs:-`.
TYPES_NEEDING_REFS = {"CLAIM", "RELEASE", "HANDOFF", "AUDIT", "REVIEW"}

PAGE_SIZE = 100  # GitHub REST maximum per_page for issue comments


class ForgeError(Exception):
    """A `gh` call failed or returned something that is not the expected JSON."""


def validate_repo(repo: str) -> bool:
    """True iff `repo` is an `owner/name` slug. Pure: no I/O."""
    return bool(_REPO_RE.match(repo or ""))


def validate_agent(agent: str) -> bool:
    """True iff `agent` matches the per-agent id grammar. Pure: no I/O."""
    return bool(_AGENT_RE.match(agent or ""))


def validate_post(ptype: str, refs: str, fields: dict) -> list:
    """Return grammar errors (empty list = valid) for one post's typed parts.

    Checks the TYPE is a real coordination type (chatter types get their own
    message), refs shape, that every field is allowed for the TYPE and matches
    its rule, that required fields are present, and the TTL range.
    Pure: no I/O. Does NOT check git reachability (see board_post.py).
    """
    errors = []
    if ptype in CHATTER_TYPES and not (ptype == "ACK" and "token" in fields):
        errors.append(
            f"{ptype} is chatter: forge state (CI, merges, PRs) is derivable and an ack is "
            "your board_sync.py cursor advance; do not post it"
        )
        return errors
    if ptype not in TYPES and ptype != "ACK":
        errors.append(f"unknown TYPE {ptype!r}; allowed: {', '.join(TYPES)}")
        return errors
    if not _REFS_RE.match(refs or ""):
        errors.append("refs must be '-' or a comma list of #<n>/path/label tokens (no spaces)")
    elif refs == "-" and ptype in TYPES_NEEDING_REFS:
        errors.append(f"{ptype} must name the item it acts on in refs:")
    allowed = TYPE_FIELDS[ptype]
    for key, value in fields.items():
        if key not in FIELD_RULES:
            errors.append(f"unknown field {key!r}")
        elif key not in allowed:
            errors.append(f"field {key}: is not allowed on {ptype}")
        elif not FIELD_RULES[key].match(value) or (key == "verdict" and value not in VERDICTS[ptype]):
            errors.append(f"field {key}: has a malformed value")
        elif key == "ttl" and not 1 <= int(value) <= MAX_TTL_MINUTES:
            errors.append(f"ttl must be 1..{MAX_TTL_MINUTES} minutes")
    for key in sorted(TYPE_REQUIRED.get(ptype, set())):
        if key not in fields:
            errors.append(f"{ptype} requires {key}:")
    if ptype == "REVIEW" and len(fields.get("sha", "")) not in (0, 40):
        errors.append("REVIEW sha: must be the full 40-char head sha (an attestation binds one exact head)")
    return errors


def format_header(agent: str, ptype: str, refs: str, fields: dict) -> str:
    """Render the canonical first line; fields always in FIELD_ORDER. Pure."""
    parts = [f"[agent:{agent}] {ptype} refs:{refs}"]
    parts += [f"{k}:{fields[k]}" for k in FIELD_ORDER if k in fields]
    return " ".join(parts)


def parse_header(line: str):
    """Parse a comment's first line into a post dict, or None if not typed.

    Returns None when the line does not start with the `[agent:<id>] <TYPE>`
    shape at all (an untyped comment). Otherwise returns
    `{"agent", "type", "refs", "fields", "errors"}`; `errors` is non-empty for
    a typed-looking line that breaks the grammar (missing refs:, duplicate or
    malformed field, chatter TYPE, ...). Callers treat a post as valid state
    input only when `errors` is empty. Pure: no I/O.
    """
    m = _HEADER_RE.match(line or "")
    if not m:
        return None
    post = {"agent": m.group("agent"), "type": m.group("type"), "refs": None, "fields": {}, "errors": []}
    tokens = m.group("rest").split()
    if not tokens or not tokens[0].startswith("refs:"):
        post["errors"].append("missing refs: right after the TYPE")
    else:
        post["refs"] = tokens.pop(0)[len("refs:"):]
    for tok in tokens:
        key, sep, value = tok.partition(":")
        if not sep or not value:
            post["errors"].append(f"token {tok!r} is not key:value")
        elif key in post["fields"]:
            post["errors"].append(f"duplicate field {key}:")
        else:
            post["fields"][key] = value
    if post["refs"] is not None:
        post["errors"] += validate_post(post["type"], post["refs"], post["fields"])
    return post


def first_line(body: str) -> str:
    """The first line of a comment body ('' for an empty body). Pure."""
    return (body or "").split("\n", 1)[0].rstrip("\r")


def snippet(body: str, skip_header: bool, limit: int = 100) -> str:
    """One display line from a comment body, safe for a terminal or markdown.

    Takes the first non-blank line (after the header line when `skip_header`),
    drops every non-printable character (so peer text cannot inject terminal
    escape sequences), removes `<`, `>`, `|` and backticks (so it cannot open an
    HTML comment, close the state markers, or break a table), collapses
    whitespace, and truncates to `limit` chars with an ellipsis. Pure.
    """
    lines = (body or "").splitlines()
    if skip_header and lines:
        lines = lines[1:]
    text = next((ln for ln in lines if ln.strip()), "")
    text = "".join(ch for ch in text if ch.isprintable() and ch not in "<>|`")
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def parse_ts(value: str) -> datetime:
    """Parse a GitHub `YYYY-MM-DDTHH:MM:SSZ` timestamp to an aware UTC datetime."""
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def format_ts(value: datetime) -> str:
    """Format an aware datetime back to GitHub's `...Z` form. Pure."""
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_runner(args, cwd=None):
    """Run a command without a shell; return (returncode, stdout, stderr).

    Side-effects: spawns a subprocess (network for `gh`). A missing binary is
    returned as rc 127 rather than raised, so callers fail closed uniformly.
    """
    try:
        proc = subprocess.run(args, cwd=cwd, capture_output=True, text=True, timeout=300)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out: {args[0]}"
    return gh_rest.fallback(args, proc.returncode, proc.stdout, proc.stderr)


def decode_pages(text: str) -> list:
    """Decode `gh api --paginate` output into one flat list.

    Without `--slurp`, `gh api --paginate` prints each page's JSON array back to
    back (`[...][...]`), which is not one JSON document. This decodes every
    array in sequence and concatenates them. Raises ForgeError on anything
    that is not a sequence of arrays, so a half-read never passes as complete.
    Pure: no I/O.
    """
    decoder = json.JSONDecoder()
    items, pos, text = [], 0, text or ""
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return items
        try:
            chunk, pos = decoder.raw_decode(text, pos)
        except ValueError as exc:
            raise ForgeError(f"gh output is not JSON: {exc}") from exc
        if not isinstance(chunk, list):
            raise ForgeError("gh --paginate output held a non-array page")
        items.extend(chunk)


def gh_list(runner, path: str) -> list:
    """GET every page of a list endpoint via `gh api --paginate`.

    Side-effects: one `gh` invocation through `runner`. Raises ForgeError on a
    non-zero exit or undecodable output.
    """
    rc, out, err = runner(["gh", "api", "--paginate", path])
    if rc != 0:
        raise ForgeError(f"gh api {path} failed (rc {rc}): {err.strip()[:300]}")
    return decode_pages(out)


def gh_object(runner, path: str) -> dict:
    """GET one JSON object via `gh api`. Raises ForgeError on failure."""
    rc, out, err = runner(["gh", "api", path])
    if rc != 0:
        raise ForgeError(f"gh api {path} failed (rc {rc}): {err.strip()[:300]}")
    try:
        obj = json.loads(out)
    except ValueError as exc:
        raise ForgeError(f"gh api {path} returned non-JSON: {exc}") from exc
    if not isinstance(obj, dict):
        raise ForgeError(f"gh api {path} did not return an object")
    return obj


def comments_path(repo: str, issue: int, since: str = "") -> str:
    """The REST path for an issue's comments, 100 per page, optional since=."""
    path = f"repos/{repo}/issues/{issue}/comments?per_page={PAGE_SIZE}"
    return path + (f"&since={since}" if since else "")


# --------------------------------------------------------------------------
# Selftest support: an in-memory issue that answers the exact gh calls above.
# --------------------------------------------------------------------------


def make_comment(cid: int, body: str, created: str, updated: str = "", login: str = "fleet-bot") -> dict:
    """Build one fixture comment in the REST shape the scripts read. Pure."""
    return {"id": cid, "body": body, "created_at": created, "updated_at": updated or created, "user": {"login": login}}


class FakeGh:
    """Selftest forge: one issue, its comments, and a call log. No network.

    Answers `gh api --paginate <comments path>` (filtering by `since=` on
    updated_at, as GitHub documents, and printing 100-comment pages back to
    back), `gh api repos/<r>/issues/<n>` (comment count + body),
    `gh api -X PATCH ... --input <file>` (body update), and
    `gh issue comment ... --body-file <file>` (append a comment). Set
    `fail = True` to make every call exit 1.
    """

    def __init__(self, comments=None, body: str = ""):
        self.comments = list(comments or [])
        self.body = body
        self.calls = []
        self.fail = False

    def __call__(self, args, cwd=None):
        self.calls.append(list(args))
        if self.fail:
            return 1, "", "HTTP 502: simulated outage"
        if args[:3] == ["gh", "api", "--paginate"]:
            query = parse_qs(urlsplit(args[3]).query)
            since = query.get("since", [""])[0]
            rows = sorted(
                (c for c in self.comments if not since or c["updated_at"] >= since), key=lambda c: c["id"]
            )
            pages = [rows[i : i + PAGE_SIZE] for i in range(0, len(rows), PAGE_SIZE)] or [[]]
            return 0, "".join(json.dumps(p) for p in pages), ""
        if args[:4] == ["gh", "api", "-X", "PATCH"]:
            with open(args[args.index("--input") + 1], encoding="utf-8") as fh:
                self.body = json.load(fh)["body"]
            return 0, "{}", ""
        if args[:2] == ["gh", "api"] and len(args) == 3:
            return 0, json.dumps({"comments": len(self.comments), "body": self.body}), ""
        if args[:3] == ["gh", "issue", "comment"]:
            return 0, "https://example.com/comment", ""
        return 2, "", f"FakeGh: unexpected call {args}"


def run_checks(name: str, cases) -> int:
    """Run `(label, fn)` selftest cases; each fn returns (ok, detail). Print + exit code."""
    failures = []
    for label, fn in cases:
        try:
            ok, detail = fn()
        except Exception as exc:  # a crashing case is a failing case, never a skip
            ok, detail = False, f"raised {type(exc).__name__}: {exc}"
        if not ok:
            failures.append(f"  FAIL {label}: {detail}")
    passed = len(cases) - len(failures)
    if failures:
        print(f"{name} SELFTEST FAILED ({passed}/{len(cases)}):")
        print("\n".join(failures))
        return 1
    print(f"{name} SELFTEST OK: {passed}/{len(cases)}")
    return 0


def _selftest() -> int:
    ok_hdr = "[agent:alpha] FIX-CLAIM refs:#12 sha:abc1234 test:tests/test_x.py::test_y topic:ratchet"
    cases = [
        ("header-roundtrip", lambda: (
            (lambda p: (p and not p["errors"] and format_header(p["agent"], p["type"], p["refs"], p["fields"]) == ok_hdr, p))(
                parse_header(ok_hdr)))),
        ("untyped-is-none", lambda: (parse_header("fixed it, merging now") is None, "typed")),
        ("chatter-type-errors", lambda: (bool(parse_header("[agent:a] STATUS refs:-")["errors"]), "no error")),
        ("missing-refs-errors", lambda: (bool(parse_header("[agent:a] CLAIM ttl:5")["errors"]), "no error")),
        ("field-not-allowed-errors", lambda: (bool(parse_header("[agent:a] CLAIM refs:#1 sha:abc1234")["errors"]), "no error")),
        ("duplicate-field-errors", lambda: (bool(parse_header("[agent:a] CLAIM refs:#1 ttl:5 ttl:6")["errors"]), "no error")),
        ("claim-needs-refs", lambda: (bool(validate_post("CLAIM", "-", {})), "accepted refs:-")),
        ("legacy-release-without-rule-parses", lambda: (
            (lambda p: (p is not None and not p["errors"], p))(parse_header("[agent:a] RELEASE refs:#1")))),
        ("release-rule-closed-set", lambda: (
            (lambda ok, bad: (not any(ok) and all(bad), (ok, bad)))(
                [validate_post("RELEASE", "#1", {"rule": r}) for r in ("earliest-claim", "done", "superseded", "handoff")],
                [validate_post("RELEASE", "#1", {"rule": r}) for r in ("because", "earliest", "done-ish")]))),
        ("fix-claim-needs-sha", lambda: (any("sha" in e for e in validate_post("FIX-CLAIM", "#1", {"test": "t.py"})), "no sha error")),
        ("audit-roundtrip", lambda: (
            (lambda p: (p is not None and not p["errors"] and p["fields"] == {"sha": "abc1234", "verdict": "na"}, p))(
                parse_header("[agent:a] AUDIT refs:#7,web/cart sha:abc1234 verdict:na")))),
        ("audit-needs-verdict-sha-refs", lambda: (
            (lambda e: (any("verdict" in x for x in e[0]) and any("sha" in x for x in e[0]) and e[1] and e[2], e))(
                (validate_post("AUDIT", "#7", {}), validate_post("AUDIT", "-", {"sha": "abc1234", "verdict": "gap"}),
                 validate_post("AUDIT", "#7", {"sha": "abc1234", "verdict": "maybe"}))))),
        ("snippet-strips-markup", lambda: (
            (lambda s: ("-->" not in s and "\x1b" not in s and "|" not in s, s))(
                snippet("head\n\x1b[31mred --> | x", True)))),
        ("pages-concatenated", lambda: (decode_pages("[1,2][3]\n[]") == [1, 2, 3], "bad decode")),
        ("pages-reject-object", lambda: (_raises(lambda: decode_pages("[1]{}"), ForgeError), "accepted object page")),
        ("fake-gh-pages-and-since", lambda: _fake_gh_case()),
    ]
    return run_checks("board_common", cases)


def _raises(fn, exc_type) -> bool:
    try:
        fn()
    except exc_type:
        return True
    return False


def _fake_gh_case():
    gh = FakeGh([make_comment(i, "x", "2026-01-01T00:00:00Z", f"2026-01-01T00:{i % 60:02d}:00Z") for i in range(1, 131)])
    rc, out, _ = gh(["gh", "api", "--paginate", comments_path("o/r", 1)])
    everything = decode_pages(out)
    rc2, out2, _ = gh(["gh", "api", "--paginate", comments_path("o/r", 1, "2026-01-01T00:59:00Z")])
    recent = decode_pages(out2)
    ok = rc == 0 and out.count("][") == 1 and len(everything) == 130 and rc2 == 0 and {c["id"] for c in recent} == {59, 119}
    return ok, f"pages={out.count('][') + 1} n={len(everything)} since={[c['id'] for c in recent]}"


if __name__ == "__main__":
    if sys.argv[1:] == ["--selftest"]:
        sys.exit(_selftest())
    print("board_common.py is a library for board_sync/board_post/board_state; run it with --selftest", file=sys.stderr)
    sys.exit(2)
