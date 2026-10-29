#!/usr/bin/env python3
"""Verify a "done / fixed / deployed" claim on the AUTHORITATIVE surface.

A merged PR, a green CI run, or a local tree is a PROXY for delivery; the
surface a reviewer actually opens can be silently stale (a broken auto-sync
leaves a preview hours behind HEAD), and a local `main` can be thousands of
commits behind the real base. This script checks the claim where it counts.

WHAT IT PROVES — AND WHAT IT DOES NOT. A PASS proves that the surface serves
(or the remote branch contains) the claimed build. It does NOT prove the
feature works, renders, or is correct: pair it with the functional check.

Modes (stdlib only, no third-party dependency):

  served --url U --expect-sha S --probe SPEC [--probe SPEC ...]
      Fetch the running app and extract the build/commit id the SERVING
      PROCESS reports. SPEC is one of:
        header:NAME              a response header of U (case-insensitive)
        meta:NAME                <meta name|property="NAME" content="..."> in U
        path:/version.json:key   JSON at that same-origin path; key is dotted
                                 (e.g. build.sha)
      PASS only when at least one probe yields an id and every yielded id
      matches S (the shorter of the two, at least 7 hex chars, is a prefix of
      the longer). A value that is not a commit sha — a data timestamp, a
      semver, a JSON number — is NOT a build id: a payload's "data as of"
      stamp dates the artifact, not the running code. Redirects are NOT
      followed (a redirect means U is not the surface that serves the build;
      re-run with the Location URL if that is the real surface). --timeout
      bounds each socket read and, as a wall-clock cap, the body read.

  ref --repo DIR --branch B --expect-sha S [--remote origin] [--timeout 120]
      Fetch B from the remote the reviewer uses, then PASS only when S is an
      ancestor of (reachable from) that fetched remote head. A local branch or
      a stale local tree is never consulted. Fetch writes the remote-tracking
      ref refs/remotes/<remote>/<B>, exactly as a plain `git fetch` would.
      Git runs with GIT_TERMINAL_PROMPT=0 and no terminal; a call past
      --timeout seconds is killed and reported as COULD_NOT_CHECK.
      --require-clean also FAILs when --repo has any tracked change (staged
      or not) or any untracked, non-ignored file that is not committed
      (`git status --untracked-files=normal`): a commit a hook rejected
      leaves the edit staged, and a new file never added is left behind,
      while the already-pushed HEAD still passes — edit done is not
      committed, and committed is not pushed. Pass HEAD's sha with it.

  checks --gh-repo OWNER/NAME --sha S [--require NAME ...] [--timeout 60]
      Read the forge's check-runs for S (`gh api`, filter=latest, every
      page) and judge each check NAME by its own latest run — never a
      combined status rollup, which can carry stale or empty entries and
      undercount a green head. Runs are grouped by producer (app id, check
      suite id) and name. Per group: any run not completed is PENDING (a live
      rerun supersedes an older result); otherwise the run with the latest
      completion time decides: success / neutral / skipped is PASS,
      cancelled is PENDING (transient, never red), anything else is FAIL.
      When several producers emit one name (two workflows or apps both
      reporting `test`) and their latest verdicts disagree, the name is FAIL
      as ambiguous: a newer green from one producer never hides another's
      red. Re-run the failed producer's own run to resolve it.
      With --require, only those names count and a missing one is NO-RUN.
      Exit 1 on any FAIL; exit 2 on any PENDING / NO-RUN, no runs at all,
      a page count short of total_count, or a `gh` error; else PASS. Legacy
      commit statuses are not read: a check that reports only as a status
      shows as NO-RUN under --require (fail closed). When no check ran at all at
      S (any run at S, even an unrelated one, means checks ran) and S's commit message holds a CI-skip
      token (a bracketed `[skip ci]`-style token anywhere, or a final `skip-checks: true`
      trailer; case-sensitive), the verdict is FAIL naming it as the likely cause: push
      a new commit with a clean message; still no runs means path filters or no CI.

      --wait [--interval S] [--min-checks K]
          Poll the same per-name verdicts every S seconds (default 45) until
          every observed/required name is a terminal PASS, one is a terminal
          FAIL, or --timeout's total budget elapses (default 60s; in --wait
          mode --timeout is the WHOLE poll's wall-clock budget, not one gh
          call's — each individual gh read stays bounded to <=30s so a stuck
          call cannot itself eat the budget). --min-checks K (default 1)
          guards a false-green report: fewer than K names observed keeps
          polling rather than declaring ALL GREEN on zero dispatched checks.
          Prints exactly ONE line: `<gh-repo> @<sha> checks=<n> ALL GREEN` or
          `<gh-repo> @<sha> checks=<n> NOT-GREEN: <name, name, ...>`. Exit 0
          ALL GREEN; 1 a FAIL is terminal; 2 timed out still PENDING/NO-RUN or
          under --min-checks, or the sha/repo could not be checked at all.

  deps [--repo DIR] [--base origin/main] [--timeout 120]
      Local green is a proxy when the worktree has no node_modules of its
      own: Node walks UP the directory tree and quietly resolves a parent
      checkout's packages, so tsc, lint and tests can pass against a stale
      major while CI fails (a zod 3 -> 4 bump went green locally that way).
      When the diff from the merge-base with --base to the working tree
      (tracked changes plus untracked files) touches a package.json or a
      lockfile (package-lock.json, npm-shrinkwrap.json, yarn.lock,
      pnpm-lock.yaml, bun.lock, bun.lockb), FAIL unless a node_modules
      exists at or above each touched file INSIDE the worktree AND every
      entry whose spec that diff added or changed (dependencies,
      devDependencies, optionalDependencies, peerDependencies, and by name
      overrides, resolutions, pnpm.overrides) resolves, searching up from its
      package.json's directory, to a node_modules/<pkg>/package.json INSIDE
      the worktree (symlinks followed). A package name that is not a valid
      npm name FAILs. Versions are compared only for exact, ^, ~ and x-range
      specs (^4, ~4.1, 4.x, 4); a prerelease installed version satisfies only
      a spec naming a prerelease of the same x.y.z. Every other spec (a
      range such as >=1 or ||, *, a tag, npm:, workspace:, file:, git, a
      nested override) is counted and printed as "N unjudged (range/tag),
      version not compared": it is not a version proof. A package absent
      from node_modules is a FAIL for dependencies and devDependencies but
      unjudged for the optional, peer and override sections. A package.json
      whose JSON is not an object of string specs exits 2. A diff touching
      none of those files is a PASS that says it skipped. Yarn Plug'n'Play
      (no node_modules) always FAILs here: judge it by hand. The FAIL
      prints the install command to copy (`npm ci`; the frozen install for
      a yarn/pnpm/bun lockfile): this mode only reads, it never installs. A
      lockfile-only change compares no versions (no spec changed): it
      proves a node_modules exists inside the worktree, not that it matches
      the lock.

  attested --gh-repo OWNER/NAME --pr N --board-issue M --author ID
           [--board-repo OWNER/NAME] [--timeout 30]
      The reviewed-attestation gate for a ready-flip. Read PR N's CURRENT head
      (sha + branch) and the board issue M's comments (on --board-repo,
      default --gh-repo), keep only valid `REVIEW` posts (board_post.py
      --type REVIEW) whose refs name `#N` and whose sha and branch equal that
      exact head, and take each reviewer id's latest such post. PASS only when
      at least one reviewer other than --author (the lane that wrote the PR)
      says `verdict:approve` and none says `verdict:changes`. The author's own
      REVIEW never counts, and a comment edited after posting is not trusted.
      A push after the review moves the head, so the old attestation no longer
      matches: a new push always needs a new review. It never flips the PR
      itself: chain the flip as its own visible command,
          surface_check.py attested ... && gh pr ready N --repo OWNER/NAME
      so a FAIL stops the chain. This makes "reviewed" true and checkable; it
      does not bypass the host. The host's own permission decision on that
      `gh pr ready` (an auto-mode classifier, a hook, an allowlist) stays
      final, and a denial is surfaced to the owner, not retried through
      another path (a flip hidden inside this script would route around it,
      which is why there is none). The chain has a check-then-act gap
      (`gh pr ready` takes no sha), so a push landing between the two commands
      is not caught here: whatever merges next re-checks the head it merges.
      Reviewer ids are self-declared, so a REVIEW post's declared `agent:`
      id is cross-checked against the comment's real forge account
      (`user.login`) two ways: (1) a REVIEW whose login equals the PR's own
      `user.login` (when the PR read exposes one) counts as the author's,
      whatever id it declares; (2) a REVIEW whose login also posted this
      PR's own `agent:<author>` REVIEW under the matching head counts as
      the author's too. Either way it is dropped before approve/changes are
      tallied, and the reason is printed. `--author` is itself checked
      against the PR's `user.login` when the PR read exposes one: a
      mismatch refuses (COULD_NOT_CHECK) rather than gate a PR under the
      wrong claimed identity.
      REMAINING LIMIT: every lane still shares ONE forge account for board
      comments, so this proves a distinct DECLARED id was not caught
      contradicting itself or the PR's own login — not a distinct human or
      even a distinct process. It cannot catch two lanes on the SAME shared
      login approving each other's work under different declared ids; that
      needs separate bot identities per lane (recommended), at which point
      the `--author`/`user.login` check above becomes a real binding one.

      --draft-skip-ci
          Say so when CI is configured to skip drafts and run only on
          `ready_for_review`: this gate never required checks for the ready
          decision (it never has — it reads REVIEW posts, not check runs),
          and the flag makes the PASS/FAIL reason say that explicitly, so a
          draft PR sitting at zero check suites reads as the expected state
          under that CI config, not an anomaly needing an admin. Merging
          still requires green (`checks`/`--wait`) — this flag only concerns
          the *ready* decision, never the merge one.

  --json  print one JSON object (verdict, observed id, surface, reason, UTC
          observation time) for a board post or a handback `Verify:` line.

Leakage: a rejected build-id value is reported by type and length only, and
every printed URL (the surface, a redirect Location, a URL remote) drops its
userinfo, query, and fragment. A --url carrying userinfo is refused.

Exit codes: 0 PASS; 1 FAIL (the surface serves / the branch holds something
else); 2 COULD_NOT_CHECK (no build id, non-200, redirect, network or git
error, a timeout, a shallow clone, an ambiguous or too-short sha, or bad
usage). Exit 2 is never a pass: an unverifiable claim stays unverified.

Side effects: `served` performs HTTP GETs (proxy env vars are honoured);
`ref` runs `git fetch` against the named remote (and `git status` with
--require-clean); `checks` and `attested` run read-only `gh api` calls;
`deps` runs read-only git and reads package files.
Nothing else is written.
"""
import argparse
import contextlib
import datetime
import io
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402  (curl fallback for gh's macOS-sandbox TLS failure)
import board_common as bc  # noqa: E402  (sibling module: the one typed-post grammar)

PASS, FAIL, COULD_NOT_CHECK = 0, 1, 2
VERDICT = {PASS: "PASS", FAIL: "FAIL", COULD_NOT_CHECK: "COULD_NOT_CHECK"}
MIN_SHA = 7
MAX_BODY = 2 * 1024 * 1024
DEFAULT_GIT_TIMEOUT = 120.0  # seconds per git call in `ref` mode
HEX_RE = re.compile(r"^[0-9a-f]+$")
PROVES = "the surface serves this build; not that the feature works"
PROVES_REF = "the remote branch contains this commit; not that it is deployed or works"
PROVES_CHECKS = "each named check's latest run at this sha; not that the checks cover the change"
PROVES_DEPS = "changed dependency specs resolve inside this worktree, versions compared only for exact, ^, ~ and x-range specs (others unjudged); not that node_modules matches the lockfile or that tests ran"
PROVES_ATTESTED = "a non-author reviewer lane approved this exact head; not that the review was thorough"
CHECK_PASS = ("success", "neutral", "skipped")
REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
# Tokens GitHub honors in a head commit message (docs: skipping-workflow-runs, verified 2026-10-29). The docs list them lowercase and
# do not say whether matching ignores case, so this is case-sensitive. A bracketed token counts anywhere (a bare mention too); a
# `skip-checks: true` trailer counts only as the message's last line, after two empty lines (the docs' trailer rule).
SKIP_TOKEN_RE = re.compile(r"(\[(?:skip ci|ci skip|no ci|skip actions|actions skip)\])|\n\n\n(?:[^\n]+\n)*(skip-checks: ?true)\s*\Z")
NO_CHECKS = "no check ran at this sha"  # NO-RUN detail when the sha has no runs at all (an unrelated run existing changes it)
# Tests swap this for {} so a local fixture never routes through a proxy.
_PROXIES = None


class CheckError(Exception):
    """A condition that makes the claim uncheckable (always exit 2)."""


def _sha(value, what):
    """Normalise a claimed sha: hex only, at least MIN_SHA chars, else refuse."""
    s = (value or "").strip().lower()
    if not HEX_RE.match(s):
        raise CheckError(f"{what} {value!r} is not a hex commit sha")
    if len(s) < MIN_SHA:
        raise CheckError(f"{what} {value!r} is shorter than {MIN_SHA} chars; too ambiguous to compare")
    return s


def _matches(expected, observed):
    """True iff the shorter sha (both already >= MIN_SHA) prefixes the longer."""
    n = min(len(expected), len(observed))
    return expected[:n] == observed[:n]


# --------------------------------------------------------------------------
# served
# --------------------------------------------------------------------------
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # urllib then raises HTTPError with the 3xx code


class _MetaParser(HTMLParser):
    def __init__(self, name):
        super().__init__()
        self.name = name.lower()
        self.found = None

    def handle_starttag(self, tag, attrs):
        if tag != "meta" or self.found is not None:
            return
        a = {k.lower(): (v or "") for k, v in attrs}
        if (a.get("name") or a.get("property") or "").lower() == self.name:
            self.found = a.get("content", "")


def redact_url(url):
    """Return `url` safe to print: userinfo, query, and fragment dropped, control chars removed.

    A surface URL or a peer's redirect target can carry a password or a token
    (`https://user:pw@host/p?token=...`); only scheme, host, port, and path are
    kept. Non-URL text is returned with control characters stripped. Pure.
    """
    text = "".join(ch for ch in str(url) if ch.isprintable())[:300]
    try:
        parts = urllib.parse.urlsplit(text)
        host = parts.hostname or ""
        port = f":{parts.port}" if parts.port else ""
    except ValueError:
        return "<unparseable URL>"
    if not parts.scheme or not parts.netloc:
        return text.split("?", 1)[0].split("#", 1)[0]
    if ":" in host:  # IPv6 literal
        host = f"[{host}]"
    return urllib.parse.urlunsplit((parts.scheme, host + port, parts.path, "", ""))


def _describe(raw):
    """Type and length of a value that is not a build id — never the value (it may be a secret). Pure."""
    return f"{type(raw).__name__} of length {len(str(raw))}"


def _fetch(url, timeout):
    """GET url without following redirects; return (headers, body text).

    `timeout` bounds each socket operation AND the whole body read (wall-clock),
    so a server that trickles bytes cannot hold the check open.
    """
    handlers = [_NoRedirect()]
    if _PROXIES is not None:
        handlers.append(urllib.request.ProxyHandler(_PROXIES))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, headers={"User-Agent": "surface_check/1"})
    shown = redact_url(url)
    try:
        with opener.open(req, timeout=timeout) as resp:
            status = resp.status
            headers = resp.headers
            deadline = time.monotonic() + timeout
            chunks, size = [], 0
            while size < MAX_BODY:
                if time.monotonic() > deadline:
                    raise CheckError(f"{shown} body not read within the {timeout:g}s wall-clock cap")
                chunk = resp.read1(min(65536, MAX_BODY - size))
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
            body = b"".join(chunks).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if 300 <= exc.code < 400:
            loc = redact_url(exc.headers.get("Location", "?"))
            raise CheckError(f"{shown} redirected ({exc.code}) to {loc}; not followed — "
                             "re-run with that URL if it is the surface the reviewer opens")
        raise CheckError(f"{shown} returned HTTP {exc.code}, not 200")
    except (urllib.error.URLError, OSError, ValueError) as exc:
        detail = exc.reason if isinstance(exc, urllib.error.URLError) else exc
        raise CheckError(f"{shown} could not be fetched: {str(detail).replace(url, shown)[:200]}")
    if status != 200:
        raise CheckError(f"{shown} returned HTTP {status}, not 200")
    return headers, body


def _parse_probe(spec):
    kind, sep, rest = spec.partition(":")
    if not sep or not rest or kind not in ("header", "meta", "path"):
        raise CheckError(f"bad --probe {spec!r} (want header:NAME, meta:NAME, or path:/p.json:key)")
    if kind == "path":
        path, sep, key = rest.rpartition(":")
        if not sep or not path.startswith("/") or path.startswith("//") or not key:
            raise CheckError(f"bad --probe {spec!r} (path form is path:/same-origin/path:dotted.key)")
        return kind, (path, key)
    return kind, rest


def _json_key(doc, key):
    cur = doc
    for part in key.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def _as_build_id(raw):
    """Return (sha, None) for a usable build id, else (None, why-not).

    A rejected value is described by type and length only, never echoed: a
    header or JSON key named like a build id can hold a token or a secret.
    """
    if raw is None or raw == "":
        return None, "absent"
    if not isinstance(raw, str):
        return None, f"{_describe(raw)} is not a commit sha (a timestamp/number is not a build id)"
    v = raw.strip().lower()
    if not HEX_RE.match(v):
        return None, f"{_describe(raw)} is not a commit sha (a data timestamp or version is not a build id)"
    if len(v) < MIN_SHA:
        return None, f"{_describe(raw)} is shorter than {MIN_SHA} hex chars; too ambiguous"
    return v, None


def check_served(url, expect, probes, timeout):
    """Return (code, observed, reason) for the served-build check."""
    expected = _sha(expect, "--expect-sha")
    try:
        parts = urllib.parse.urlsplit(url)
        userinfo = parts.username is not None or parts.password is not None
    except ValueError:
        raise CheckError("--url is not a parseable URL")
    scheme = parts.scheme.lower()
    if scheme not in ("http", "https"):
        raise CheckError(f"--url scheme {scheme or '(none)'!r} unsupported; want http or https")
    if userinfo:
        # urllib would resolve "user:pw@host" as a hostname, leaking it to DNS.
        raise CheckError("--url carries userinfo credentials, which are not sent and would leak "
                         "(argv is visible to local users); give the bare URL")
    if not probes:
        raise CheckError("at least one --probe is required; the build id must come from a named signal")
    parsed = [(spec, *_parse_probe(spec)) for spec in probes]
    page = None
    if any(kind in ("header", "meta") for _, kind, _ in parsed):
        page = _fetch(url, timeout)
    found, missing = [], []
    for spec, kind, arg in parsed:
        if kind == "header":
            raw = page[0].get(arg)
        elif kind == "meta":
            mp = _MetaParser(arg)
            mp.feed(page[1])
            raw = mp.found
        else:
            path, key = arg
            _, body = _fetch(urllib.parse.urljoin(url, path), timeout)
            try:
                raw = _json_key(json.loads(body), key)
            except ValueError:
                raise CheckError(f"{path} is not JSON")
        sha, why = _as_build_id(raw)
        if sha is None:
            missing.append(f"{spec}: {why}")
        else:
            found.append((spec, sha))
    if not found:
        return COULD_NOT_CHECK, None, "no build id reported (" + "; ".join(missing) + ")"
    bad = [(s, v) for s, v in found if not _matches(expected, v)]
    observed = found[0][1]
    if bad:
        detail = ", ".join(f"{s}={v}" for s, v in bad)
        return FAIL, bad[0][1], f"surface serves {detail}, not {expected} (stale or wrong build)"
    via = ", ".join(s for s, _ in found)
    note = f"; unreported: {'; '.join(missing)}" if missing else ""
    return PASS, observed, f"served build {observed} matches {expected} via {via}{note}"


# --------------------------------------------------------------------------
# ref
# --------------------------------------------------------------------------
def _git(repo, *args, timeout=DEFAULT_GIT_TIMEOUT):
    """Run one git command non-interactively; a hang past `timeout` s raises CheckError.

    GIT_TERMINAL_PROMPT=0, a closed stdin, and a new session (no controlling
    terminal) stop git and its ssh child from waiting on a credential prompt;
    on timeout the whole process group is killed so a grandchild holding the
    pipes cannot keep the check open.
    """
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    try:
        proc = subprocess.Popen(["git", "-C", repo, *args], stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env, start_new_session=True)
    except OSError as exc:
        raise CheckError(f"git could not be started: {exc}")
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(OSError):
            if hasattr(os, "killpg"):
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        proc.communicate()
        raise CheckError(f"git {args[0]} timed out after {timeout:g}s (a hung remote or credential prompt)")
    return subprocess.CompletedProcess(proc.args, proc.returncode, out, err)


def check_ref(repo, remote, branch, expect, timeout=DEFAULT_GIT_TIMEOUT, require_clean=False):
    """Return (code, observed-remote-head, reason) for the reachability check.

    With `require_clean`, any uncommitted tracked change or untracked,
    non-ignored file in `repo` is a FAIL before anything is fetched. Every git call is bounded by `timeout`
    seconds; a timeout raises CheckError (exit 2).
    """
    git = lambda *a: _git(repo, *a, timeout=timeout)  # noqa: E731  (one bound runner for this check)
    expected = _sha(expect, "--expect-sha")
    if require_clean:
        # --untracked-files=normal: a new file the lane never added is as
        # uncommitted as a staged edit; ignored files stay out (.gitignore).
        st = git("status", "--porcelain=v1", "--untracked-files=normal")
        if st.returncode != 0:
            raise CheckError(f"git status failed in {repo}: {st.stderr.strip()[:300]}")
        dirty = [ln for ln in st.stdout.splitlines() if ln.strip()]
        new = sum(1 for ln in dirty if ln.startswith("??"))
        if dirty:
            return FAIL, None, (f"{len(dirty) - new} tracked path(s) changed and {new} untracked path(s) in {repo}, "
                                "not committed (staged or not): a hook-rejected commit leaves the edit uncommitted; "
                                "edit done is not committed is not pushed")
    shown = redact_url(remote)  # a URL remote can carry credentials
    if remote.startswith("-") or not remote:
        raise CheckError(f"bad --remote {shown!r}")
    if branch.startswith("-") or git("check-ref-format", "--branch", branch).returncode != 0:
        raise CheckError(f"bad --branch {branch!r}")
    if git("rev-parse", "--is-shallow-repository").stdout.strip() == "true":
        raise CheckError("shallow clone: ancestry is incomplete, reachability cannot be decided")
    tracking = f"refs/remotes/{remote}/{branch}"
    fetch = git("fetch", "--quiet", "--no-tags", remote, f"+refs/heads/{branch}:{tracking}")
    if fetch.returncode != 0:
        raise CheckError(f"git fetch {shown} {branch} failed: {fetch.stderr.replace(remote, shown).strip()[:300]}")
    head = git("rev-parse", "--verify", "--quiet", tracking + "^{commit}").stdout.strip()
    if not head:
        raise CheckError(f"{tracking} did not resolve after fetch")
    res = git("rev-parse", "--verify", "--quiet", expected + "^{commit}")
    if res.returncode != 0:
        # After a full fetch every ancestor of the remote head is local, so an
        # unknown object is not on the branch; an ambiguous prefix is refused.
        amb = git("rev-parse", "--disambiguate=" + expected).stdout.split()
        if len(amb) > 1:
            raise CheckError(f"--expect-sha {expected} is ambiguous in {repo}; give more chars")
        return FAIL, head, f"{expected} is not in {repo} after fetching {shown}/{branch} (head {head[:12]})"
    full = res.stdout.strip()
    anc = git("merge-base", "--is-ancestor", full, head)
    if anc.returncode == 0:
        return PASS, head, f"{full[:12]} is reachable from {shown}/{branch} (head {head[:12]})"
    if anc.returncode == 1:
        return FAIL, head, f"{full[:12]} is NOT reachable from {shown}/{branch} (head {head[:12]})"
    raise CheckError(f"git merge-base failed: {anc.stderr.strip()[:300]}")


# --------------------------------------------------------------------------
# checks
# --------------------------------------------------------------------------
DEP_FILES = ("package.json", "package-lock.json", "npm-shrinkwrap.json", "yarn.lock", "pnpm-lock.yaml", "bun.lock", "bun.lockb")
DEP_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
OVERRIDES = ("overrides", "resolutions", "pnpm.overrides")
SOFT = ("optionalDependencies", "peerDependencies", *OVERRIDES)  # may legitimately be absent from node_modules: reported unjudged, never FAIL
INSTALL = (("pnpm-lock.yaml", "pnpm install --frozen-lockfile"), ("yarn.lock", "yarn install --frozen-lockfile"),
           ("bun.lock", "bun install --frozen-lockfile"), ("bun.lockb", "bun install --frozen-lockfile"))
NAME_RE = re.compile(r"(?:@[A-Za-z0-9~-][A-Za-z0-9._~-]*/)?[A-Za-z0-9~-][A-Za-z0-9._~-]*")  # npm name: no "..", no leading "/" or "."
SPEC_RE = re.compile(r"([\^~]?)v?(\d+)(?:\.(\d+|[xX*])(?:\.(\d+|[xX*]))?)?(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")
VER_RE = re.compile(r"v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?(?:\+[0-9A-Za-z.-]+)?")


def _pre(ids):
    """Sort key for a semver prerelease: numeric ids compare as numbers and sort before alphanumeric ones; a prefix sorts first."""
    return [(0, int(i), "") if i.isdigit() else (1, 0, i) for i in ids.split(".")]


def _satisfies(ver, spec):
    """True/False for an exact, ^, ~ or x-range (4, 4.x, 4.1) spec; None when the spec is a range, tag or url this does not judge.

    A prerelease version satisfies only a spec naming a prerelease of the same x.y.z (npm's rule), so 4.0.0-rc.1 never satisfies ^4.0.0.
    """
    m, v = SPEC_RE.fullmatch(spec.strip()), VER_RE.fullmatch(ver.strip())
    if not m or not v:
        return None
    op, *nums, pre = m.groups()
    want = []
    for x in nums:
        if x is None or x in "xX*":
            break
        want.append(int(x))
    if any(x not in (None, "x", "X", "*") for x in nums[len(want):]) or (pre and len(want) < 3):
        return None
    have, hpre = tuple(map(int, v.groups()[:3])), v.group(4)
    if not op and len(want) == 3:
        return have == tuple(want) and hpre == pre
    n = {"^": next((i + 1 for i, x in enumerate(want) if x), len(want)), "~": min(2, len(want)), "": len(want)}[op]
    full = tuple(want + [0] * (3 - len(want)))
    if hpre:
        return bool(pre) and have == full and _pre(hpre) >= _pre(pre)
    return have[:n] == full[:n] and have >= full


def _specs(doc, p):
    """{(section, key): value} for every dependency-like entry of one parsed package.json; a wrong JSON shape raises CheckError."""
    if not isinstance(doc, dict):
        raise CheckError(f"{p} is not a JSON object")
    pnpm = doc.get("pnpm")
    if pnpm is not None and not isinstance(pnpm, dict):
        raise CheckError(f"{p} pnpm is not an object")
    out = {}
    for sec in (*DEP_SECTIONS, *OVERRIDES):
        d = (pnpm or {}).get("overrides") if sec == "pnpm.overrides" else doc.get(sec)
        if d is not None and not isinstance(d, dict):
            raise CheckError(f"{p} {sec} is not an object")
        out.update({(sec, k): v for k, v in (d or {}).items()})
    return out


def check_deps(repo, base, timeout=DEFAULT_GIT_TIMEOUT):
    """Judge that a lane diff touching dependency files has its deps installed INSIDE the worktree (see `deps` in the module docstring)."""
    def git(*a):
        r = _git(repo, *a, timeout=timeout)
        if r.returncode:
            raise CheckError(f"git {a[0]} failed: {r.stderr.strip()[:200]}")
        return r.stdout
    root = Path(git("rev-parse", "--show-toplevel").strip()).resolve()
    repo = str(root)  # untracked listing and diff paths are then root-relative whatever --repo was
    mb = git("merge-base", base, "HEAD").strip()
    names = git("diff", "-z", "--name-only", "--no-relative", mb).split("\0") + git("ls-files", "-z", "-o", "--exclude-standard").split("\0")
    touched = sorted({p for p in names if os.path.basename(p) in DEP_FILES})
    if not touched:
        return PASS, None, f"skip: diff against {base} touches no package.json or lockfile"
    fix = next((c for f, c in INSTALL if (root / f).exists()), "npm ci")
    todo = f"copy-paste: cd {shlex.quote(str(root))} && {fix}"

    def chain(p):  # the file's directory up to and including the worktree root
        out = [(root / p).parent]
        while out[-1] != root:
            out.append(out[-1].parent)
        return out
    missing = [p for p in touched if (root / p).is_file() and not any((d / "node_modules").is_dir() for d in chain(p))]
    if missing:
        return FAIL, None, f"{', '.join(missing)} changed but the worktree has no node_modules of its own at or above it, so Node resolves a parent checkout's packages; {todo}"
    bad, ok, unj, n = [], 0, 0, 0
    for p in touched:
        if os.path.basename(p) != "package.json" or not (root / p).is_file():
            continue
        try:
            new = _specs(json.loads((root / p).read_text()), p)
        except (OSError, ValueError) as exc:
            raise CheckError(f"{p} unreadable: {exc}")
        old = _git(repo, "show", f"{mb}:{p}", timeout=timeout)
        try:
            old = _specs(json.loads(old.stdout), p) if old.returncode == 0 else {}
        except (ValueError, CheckError):
            old = {}
        for (sec, key), spec in new.items():
            if old.get((sec, key)) == spec:
                continue
            n += 1
            if isinstance(spec, dict) and sec in OVERRIDES:  # nested override: not compared
                unj += 1
                continue
            if not isinstance(spec, str):
                raise CheckError(f"{p} {sec}.{key} is not a string spec")
            pkg = re.sub(r"(?<=.)@[^/]*$", "", key) if sec in OVERRIDES else key  # "name@range" override keys: by name
            if not NAME_RE.fullmatch(pkg):
                if sec in OVERRIDES:  # a path-like key names no single package
                    unj += 1
                else:
                    bad.append(f"{p} {sec} name {key!r} is not a valid npm package name")
                continue
            d = (root / p).parent
            f = next((q for q in (x / "node_modules" / pkg / "package.json" for x in (d, *d.parents)) if q.is_file()), None)
            try:
                ver = json.loads(f.read_text())["version"] if f else None
            except (OSError, ValueError, KeyError, TypeError):
                ver = None
            if not isinstance(ver, str):
                ver = None
            if f is None or ver is None:
                if sec in SOFT:
                    unj += 1
                else:
                    bad.append(f"{pkg} {spec} not installed (or unreadable) from {p}")
            elif root not in f.resolve().parents:
                bad.append(f"{pkg} {spec} resolves OUTSIDE the worktree at {f} ({ver})")
            elif (s := _satisfies(ver, spec)) is False:
                bad.append(f"{pkg} wants {spec}, installed {ver}")
            elif s is None:
                unj += 1
            else:
                ok += 1
    if bad:
        return FAIL, None, "; ".join(bad) + f"; {todo}"
    if not n:
        return PASS, None, f"{', '.join(touched)} changed, worktree has its own node_modules; no dependency spec changed, so no version was compared (a lockfile-only bump is unverified; {todo})"
    tail = f"; {unj} unjudged (range/tag), version not compared" if unj else ""
    return PASS, None, f"{ok} changed spec(s) resolve inside the worktree at a version satisfying the spec{tail}"


def _gh_default(args, timeout):
    """Run one `gh` call without a shell; return (rc, stdout, stderr). A hang past `timeout` s is rc 124."""
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:g}s"
    return gh_rest.fallback(args, proc.returncode, proc.stdout, proc.stderr, timeout)


_gh = _gh_default  # the selftest swaps in a fake forge
_sleep = time.sleep  # the selftest swaps in a no-op / counting fake
_monotonic = time.monotonic  # the selftest swaps in a fake stepped clock


def _decode_objects(text):
    """Decode `gh api --paginate` output for an object endpoint: pages printed back to back."""
    decoder, pos, out = json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return out
        try:
            page, pos = decoder.raw_decode(text, pos)
        except ValueError as exc:
            raise CheckError(f"gh output is not JSON: {exc}")
        if not isinstance(page, dict) or not isinstance(page.get("check_runs"), list):
            raise CheckError("gh output held a page without a check_runs list")
        out.append(page)


def _producer(run):
    """The (app id, check suite id) that produced a check run; None where the forge omitted one. Pure.

    A rerun inside one workflow run stays in the same check suite, so it
    still supersedes its older attempt; a second workflow or app emitting the
    same name is a separate producer.
    """
    app, suite = run.get("app"), run.get("check_suite")
    return (app.get("id") if isinstance(app, dict) else None, suite.get("id") if isinstance(suite, dict) else None)


def _latest_verdict(runs):
    """(state, detail) for one producer's runs of one name: live is PENDING, else its latest completion decides. Pure."""
    live = [r for r in runs if r.get("status") != "completed"]
    if live:
        return "PENDING", str(live[0].get("status"))
    last = max(runs, key=lambda r: (str(r.get("completed_at") or ""), r.get("id") or 0))
    concl = str(last.get("conclusion"))
    return ("PASS" if concl in CHECK_PASS else "PENDING" if concl == "cancelled" else "FAIL"), concl


def _check_states(slug, expected, required, timeout):
    """Return {name: (state, detail)} — state in PASS/FAIL/PENDING/NO-RUN — for one gh read. `expected` is pre-normalised.

    Raises CheckError when the read itself is uncheckable (bad slug, gh
    failure, truncated pages) or when there are no runs at all and no
    --require list was given (nothing to report). An empty {} is never
    returned silently in that case — the caller sees the CheckError.
    """
    if not REPO_SLUG_RE.match(slug or ""):
        raise CheckError(f"--gh-repo {slug!r} is not OWNER/NAME")
    rc, out, err = _gh(["gh", "api", "--paginate",
                        f"repos/{slug}/commits/{expected}/check-runs?filter=latest&per_page=100"], timeout)
    if rc != 0:
        raise CheckError(f"gh api failed (rc {rc}): {err.strip()[:300]}")
    pages = _decode_objects(out)
    runs = {r.get("id"): r for pg in pages for r in pg["check_runs"] if isinstance(r, dict)}
    total = pages[0].get("total_count") if pages else 0
    if not isinstance(total, int) or len(runs) < total:
        raise CheckError(f"read {len(runs)} check-runs, forge reports {total}: truncated, refusing to judge")
    by_name = {}
    for r in runs.values():
        head = str(r.get("head_sha") or "").lower()
        if HEX_RE.match(head) and len(head) >= MIN_SHA and _matches(expected, head) and r.get("name"):
            by_name.setdefault(str(r["name"]), []).append(r)
    if not by_name and not required:
        raise CheckError(f"no check-runs for {expected}: not passed, not failed; dispatch a run")
    states = {}
    for name in (required or sorted(by_name)):
        group = by_name.get(name)
        if not group:
            states[name] = ("NO-RUN", "no run" if by_name else NO_CHECKS)
            continue
        producers = {}
        for r in group:
            producers.setdefault(_producer(r), []).append(r)
        verdicts = {key: _latest_verdict(runs) for key, runs in sorted(producers.items(), key=lambda kv: str(kv[0]))}
        if len({st for st, _ in verdicts.values()}) == 1:
            states[name] = next(iter(verdicts.values()))
        else:
            # Several producers emit this name and their latest runs disagree:
            # no run is authoritative, so never let the newest one win.
            seen = ", ".join(f"app {a} suite {s}: {concl}" for (a, s), (_, concl) in verdicts.items())
            states[name] = ("FAIL", f"ambiguous: {len(verdicts)} latest runs disagree ({seen})")
    return states


def _skip_token(slug, sha, timeout):
    """The CI-skip token in the forge's commit message for `sha`, else None. A failed or odd read is None, never a guess."""
    rc, out, _ = _gh(["gh", "api", f"repos/{slug}/commits/{sha}"], timeout)
    try:
        m = SKIP_TOKEN_RE.search(json.loads(out)["commit"]["message"]) if rc == 0 else None
    except (ValueError, KeyError, TypeError):
        return None
    return (m.group(1) or m.group(2)) if m else None


def _skipped(tok):
    return (f"no check ran and the head commit message holds {tok!r}, the likely cause: GitHub skips every push and pull_request "
            "workflow for such a head, so waiting cannot help. Not certain: a ref with no CI, or workflow path filters, also leave "
            "zero runs. Push a new commit with a clean message (never quote the token in it) and re-check; if there are still zero "
            "runs, check the workflow triggers and path filters")


def check_checks(slug, sha, required, timeout):
    """Return (code, summary, reason) for the per-name latest check-run verdict (see `checks`).

    No check ran at all (no check-runs at the sha, with or without --require) and the head commit message holds a CI-skip token:
    FAIL naming it as the likely cause. Any run at the sha keeps the plain verdict, an unrelated one included (a required name with
    no run is then NO-RUN, not FAIL); an unreadable message adds nothing.
    """
    expected = _sha(sha, "--sha")
    try:
        states = _check_states(slug, expected, required, timeout)
    except CheckError as exc:
        tok = _skip_token(slug, expected, timeout) if str(exc).startswith("no check-runs") else None
        return (FAIL, None, _skipped(tok)) if tok else (COULD_NOT_CHECK, None, str(exc))
    tally = {k: sorted(n for n, (st, _) in states.items() if st == k) for k in ("PASS", "FAIL", "PENDING", "NO-RUN")}
    summary = ", ".join(f"{len(v)} {k}" for k, v in tally.items())
    detail = "; ".join(f"{k}: " + ", ".join(f"{n} ({states[n][1]})" if k != "NO-RUN" else n for n in v)
                       for k, v in tally.items() if v and k != "PASS")
    if tally["FAIL"]:
        return FAIL, summary, f"{summary} — {detail}"
    if tally["PENDING"] or tally["NO-RUN"]:
        tok = _skip_token(slug, expected, timeout) if all(d == NO_CHECKS for _, d in states.values()) else None
        if tok:
            return FAIL, summary, f"{summary} — {_skipped(tok)}"
        return COULD_NOT_CHECK, summary, f"{summary} — {detail}: wait or re-dispatch, then re-check"
    return PASS, summary, f"{summary} at {expected[:12]} (latest run per check name)"


MIN_WAIT_INTERVAL = 5.0


def wait_for_checks(slug, sha, required, interval, timeout, min_checks):
    """Poll `_check_states` every `interval`s until terminal or `timeout`s elapse. Return (code, label, reason).

    ALL GREEN only when every observed/required name is PASS AND at least
    `min_checks` names were observed (a green report before any check has
    even been dispatched proves nothing — this guards it). A terminal FAIL
    returns immediately (a completed red does not get greener with more
    waiting); PENDING/NO-RUN/too-few-observed keep polling until `timeout`.
    `label` is the single line the CLI prints; never blocks past `timeout`.
    """
    expected = _sha(sha, "--sha")
    interval = max(MIN_WAIT_INTERVAL, interval)  # a 0s interval would hammer the API until the deadline
    deadline = _monotonic() + max(0.0, timeout)
    last_n, last_desc = 0, f"no checks observed (fewer than --min-checks {min_checks})"
    while True:
        try:
            remaining = deadline - _monotonic()
            # each gh call is bounded by what is left of the budget, so the poll never overruns --timeout by a call
            states = _check_states(slug, expected, required, max(1.0, min(30.0, remaining)))
            names = sorted(states)
            failed = [n for n in names if states[n][0] == "FAIL"]
            not_green = [n for n in names if states[n][0] != "PASS"]
            if failed:
                return (FAIL, f"{slug} @{expected[:12]} checks={len(names)} NOT-GREEN: {', '.join(failed)}",
                        "at least one check is a terminal FAIL")
            if not not_green and len(names) >= min_checks:
                return (PASS, f"{slug} @{expected[:12]} checks={len(names)} ALL GREEN",
                        "all named checks are a terminal PASS")
            last_n = len(names)
            last_desc = ", ".join(not_green) if not_green else f"fewer than --min-checks {min_checks} observed"
        except CheckError as exc:
            last_n, last_desc = 0, f"uncheckable: {exc}"
        if _monotonic() >= deadline:
            return (COULD_NOT_CHECK, f"{slug} @{expected[:12]} checks={last_n} NOT-GREEN: {last_desc}",
                    f"timed out after {timeout:g}s waiting for green")
        _sleep(max(0.0, min(interval, deadline - _monotonic())))


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------
# --------------------------------------------------------------------------
# attested
# --------------------------------------------------------------------------
def _gh_out(args, timeout):
    """Run one `gh` call through `_gh`; return stdout or raise CheckError naming the failure."""
    rc, out, err = _gh(args, timeout)
    if rc != 0:
        raise CheckError(f"{' '.join(args[:3])} failed (rc {rc}): {err.strip()[:300]}")
    return out


def _pr_head(slug, pr, timeout):
    """Return (head sha, head branch, is draft, author login or None) for PR `pr`.

    `author login` is `doc["user"]["login"]` when the forge response carries one, else None — callers
    treat None as "not available" and skip login-bound checks rather than guess. Raises CheckError when
    the read itself is unreadable or the head sha is malformed.
    """
    try:
        doc = json.loads(_gh_out(["gh", "api", f"repos/{slug}/pulls/{pr}"], timeout))
        sha, ref = doc["head"]["sha"], doc["head"]["ref"]
    except (ValueError, KeyError, TypeError) as exc:
        raise CheckError(f"PR #{pr} read returned an unexpected shape: {exc}") from exc
    if not (isinstance(sha, str) and len(sha) == 40 and HEX_RE.match(sha)):
        raise CheckError(f"PR #{pr} head sha is not a 40-char hex sha")
    user = doc.get("user")
    login = user.get("login") if isinstance(user, dict) else None
    return sha, ref, bool(doc.get("draft")), (login if isinstance(login, str) and login else None)


def check_attested(slug, pr, issue, author, board_repo=None, timeout=30.0, draft_skip_ci=False):
    """Gate a ready-flip on a REVIEW attestation for PR `pr`'s exact current head (see module docstring).

    Returns (code, head sha, reason). Raises CheckError (exit 2) on bad input or an unreadable forge.
    Side-effects: read-only `gh api` calls only; it never flips the PR (the caller chains `gh pr ready`).
    `draft_skip_ci` never changes the verdict (this gate never reads check runs) — on the draft/
    ready-flip branch only, it appends a sentence to the reason saying checks were not required for
    this decision, so a caller/orchestrator reading a draft PR with zero check suites treats that as
    the expected state under draft-skip CI, not an anomaly. Omitted on an already-ready (non-draft)
    PR: it already ran checks, so there is nothing for the note to explain there.
    """
    board_repo = board_repo or slug
    for repo in (slug, board_repo):
        if not REPO_SLUG_RE.match(repo or ""):
            raise CheckError(f"repo {repo!r} is not OWNER/NAME")
    if pr < 1 or issue < 1:
        raise CheckError("--pr and --board-issue must be positive numbers")
    if not bc.validate_agent(author):
        raise CheckError("--author must be the authoring lane's board id ([A-Za-z0-9][A-Za-z0-9._-]{0,63})")
    sha, ref, draft, pr_login = _pr_head(slug, pr, timeout)
    if pr_login is not None and pr_login != author:
        raise CheckError(f"--author {author!r} does not match PR #{pr}'s actual login {pr_login!r}; "
                         f"pass the id that actually opened this PR, not a different lane's")
    try:
        comments = bc.decode_pages(_gh_out(["gh", "api", "--paginate", bc.comments_path(board_repo, issue)], timeout))
    except bc.ForgeError as exc:
        raise CheckError(f"board read returned an unexpected shape: {exc}") from exc
    latest, edited, own, author_logins = {}, 0, False, set()
    for c in sorted(comments, key=lambda c: c.get("id", 0)):
        post = bc.parse_header(bc.first_line(c.get("body") or ""))
        if not post or post["errors"] or post["type"] != "REVIEW":
            continue
        f = post["fields"]
        if f["sha"] != sha or f["branch"] != ref or f"#{pr}" not in post["refs"].split(","):
            continue
        if c.get("updated_at") != c.get("created_at"):
            edited += 1
            continue
        user = c.get("user")
        login = user.get("login") if isinstance(user, dict) else None
        if post["agent"] == author:
            own = True
            if login:
                author_logins.add(login)
            continue
        latest[post["agent"]] = dict(f, _login=login)
    # A declared reviewer id is not trusted when its comment's real login is the PR's own login, or is a
    # login that also posted this PR's author REVIEW under a different id: either way the same forge
    # account is claiming two identities, which is exactly the self-declared-id gap this binds shut (see
    # module docstring REMAINING LIMIT: it still cannot separate two lanes sharing ONE forge account).
    spoofed = {}
    for a, f in latest.items():
        login = f["_login"]
        if login and pr_login is not None and login == pr_login:
            spoofed[a] = f"its login matches PR #{pr}'s own author account despite declaring agent:{a}"
        elif login and login in author_logins:
            spoofed[a] = f"its login also posted this PR's author:{author} REVIEW under a different declared id"
    latest = {a: f for a, f in latest.items() if a not in spoofed}
    changes = sorted(a for a, f in latest.items() if f["verdict"] == "changes")
    approved = sorted(a for a, f in latest.items() if f["verdict"] == "approve")
    if changes:
        return FAIL, sha, f"{', '.join(changes)} requested changes at {sha[:12]}; fix, push, and re-review"
    if not approved:
        notes = (["the author's own REVIEW does not count"] if own else []) + (
            [f"{edited} matching REVIEW(s) edited after posting (not trusted)"] if edited else []) + (
            [f"{a} not attested ({reason})" for a, reason in sorted(spoofed.items())])
        return FAIL, sha, (f"no REVIEW verdict:approve from a reviewer other than {author} for #{pr} at the exact "
                           f"head {sha[:12]} ({ref}); a push after a review needs a new one"
                           + (f"; {'; '.join(notes)}" if notes else ""))
    resolved = ", ".join(f"{a} resolved={latest[a]['resolved']}" for a in approved)
    spoof_note = ("; ignored not-attested REVIEW(s): " + "; ".join(
        f"{a} ({reason})" for a, reason in sorted(spoofed.items()))) if spoofed else ""
    if not draft:
        return PASS, sha, f"#{pr} head {sha[:12]} approved by {resolved}; already ready{spoof_note}"
    # ci_note only applies to the draft/ready-flip branch: an already-ready (non-draft) PR already
    # ran checks under draft-skip CI, so there is nothing for --draft-skip-ci to explain there.
    ci_note = ("; --draft-skip-ci: checks are not required for this decision — a draft PR with zero "
               "check suites is expected under draft-skip CI, not an anomaly" if draft_skip_ci else "")
    return PASS, sha, (f"#{pr} head {sha[:12]} approved by {resolved}; next, as its own command: "
                       f"gh pr ready {pr} --repo {slug} (the host's permission decision applies)"
                       f"{spoof_note}{ci_note}")


def _parser():
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true", default=argparse.SUPPRESS,
                        help="print one JSON object instead of text")
    p = argparse.ArgumentParser(prog="surface_check.py", parents=[common],
                                description="Verify a done/deployed claim on the authoritative surface.")
    p.add_argument("--selftest", action="store_true", help="run offline self-tests")
    sub = p.add_subparsers(dest="mode")
    s = sub.add_parser("served", parents=[common], help="check the build id a running app serves")
    s.add_argument("--url", required=True)
    s.add_argument("--expect-sha", required=True)
    s.add_argument("--probe", action="append", default=[],
                   help="header:NAME | meta:NAME | path:/version.json:key (repeatable)")
    s.add_argument("--timeout", type=float, default=10.0)
    r = sub.add_parser("ref", parents=[common], help="check a sha is reachable from a remote branch")
    r.add_argument("--repo", default=".")
    r.add_argument("--remote", default="origin")
    r.add_argument("--branch", required=True)
    r.add_argument("--expect-sha", required=True)
    r.add_argument("--timeout", type=float, default=DEFAULT_GIT_TIMEOUT, help="seconds per git call")
    r.add_argument("--require-clean", action="store_true",
                   help="also FAIL when --repo has an uncommitted change or untracked file (a hook-rejected commit)")
    c = sub.add_parser("checks", parents=[common], help="judge each check name by its latest run at a sha")
    c.add_argument("--gh-repo", required=True, help="OWNER/NAME on the forge")
    c.add_argument("--sha", required=True)
    c.add_argument("--require", action="append", default=[], help="a check name that must PASS (repeatable)")
    c.add_argument("--timeout", type=float, default=60.0,
                   help="seconds for the gh read (in --wait mode: the WHOLE poll's wall-clock budget instead)")
    c.add_argument("--wait", action="store_true",
                   help="poll every --interval seconds until every check is green, one FAILs, or --timeout elapses")
    c.add_argument("--interval", type=float, default=45.0, help="--wait: seconds between polls")
    c.add_argument("--min-checks", type=int, default=1,
                   help="--wait: require at least this many checks observed before ALL GREEN")
    dp = sub.add_parser("deps", parents=[common], help="fail a green when a dependency diff resolves packages outside the worktree")
    dp.add_argument("--repo", default=".")
    dp.add_argument("--base", default="origin/main", help="ref the lane branched from")
    dp.add_argument("--timeout", type=float, default=DEFAULT_GIT_TIMEOUT, help="seconds per git call")
    a = sub.add_parser("attested", parents=[common], help="gate a ready-flip on a non-author REVIEW of the exact head")
    a.add_argument("--gh-repo", required=True, help="OWNER/NAME holding the PR")
    a.add_argument("--pr", type=int, required=True)
    a.add_argument("--board-issue", type=int, required=True, help="the coordination issue holding REVIEW posts")
    a.add_argument("--board-repo", help="OWNER/NAME of the board issue (default: --gh-repo)")
    a.add_argument("--author", required=True, help="board id of the lane that wrote the PR (its REVIEW never counts)")
    a.add_argument("--timeout", type=float, default=30.0, help="seconds per gh call")
    a.add_argument("--draft-skip-ci", action="store_true",
                   help="CI skips drafts and runs on ready_for_review: never changes the verdict, "
                        "only says explicitly that checks were not required for this ready decision")
    return p


def main(argv=None):
    """CLI entry point; returns the exit code (0 PASS, 1 FAIL, 2 COULD_NOT_CHECK)."""
    args = _parser().parse_args(argv)
    if args.selftest:
        return _selftest()
    if not args.mode:
        _parser().print_usage(sys.stderr)
        return COULD_NOT_CHECK
    # Printed and JSON surfaces never carry userinfo, a query, or a fragment (tokens live there).
    if args.mode == "served":
        surface, proves = redact_url(args.url), PROVES
    elif args.mode == "ref":
        surface, proves = f"{redact_url(args.remote)}/{args.branch} in {args.repo}", PROVES_REF
    elif args.mode == "deps":
        surface, proves = f"dependencies resolved from {args.repo}", PROVES_DEPS
    elif args.mode == "attested":
        surface, proves = f"PR #{args.pr} of {args.gh_repo} + board #{args.board_issue}", PROVES_ATTESTED
    else:
        surface, proves = f"check-runs of {args.gh_repo}", PROVES_CHECKS
    waiting = args.mode == "checks" and getattr(args, "wait", False)
    label = None
    try:
        if args.mode == "served":
            code, observed, reason = check_served(args.url, args.expect_sha, args.probe, args.timeout)
        elif args.mode == "ref":
            code, observed, reason = check_ref(args.repo, args.remote, args.branch, args.expect_sha, args.timeout,
                                               args.require_clean)
        elif args.mode == "deps":
            code, observed, reason = check_deps(args.repo, args.base, args.timeout)
        elif waiting:
            code, label, reason = wait_for_checks(args.gh_repo, args.sha, args.require, args.interval,
                                                  args.timeout, args.min_checks)
            observed = None
        elif args.mode == "attested":
            code, observed, reason = check_attested(args.gh_repo, args.pr, args.board_issue, args.author,
                                                    args.board_repo, args.timeout, args.draft_skip_ci)
        else:
            code, observed, reason = check_checks(args.gh_repo, args.sha, args.require, args.timeout)
    except CheckError as exc:
        code, observed, reason = COULD_NOT_CHECK, None, str(exc)
    if getattr(args, "json", False):
        doc = {
            "mode": args.mode, "verdict": VERDICT[code], "exit": code, "surface": surface,
            "expect_sha": getattr(args, "sha", None) or getattr(args, "expect_sha", None), "observed": observed, "reason": reason,
            "checked_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "proves": proves,
        }
        if waiting:
            doc["label"] = label
        print(json.dumps(doc, sort_keys=True))
    elif waiting:
        print(label)
    else:
        print(f"surface_check {args.mode}: {VERDICT[code]} — {reason}")
        print(f"  surface: {surface}; proves: {proves}")
    return code


# --------------------------------------------------------------------------
# --selftest — offline: a local http.server fixture on 127.0.0.1 and throwaway
# git repos (a bare "remote" plus a clone) in a temp dir. Every negative case
# proves the check FIRES (never a silent pass).
# --------------------------------------------------------------------------
def _selftest():
    import http.server
    import shutil
    import tempfile
    import threading

    global _PROXIES
    _PROXIES = {}
    good = "0123456789abcdef0123456789abcdef01234567"
    stale = "fedcba9876543210fedcba9876543210fedcba98"
    routes = {
        "/hdr": (200, {"X-Build-Sha": good}, ""),
        "/hdr-stale": (200, {"X-Build-Sha": stale}, ""),
        "/hdr-short": (200, {"X-Build-Sha": "0123"}, ""),
        "/hdr-ts": (200, {"X-Build-Sha": "2026-09-23T10:00:00Z"}, ""),
        "/none": (200, {}, '<html><script>{"data_as_of":"2026-09-23T10:00:00Z"}</script></html>'),
        "/meta": (200, {}, f'<html><head><meta name="build-sha" content="{good}"></head></html>'),
        "/mixed": (200, {"X-Build-Sha": good}, f'<meta name="build-sha" content="{stale}">'),
        "/version.json": (200, {}, json.dumps({"build": {"sha": good[:12]},
                                               "data_as_of": "2026-09-23T10:00:00Z", "ts": 1790000000})),
        "/notjson.json": (200, {}, "<html>nope</html>"),
        "/redir": (302, {"Location": "/hdr"}, ""),
        "/boom": (500, {"X-Build-Sha": good}, ""),
        "/proxied": (203, {"X-Build-Sha": good}, ""),
        "/hdr-secret": (200, {"X-Build-Sha": "Bearer s3cr3t-t0ken-value"}, ""),
        "/redir-cred": (302, {"Location": "https://jane:hunter2@evil.example/next?token=abc#frag"}, ""),
    }

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/drip":  # a body that trickles in under the per-read timeout forever
                self.send_response(200)
                self.send_header("Content-Length", "100000")
                self.end_headers()
                with contextlib.suppress(OSError):
                    for _ in range(200):
                        self.wfile.write(b"<")
                        self.wfile.flush()
                        time.sleep(0.1)
                return
            code, hdrs, body = routes.get(path, (404, {}, "missing"))
            data = body.encode()
            self.send_response(code)
            for k, v in hdrs.items():
                self.send_header(k, v)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    passed = failed = 0

    def run(argv):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(argv)
        return rc, buf.getvalue()

    def case(name, argv, want, must=None):
        nonlocal passed, failed
        rc, out = run(argv)
        ok = rc == want and (must is None or must in out)
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name} (rc={rc}, want {want})" + ("" if ok else f"\n      {out.strip()}"))

    def served(path, sha, *probes):
        argv = ["served", "--url", base + path, "--expect-sha", sha, "--timeout", "5"]
        for pr in probes:
            argv += ["--probe", pr]
        return argv

    H_ = "header:x-build-sha"
    case("served: header full sha matches", served("/hdr", good, H_), PASS)
    case("served: 7-char expected prefix matches", served("/hdr", good[:7], H_), PASS)
    case("served: stale build id FIRES", served("/hdr-stale", good, H_), FAIL, "stale or wrong build")
    case("served: missing id -> could not check", served("/none", good, H_), COULD_NOT_CHECK, "no build id")
    case("served: payload timestamp is not a build id", served("/hdr-ts", good, H_), COULD_NOT_CHECK,
         "not a commit sha")
    case("served: served id too short refused", served("/hdr-short", good, H_), COULD_NOT_CHECK)
    case("served: meta tag matches", served("/meta", good, "meta:build-sha"), PASS)
    case("served: meta absent (only a data stamp) refused", served("/none", good, "meta:build-sha"),
         COULD_NOT_CHECK)
    case("served: version.json dotted key (short served id) matches",
         served("/", good, "path:/version.json:build.sha"), PASS)
    case("served: version.json data_as_of stamp refused",
         served("/", good, "path:/version.json:data_as_of"), COULD_NOT_CHECK, "not a build id")
    case("served: version.json numeric ts refused", served("/", good, "path:/version.json:ts"),
         COULD_NOT_CHECK)
    case("served: non-JSON version path refused", served("/", good, "path:/notjson.json:sha"),
         COULD_NOT_CHECK, "not JSON")
    case("served: probes disagree FIRES", served("/mixed", good, H_, "meta:build-sha"), FAIL)
    case("served: redirect not followed", served("/redir", good, H_), COULD_NOT_CHECK, "redirected (302)")
    case("served: HTTP 500 refused even with a matching header", served("/boom", good, H_),
         COULD_NOT_CHECK, "HTTP 500")
    case("served: HTTP 404 refused", served("/gone", good, H_), COULD_NOT_CHECK, "HTTP 404")
    case("served: non-200 2xx (203) refused", served("/proxied", good, H_), COULD_NOT_CHECK, "HTTP 203")
    case("served: expected sha < 7 chars refused", served("/hdr", good[:6], H_), COULD_NOT_CHECK,
         "shorter than 7")
    case("served: non-hex expected sha refused", served("/hdr", "v1.2.3-abc", H_), COULD_NOT_CHECK)
    case("served: no probe refused", served("/hdr", good), COULD_NOT_CHECK, "at least one --probe")
    case("served: bad probe spec refused", served("/hdr", good, "cookie:x"), COULD_NOT_CHECK, "bad --probe")
    case("served: non-http scheme refused",
         ["served", "--url", "file:///etc/hosts", "--expect-sha", good, "--probe", H_], COULD_NOT_CHECK)
    rc, out = run(["served", "--json", "--url", base + "/hdr-stale", "--expect-sha", good, "--probe", H_])
    try:
        doc = json.loads(out)
        ok = (rc == FAIL and doc["verdict"] == "FAIL" and doc["observed"] == stale
              and doc["proves"] == PROVES and doc["checked_at"].endswith("Z"))
    except (ValueError, KeyError):
        ok = False
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  served --json: machine verdict carries observed id + proves")

    def no_leak(name, argv, want, secrets, must):
        nonlocal passed, failed
        rc, out = run(argv)
        ok = rc == want and must in out and not any(s in out for s in secrets)
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name} (rc={rc}, want {want})" + ("" if ok else f"\n      {out.strip()}"))

    no_leak("served: non-sha value reported as type+length, never echoed", served("/hdr-secret", good, H_),
            COULD_NOT_CHECK, ("s3cr3t", "Bearer"), "str of length 25")
    no_leak("served: redirect Location stripped of userinfo/query/fragment", served("/redir-cred", good, H_),
            COULD_NOT_CHECK, ("hunter2", "jane", "token=abc", "frag"), "https://evil.example/next")
    no_leak("served: surface drops query in text output", served("/hdr?token=abc", good, H_), PASS,
            ("token=abc",), f"surface: {base}/hdr;")
    cred = base.replace("http://", "http://jane:hunter2@") + "/hdr?token=abc"
    no_leak("served --json: userinfo URL refused; surface and reason drop userinfo and query",
            ["served", "--json", "--url", cred, "--expect-sha", good, "--probe", H_, "--timeout", "5"],
            COULD_NOT_CHECK, ("hunter2", "jane", "token=abc"), f'"surface": "{base}/hdr"')
    t0 = time.monotonic()
    rc, out = run(["served", "--url", base + "/drip", "--expect-sha", good, "--probe", "meta:build-sha",
                   "--timeout", "1"])
    ok = rc == COULD_NOT_CHECK and "wall-clock" in out and time.monotonic() - t0 < 10
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  served: trickling body hits the wall-clock cap (rc={rc})"
          + ("" if ok else f"\n      {out.strip()}"))
    srv.shutdown()

    tmp = tempfile.mkdtemp(prefix="surface-check-selftest-")
    env_keys = ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM", "GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL",
                "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL", "GIT_SSH_COMMAND")
    saved = {k: os.environ.get(k) for k in env_keys}
    os.environ.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1",
                      GIT_AUTHOR_NAME="Jane Smith", GIT_AUTHOR_EMAIL="jane@example.com",
                      GIT_COMMITTER_NAME="Jane Smith", GIT_COMMITTER_EMAIL="jane@example.com")
    try:
        remote = os.path.join(tmp, "remote.git")
        work = os.path.join(tmp, "work")
        g = lambda *a: subprocess.run(["git", *a], capture_output=True, text=True, check=True).stdout.strip()
        g("init", "--quiet", "--bare", remote)
        g("init", "--quiet", work)
        g("-C", work, "commit", "--quiet", "--allow-empty", "-m", "a")
        g("-C", work, "remote", "add", "origin", remote)
        g("-C", work, "push", "--quiet", "origin", "HEAD:refs/heads/main")
        pushed = g("-C", work, "rev-parse", "HEAD")
        g("-C", work, "commit", "--quiet", "--allow-empty", "-m", "b")
        local_only = g("-C", work, "rev-parse", "HEAD")

        def ref(sha, branch="main"):
            return ["ref", "--repo", work, f"--branch={branch}", "--expect-sha", sha]

        case("ref: pushed sha reachable", ref(pushed), PASS)
        case("ref: pushed 7-char prefix reachable", ref(pushed[:7]), PASS)
        case("ref: local-only commit FIRES (merged locally, not on remote)", ref(local_only), FAIL,
             "NOT reachable")
        case("ref: unknown sha FIRES", ref(stale), FAIL, "is not in")
        case("ref: sha < 7 chars refused", ref(pushed[:6]), COULD_NOT_CHECK, "shorter than 7")
        case("ref: missing remote branch refused", ref(pushed, "nope"), COULD_NOT_CHECK, "git fetch")
        case("ref: option-like branch refused", ref(pushed, "--upload-pack=x"), COULD_NOT_CHECK, "bad --branch")

        # Two blobs whose ids share a 7-hex prefix (found by a birthday search
        # over this content template): a 7-char --expect-sha naming either is
        # ambiguous and must be refused, never read as "not on the branch".
        blob = lambda i: subprocess.run(["git", "-C", work, "hash-object", "-w", "--stdin"], check=True,
                                        input=f"surface-check ambiguity fixture {i}\n", capture_output=True,
                                        text=True).stdout.strip()
        b1, b2 = blob(1365), blob(3820)
        if b1[:MIN_SHA] == b2[:MIN_SHA]:
            case("ref: ambiguous 7-char sha refused", ref(b1[:MIN_SHA]), COULD_NOT_CHECK, "ambiguous")
        else:
            failed += 1
            print(f"FAIL  ref: ambiguity fixture no longer collides ({b1[:MIN_SHA]} vs {b2[:MIN_SHA]})")

        # Edit done is not committed: a commit a hook rejected leaves the edit
        # staged while HEAD (already pushed) still passes a plain reachability check.
        with open(os.path.join(work, "app.txt"), "w") as fh:
            fh.write("v1\n")
        g("-C", work, "add", "app.txt")
        g("-C", work, "commit", "--quiet", "-m", "c")
        g("-C", work, "push", "--quiet", "origin", "HEAD:refs/heads/main")
        clean_head = g("-C", work, "rev-parse", "HEAD")
        case("ref --require-clean: committed and pushed passes", ref(clean_head) + ["--require-clean"], PASS)
        with open(os.path.join(work, "app.txt"), "w") as fh:
            fh.write("v2\n")
        g("-C", work, "add", "app.txt")
        case("ref: staged-not-committed edit is invisible without --require-clean", ref(clean_head), PASS)
        case("ref --require-clean: staged-not-committed edit FIRES", ref(clean_head) + ["--require-clean"], FAIL,
             "not committed")
        g("-C", work, "reset", "--quiet", "app.txt")
        case("ref --require-clean: unstaged edit FIRES", ref(clean_head) + ["--require-clean"], FAIL,
             "1 tracked path")
        g("-C", work, "checkout", "--quiet", "--", "app.txt")
        # A new file the lane wrote but never added is also edit-done-not-committed.
        with open(os.path.join(work, "new_module.py"), "w") as fh:
            fh.write("x = 1\n")
        case("ref --require-clean: untracked new file FIRES", ref(clean_head) + ["--require-clean"], FAIL,
             "untracked")
        os.remove(os.path.join(work, "new_module.py"))
        case("ref --require-clean: clean again after removal passes", ref(clean_head) + ["--require-clean"], PASS)

        g("-C", work, "push", "--quiet", "origin", "HEAD:refs/heads/dev")
        shallow = os.path.join(tmp, "shallow")
        g("clone", "--quiet", "--depth", "1", "--branch", "dev", "file://" + remote, shallow)
        case("ref: shallow clone refused", ["ref", "--repo", shallow, "--branch=dev", "--expect-sha", pushed],
             COULD_NOT_CHECK, "shallow clone")

        # A remote whose transport hangs (a stand-in ssh that only sleeps) must
        # hit the timeout and exit 2, not block the caller.
        g("-C", work, "remote", "add", "slow", "ssh://git@hang.example.invalid/x.git")
        os.environ["GIT_SSH_COMMAND"] = "sleep 30 #"
        t0 = time.monotonic()
        case("ref: hung fetch times out -> could not check",
             ["ref", "--repo", work, "--remote", "slow", "--branch=main", "--expect-sha", pushed, "--timeout", "1"],
             COULD_NOT_CHECK, "timed out")
        if time.monotonic() - t0 > 10:
            failed += 1
            print("FAIL  ref: hung fetch was not killed promptly")
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(tmp, ignore_errors=True)

    p2, f2 = _selftest_checks()
    passed += p2
    failed += f2
    p3, f3 = _selftest_wait()
    passed += p3
    failed += f3
    p4, f4 = _selftest_attested()
    passed += p4
    failed += f4
    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


_FAKE_SHA = "0123456789abcdef0123456789abcdef01234567"  # shared by _selftest_checks and _selftest_wait


def _cr(i, name, status="completed", conclusion="success", done="2026-09-23T10:00:00Z", head=_FAKE_SHA, app=None,
        suite=None):
    """One fake check-run object (see the `checks --gh-repo` docstring for the fields judged). Pure."""
    run = {"id": i, "name": name, "status": status, "conclusion": conclusion if status == "completed" else None,
           "completed_at": done if status == "completed" else None, "head_sha": head}
    if app is not None:
        run["app"] = {"id": app, "slug": f"app{app}"}
    if suite is not None:
        run["check_suite"] = {"id": suite}
    return run


def _pages(*page_runs, total=None):
    """Concatenated `gh api --paginate` pages for the given per-page run lists. Pure."""
    n = sum(len(r) for r in page_runs) if total is None else total
    return "".join(json.dumps({"total_count": n, "check_runs": list(r)}) for r in page_runs)


def _selftest_checks():
    """Offline `checks` cases: a fake `gh` answers the check-runs read. Returns (passed, failed)."""
    sha = _FAKE_SHA
    passed = failed = 0
    cr, pages = _cr, _pages

    def case(name, out, argv_extra, want, must, rc=0):
        global _gh
        nonlocal passed, failed
        seen = []

        def fake(args, timeout):
            seen.append(args)
            return rc, out, "HTTP 502" if rc else ""

        saved, _gh = _gh, fake
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                got = main(["checks", "--gh-repo", "acme/app", "--sha", sha, *argv_extra])
        finally:
            _gh = saved
        text = buf.getvalue()
        ok = got == want and must in text and (not seen or "filter=latest" in seen[0][-1])
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  checks: {name} (rc={got}, want {want})" + ("" if ok else f"\n      {text.strip()}"))

    stale_red_then_green = pages([cr(1, "test", conclusion="failure", done="2026-09-23T10:00:00Z"),
                                  cr(2, "test", done="2026-09-23T10:05:00Z"), cr(3, "lint")])
    case("older red + newer green rerun reads green (per-name latest, not the rollup)", stale_red_then_green, [],
         PASS, "2 PASS")
    case("newer red beats older green", pages([cr(1, "test", done="2026-09-23T10:00:00Z"),
                                               cr(2, "test", conclusion="failure", done="2026-09-23T10:05:00Z")]),
         [], FAIL, "FAIL: test (failure)")
    case("a live rerun is pending, not the older green", pages([cr(1, "test"), cr(2, "test", status="in_progress")]),
         [], COULD_NOT_CHECK, "PENDING: test (in_progress)")
    case("cancelled latest is pending, never red", pages([cr(1, "test", conclusion="cancelled")]), [],
         COULD_NOT_CHECK, "PENDING: test (cancelled)")
    case("a required check with no run is NO-RUN", pages([cr(1, "lint")]), ["--require", "test", "--require", "lint"],
         COULD_NOT_CHECK, "NO-RUN: test")
    case("required subset ignores an unrelated red", pages([cr(1, "lint"), cr(2, "docs", conclusion="failure")]),
         ["--require", "lint"], PASS, "1 PASS")
    case("two pages summed", pages([cr(i, f"job{i}") for i in range(1, 101)], [cr(101, "job101")]), [], PASS,
         "101 PASS")
    case("truncated pages refused", pages([cr(1, "test")], total=5), [], COULD_NOT_CHECK, "truncated")
    case("no check-runs for the sha", pages([]), [], COULD_NOT_CHECK, "no check-runs")
    case("gh failure could not check", "", [], COULD_NOT_CHECK, "gh api failed", rc=1)
    case("a run for another sha is ignored", pages([cr(1, "test", conclusion="failure", head="f" * 40), cr(2, "test")]),
         [], PASS, "1 PASS")
    case("unknown conclusion fails closed", pages([cr(1, "test", conclusion="startup_failure")]), [], FAIL,
         "FAIL: test (startup_failure)")
    case("completion time decides, not creation order",
         pages([cr(2, "test", conclusion="cancelled", done="2026-09-23T10:00:00Z"),
                cr(1, "test", done="2026-09-23T10:05:00Z")]), [], PASS, "1 PASS")
    # One name, several producers (two workflows or apps both emit "test"):
    # each (app, check suite, name) group has its own latest run, and when
    # those latest runs disagree the name is ambiguous, never "the newest
    # wins" — a later green from workflow B must not hide a red from A.
    case("same name from two suites that disagree is ambiguous, not newest-wins",
         pages([cr(1, "test", conclusion="failure", done="2026-09-23T10:00:00Z", app=1, suite=11),
                cr(2, "test", done="2026-09-23T10:05:00Z", app=1, suite=22)]), [], FAIL,
         "ambiguous: 2 latest runs disagree")
    case("same name from two apps that disagree is ambiguous",
         pages([cr(1, "test", conclusion="failure", done="2026-09-23T10:00:00Z", app=1, suite=5),
                cr(2, "test", done="2026-09-23T10:05:00Z", app=2, suite=6)]), ["--require", "test"], FAIL,
         "ambiguous")
    case("same name from two suites that agree passes",
         pages([cr(1, "test", app=1, suite=11), cr(2, "test", app=1, suite=22)]), [], PASS, "1 PASS")
    case("a rerun inside one suite still supersedes its older red",
         pages([cr(1, "test", conclusion="failure", done="2026-09-23T10:00:00Z", app=1, suite=11),
                cr(2, "test", done="2026-09-23T10:05:00Z", app=1, suite=11)]), [], PASS, "1 PASS")
    with contextlib.redirect_stdout(io.StringIO()):
        rc = main(["checks", "--gh-repo", "not a slug", "--sha", sha])
    ok = rc == COULD_NOT_CHECK
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  checks: bad --gh-repo refused (rc={rc})")
    return passed, failed


def _selftest_wait():
    """Offline `checks --wait` cases: a scripted `_gh` sequence plus a fake clock (no real sleeping). Returns (passed, failed)."""
    global _gh, _sleep, _monotonic
    sha, cr, pages = _FAKE_SHA, _cr, _pages
    passed = failed = 0

    def case(name, gh_responses, argv_extra, want, must, min_sleeps=None):
        global _gh, _sleep, _monotonic
        nonlocal passed, failed
        calls = {"gh": 0, "sleep": 0}
        clock = [0.0]

        def fake_gh(args, timeout):
            i = min(calls["gh"], len(gh_responses) - 1)
            calls["gh"] += 1
            out = gh_responses[i]
            return (0, out, "") if out is not None else (1, "", "HTTP 502")

        def fake_sleep(seconds):
            calls["sleep"] += 1
            clock[0] += max(seconds, 1.0)  # a no-op sleep must still advance the fake clock past --interval

        def fake_monotonic():
            return clock[0]

        saved = (_gh, _sleep, _monotonic)
        _gh, _sleep, _monotonic = fake_gh, fake_sleep, fake_monotonic
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = main(["checks", "--gh-repo", "acme/app", "--sha", sha, "--wait", *argv_extra])
        finally:
            _gh, _sleep, _monotonic = saved
        text = buf.getvalue()
        ok = rc == want and must in text and (min_sleeps is None or calls["sleep"] >= min_sleeps)
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  wait: {name} (rc={rc}, want {want}, gh calls={calls['gh']}, "
              f"sleeps={calls['sleep']})" + ("" if ok else f"\n      {text.strip()}"))

    all_green = pages([cr(1, "test"), cr(2, "lint")])
    one_pending = pages([cr(1, "test"), cr(2, "lint", status="in_progress")])
    terminal_fail = pages([cr(1, "test", conclusion="failure"), cr(2, "lint")])
    none_yet = pages([])

    case("already green: no polling needed", [all_green], ["--interval", "0.01", "--timeout", "5"], PASS,
         "ALL GREEN", min_sleeps=0)
    case("green line names the repo, sha, and count", [all_green], ["--interval", "0.01", "--timeout", "5"], PASS,
         f"acme/app @{sha[:12]} checks=2 ALL GREEN")
    case("terminal FAIL returns immediately, no polling wasted", [terminal_fail],
         ["--interval", "0.01", "--timeout", "5"], FAIL, "NOT-GREEN: test", min_sleeps=0)
    case("pending then green: one poll, one sleep", [one_pending, all_green],
         ["--interval", "0.01", "--timeout", "5"], PASS, "ALL GREEN", min_sleeps=1)
    case("still pending at the deadline -> COULD_NOT_CHECK, names the pending check", [one_pending] * 5,
         ["--interval", "1", "--timeout", "2"], COULD_NOT_CHECK, "NOT-GREEN: lint")
    case("zero checks dispatched yet stays NOT-GREEN past --min-checks, never a false green", [none_yet] * 5,
         ["--interval", "1", "--timeout", "2", "--min-checks", "1"], COULD_NOT_CHECK, "checks=0 NOT-GREEN")
    case("uncheckable gh read (--gh error) keeps polling, not an immediate crash", [None, all_green],
         ["--interval", "0.01", "--timeout", "5"], PASS, "ALL GREEN", min_sleeps=1)
    case("--require narrows to the named subset only", [pages([cr(1, "lint"), cr(2, "docs", conclusion="failure")])],
         ["--require", "lint", "--interval", "0.01", "--timeout", "5"], PASS, "checks=1 ALL GREEN")

    saved = _gh
    try:
        _gh = lambda args, timeout: (0, all_green, "")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = main(["checks", "--gh-repo", "acme/app", "--sha", sha, "--wait", "--json",
                      "--interval", "0.01", "--timeout", "5"])
    finally:
        _gh = saved
    try:
        doc = json.loads(buf.getvalue())
        ok = (rc == PASS and doc["verdict"] == "PASS" and doc["label"] == f"acme/app @{sha[:12]} checks=2 ALL GREEN"
              and doc["proves"] == PROVES_CHECKS)
    except (ValueError, KeyError):
        ok = False
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  wait --json: carries the one-line label plus the usual verdict/proves fields")
    # --interval 0 is clamped to MIN_WAIT_INTERVAL: a 20s budget allows at most ~5 polls, never a tight loop.
    polls = {"gh": 0}
    clock = [0.0]
    pending = pages([cr("build", "in_progress", None)])
    def gh_pending(args, timeout):
        polls["gh"] += 1
        return 0, pending, ""
    def adv(seconds):
        clock[0] += seconds
    saved = (_gh, _sleep, _monotonic)
    _gh, _sleep, _monotonic = gh_pending, adv, (lambda: clock[0])
    try:
        code, _, _ = wait_for_checks("acme/app", sha, [], 0, 20, 1)
    finally:
        _gh, _sleep, _monotonic = saved
    ok = polls["gh"] <= 6 and code == COULD_NOT_CHECK
    passed += ok
    failed += not ok
    print(f"{'PASS' if ok else 'FAIL'}  wait: --interval 0 clamped (gh calls={polls['gh']}, want <=6)")
    return passed, failed


def _selftest_attested():
    """Offline `attested` cases: a fake `gh` answers the PR read, the board read, and `gh pr ready`.

    Returns (passed, failed). Every negative case proves the gate FIRES; no case may run `gh pr ready`.
    """
    head, old = _FAKE_SHA, "f" * 40
    passed = failed = 0

    def review(cid, agent, sha=head, verdict="approve", branch="lane/cart-fix", refs="#41", edited=False,
               login="fleet-bot"):
        created = f"2026-09-24T10:{cid:02d}:00Z"
        body = f"[agent:{agent}] REVIEW refs:{refs} sha:{sha} branch:{branch} verdict:{verdict} resolved:2\nreviewed"
        return {"id": cid, "body": body, "created_at": created,
                "updated_at": "2026-09-24T11:59:00Z" if edited else created, "user": {"login": login}}

    def case(name, comments, want, must, draft=True, board_rc=0, author="builder-1", pr_login=None,
             draft_skip_ci=False, must_not=None):
        global _gh
        nonlocal passed, failed
        calls = []

        def fake(args, timeout):
            calls.append(args)
            if args[:3] == ["gh", "pr", "ready"]:
                return 0, "", ""
            if "/pulls/" in args[-1]:
                doc = {"draft": draft, "head": {"sha": head, "ref": "lane/cart-fix"}}
                if pr_login is not None:
                    doc["user"] = {"login": pr_login}
                return 0, json.dumps(doc), ""
            if "/comments" in args[-1]:
                return board_rc, json.dumps(comments), "HTTP 502" if board_rc else ""
            return 1, "", f"unexpected call {args}"

        saved, _gh = _gh, fake
        buf = io.StringIO()
        argv = ["attested", "--gh-repo", "acme/app", "--pr", "41", "--board-issue", "7", "--author", author]
        if draft_skip_ci:
            argv.append("--draft-skip-ci")
        try:
            with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(io.StringIO()):
                got = main(argv)
        except SystemExit as exc:
            got = f"SystemExit({exc.code})"
        finally:
            _gh = saved
        text = buf.getvalue()
        flipped = any(c[:3] == ["gh", "pr", "ready"] for c in calls)
        ok = got == want and must in text and not flipped and (must_not is None or must_not not in text)
        passed += ok
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  attested: {name} (rc={got}, want {want}, flipped={flipped})"
              + ("" if ok else f"\n      {text.strip()}"))

    case("non-author approval at the exact head passes", [review(1, "reviewer-2")], PASS, "approved by reviewer-2")
    case("approval of an older head (a push since) FIRES", [review(1, "reviewer-2", sha=old)], FAIL,
         "no REVIEW verdict:approve")
    case("author self-approval FIRES", [review(1, "builder-1")], FAIL, "author's own REVIEW does not count")
    case("a second reviewer's changes verdict at the head FIRES",
         [review(1, "reviewer-2"), review(2, "reviewer-3", verdict="changes")], FAIL, "reviewer-3 requested changes")
    case("a reviewer's later approve supersedes its own changes",
         [review(1, "reviewer-2", verdict="changes"), review(2, "reviewer-2")], PASS, "approved by reviewer-2")
    case("approval for another branch FIRES", [review(1, "reviewer-2", branch="lane/other")], FAIL,
         "no REVIEW verdict:approve")
    case("approval naming another PR FIRES", [review(1, "reviewer-2", refs="#40")], FAIL, "no REVIEW verdict:approve")
    case("edited attestation is not trusted", [review(1, "reviewer-2", edited=True)], FAIL, "edited after posting")
    case("short-sha attestation is malformed and ignored", [review(1, "reviewer-2", sha=head[:12])], FAIL,
         "no REVIEW verdict:approve")
    case("board read error -> could not check", [], COULD_NOT_CHECK, "failed", board_rc=1)
    case("a passing draft names the ready command but never runs it", [review(1, "reviewer-2")], PASS,
         "gh pr ready 41 --repo acme/app")
    case("an already-ready PR says so", [review(1, "reviewer-2")], PASS, "already ready", draft=False)
    case("bad --author refused", [review(1, "reviewer-2")], COULD_NOT_CHECK, "--author", author="-bad id")
    case("--author mismatched against the PR's real login refuses", [review(1, "reviewer-2")],
         COULD_NOT_CHECK, "does not match", pr_login="someone-else")
    case("--author matching the PR's real login passes as before", [review(1, "reviewer-2")], PASS,
         "approved by reviewer-2", pr_login="builder-1")
    case("reviewer login equal to the PR's own login is not attested despite a different declared id",
         [review(1, "reviewer-2", login="builder-1")], FAIL, "not attested", pr_login="builder-1")
    case("reviewer sharing a login with the author's own REVIEW on this PR is not attested",
         [review(1, "builder-1", login="shared-bot"), review(2, "reviewer-2", login="shared-bot")],
         FAIL, "not attested")
    case("a distinct reviewer login still passes when it differs from both the author's login and the "
         "PR's login", [review(1, "builder-1", login="shared-bot"), review(2, "reviewer-2", login="other-bot")],
         PASS, "approved by reviewer-2")
    case("--draft-skip-ci says checks were not required, never changes the verdict",
         [review(1, "reviewer-2")], PASS, "checks are not required for this decision", draft_skip_ci=True)
    case("--draft-skip-ci on an already-ready (non-draft) PR omits the note: nothing to explain",
         [review(1, "reviewer-2")], PASS, "already ready", draft=False, draft_skip_ci=True,
         must_not="draft-skip-ci")
    return passed, failed


if __name__ == "__main__":
    sys.exit(main())
