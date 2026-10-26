#!/usr/bin/env python3
"""merge_train.py — land several green PRs as ONE verified union (a merge train).

WHY THIS EXISTS (the failure it closes)
----------------------------------------
deep-code-review's `references/merge-operations.md` (*Merge trains*) states
the rules for landing several independently-green PRs without a platform
merge queue: verify the combination once, isolate a culprit by holding the
others out for the suspect's whole verification cycle (issue #1119), attribute
a numeric-cap overshoot to the member that owns it (issue #1106), retry the
union immediately after parking a member instead of sleeping a cycle per
conflict (issue #1134), and never merge onto a base that moved or was
rewritten after the union was proved (issue #1137), and never compare against
a stale fetched ref (issue #1139). Prose alone let every one
of those rules be skipped under pressure; this script is the mechanism.

SUBCOMMANDS
-----------
  plan    List open PRs targeting --base that are non-draft, same-repo (fork
          heads skipped unless --allow-forks), MERGEABLE, not parked, and
          green: the LATEST check run per name is completed with conclusion
          success/neutral/skipped, and at least --min-checks (K, >= 1) of those
          latest runs are `success`. Commit statuses (the legacy status API)
          are not read. Read-only.
  verify  Re-plan, fetch the base and every member head (`git ls-remote`
          first, then forced refspecs into refs unique to this run; a failed
          fetch or a base still stale after bounded retries stops the cycle,
          while a member still stale, gone, or moved since plan is skipped
          alone), then build ONE union
          in a throwaway worktree (members merged in PR-number order onto the
          fresh base) and run --verify-cmd once in it (plus --count-cmd vs --cap
          when given). On a merge conflict the member is parked with its files
          and the union is rebuilt at once, so N conflicts cost one run, not N
          cycles (#1134). On a deterministic failure:
            - numeric cap failed (--count-cmd output > --cap): print one line
              per member, `#N +D marker=present|none`, where D is the count at
              the member's head minus the count at its own merge-base with the
              base, and marker is whether the member's own commit range carries
              a `<--marker-key>: ...` line (#1106); every member with D > 0 and
              marker=none is parked;
            - otherwise (or when attribution names no one): prefix bisection.
              The base alone must pass (else HALT); the smallest failing prefix
              names the culprit — the member whose inclusion breaks the gate.
              Members outside a prefix are held out for that prefix's entire
              verification run, never re-admitted mid-search (#1119).
          A parked member stays excluded from every later plan/verify until its
          head changes. The surviving union is rebuilt immediately. When a
          union is green the base SHA and member heads are recorded in --state.
  merge   Dry-run by default: prints what would merge. With --apply (and
          --grant) it merges the recorded members back-to-back with
          `gh pr merge --merge --match-head-commit`, preserving each member's
          own commits and closing keywords (never a squash of the union). It
          refuses (HALT) unless the base head equals the SHA the union was
          proved on: a fast-forward move means re-plan; a non-fast-forward move
          means a possible history rewrite and needs a human (#1137). It never
          re-verifies on its own. Before each merge the PR must still be OPEN,
          at the recorded head, and MERGEABLE (UNKNOWN is polled with bounded
          backoff); after each merge the new base head must be exactly the merge
          of the previous head and that member, else another writer moved the
          base mid-train (HALT). A member that fails deterministically is parked
          with its reason and the rest HALT, because the remaining combination
          was never verified.
  partial-kill (#1778) A PR whose precheck ended COULD_NOT_CHECK on some checks carries a PARTIAL-PASS receipt
          written by `partial_pass.py write` (dir --partial-dir / $PARTIAL_DIR / .perun/partial), valid for its
          exact head, naming EXACTLY the unchecked checks and a kill criterion. plan/verify judge every check;
          a named one is skipped only while it is missing or unfinished on the head (one that ran and failed
          still blocks); the ELIGIBLE line shows `PARTIAL-PASS unchecked=...`. At most ONE such PR rides a
          train, and only one may be outstanding: a second is SKIPped ("second PARTIAL-PASS ...", or "merged and
          undecided" until `partial-kill` decides the landed one); `merge` HALTs if the recorded plan breaks
          that. `merge --apply` records the landed one in --state. `partial-kill`, run once post-merge CI has
          run on the merge commit, reverts it (--apply opens the revert PR, exit 1) when any unchecked check
          failed, prints PENDING while one is running (or absent and CI still running, until --wait seconds
          after the merge), UNVERIFIED (exit 1, record kept) when one never ran or only skipped/neutral, and
          KEPT only when every named check succeeded. A partial pass is never counted as a pass.
  keystone  The owner's pre-ratified red-base exception for ONE fix PR (issue
          #1142; deep-code-review `merge-operations.md` *Red base*). Needs
          --only globs naming the files the fix may touch; every glob must
          start with a literal directory (`src/clock*.py`, never `*.py`, `s*`
          or `**`), and `*`/`?` never cross `/` (fix_class_gate's grammar).
          Refuses (HALT) unless, in order: the PR is open, targets --base, and
          passes plan's eligibility (non-draft, same-repo, MERGEABLE, checks
          green); every changed file (`git diff --name-only --no-renames`, so a
          file renamed in from elsewhere shows its source) matches --only; the
          grants file (fixed path `.claude/KEYSTONE-GRANTS`, never chosen by the
          caller), committed on the fetched base, holds a grant line blamed to
          an owner email with no Co-authored-by trailer (focus_gate's
          standing-grant check; owners from --owner-email, DCR_OWNER_EMAIL, or
          git config dcr.owner, none = HALT; --require-signed also needs a good
          signature). Grant lines:
            keystone: #<pr> @<sha>                                 pins the PR's head
            keystone: #<pr> | <globs> | expires=D | max-files=N    the PR, within limits
            keystone-class: <globs> | expires=D | max-files=N      one keystone of a shape
          A bare `keystone: #<pr>` is refused. Limits need an unexpired date at
          most 30 days after the line's commit, globs covering every changed
          file, and at most N files. The PR's own lines are tried before
          classes, and the first grant that passes wins, so a spent or
          non-covering class never blocks a usable one. Then --verify-cmd must
          FAIL on the base alone after every retry (a red no open branch
          introduced; a flake is not a red base) and PASS on base + PR in a
          throwaway union. It records the keystone in --state and parks every
          sibling carrying a copy: a shared `git patch-id --stable`
          (cherry-pick), the keystone diff reverse-applying to the sibling's
          tree (squash or amend), or another edit to a keystone file (possible
          partial copy). `verify` re-screens members on every run (a re-push
          cannot slip a copy in) until the keystone lands: its head is an
          ancestor of the base, its PR is MERGED, or the base contains its
          change. Dry-run by default, and a dry run spends nothing. --apply
          merges the keystone alone (same same-base, still-ready, and
          another-writer checks as `merge`) with `Keystone-Grant:
          <commit>:<line-key>` in the merge commit body. That trailer spends
          the grant: one already in the base's history is refused until the
          owner commits the line again. Grant reads run with
          --no-replace-objects and an empty blame.ignoreRevsFile.
          After an --apply merge it runs `refresh` for the siblings (same
          local-commands-by-default as `refresh` itself, --use-update-branch
          opt-in), isolated: the merge already landed, so a refresh error is a
          WARN (exit still OK), never an ERROR/HALT that would make a landed
          merge look failed.
  refresh After a fix lands on the base, a CI re-run on an open PR reuses its
          OLD merge commit, so every PR opened before the fix stays red until
          its branch is updated: re-running is not the fix. Lists open PRs whose
          head lacks --since (default: the base head) and, by default, prints
          local `gh pr checkout <n>` + fetch + merge + push commands for that
          PR's own owner to run on their next push — zero extra CI runs. --use-update-
          branch instead prints/runs `gh pr update-branch <n>` (--apply runs
          it), a merge commit each, never `--rebase` (a rebase rewrites a
          branch its lane may be pushing to) — but each call costs one CI run,
          so it is opt-in. A draft or a fork PR is skipped (--include-drafts /
          --allow-forks admit them). A PR carrying a copy of a keystone is
          skipped: it must drop the copy and rebase, not merge the fix in twice
          (the keystone screen parks it, and a PR parked for a keystone is
          never updated). --use-update-branch calls are throttled (--backoff
          between each) and a 429/secondary-rate-limit response is retried on
          the existing --retries/--backoff schedule; a failed update is
          reported and the rest still run. Does not coordinate with a lane
          mid-push: run --use-update-branch only when no lane is pushing to
          the PRs it updates, or have lanes rebase afterward, since a lane's
          later force-push drops the merge commit refresh just made.
  dupes   Parallel lanes that each carry their own copy of one fix conflict
          with each other and the train parks all but one. Flags every set of
          >= 2 open PRs whose `git diff -U0` hunks in the same file overlap
          (within DUP_PAD lines) on their POST-image (the `+` lines; the
          pre-image is compared instead only for a pure deletion, which has
          no `+` lines) — two different fixes to the same line have the same
          pre-image but a different post-image, so they no longer group as
          one. An identical (whitespace-normalized) post-image is DUP-FIX
          (RED), names the lowest PR number canonical, and prints "one fix,
          one PR: <others> drop their copy and rebase on #<canonical>"; a
          near-identical one (difflib ratio >= --similarity, default 0.9, but
          not identical) is SIMILAR-FIX, printed for human review and never
          grouped or RED. Read-only.

COOPERATIVE CANCEL AND RECEIPT CARRY
------------------------------------
Every run prints `RUN <id>`. Between stages and inside every backoff wait it polls the state dir (the --state
file's directory) for `<id>.cancel` (release refs, print CANCELLED, exit 0) and `<id>.drop-<pr>` (verify rebuilds
the union without that member; merge HALTs, since the remaining union was never verified). Each file is consumed
once. A PR whose head has pending or missing checks inherits the green of its prior head recorded in --state only
when the raw `git diff --binary` of merge-base..head hashes the same and no completed check on the new head is red
(a base-merge-only move; `CARRIED <old>-><new>`).
The union train gate still always runs.

FLAKY VS DETERMINISTIC
----------------------
A failing --verify-cmd is re-run up to --retries times on the same tree with
exponential backoff (--gate-backoff seconds, default 5, doubling, capped at
300 s: a test re-run needs no long cool-down). A re-run that passes is reported
`FLAKY` and counts as a pass; failing every attempt is deterministic. The
verdict is cached per git tree SHA for the run: an identical tree (a bisect
prefix that equals a rebuilt union) is never tested twice (`CACHED`). A PASS is
also kept across runs and stages in deep-code-review's `gate_cache.py` store
(key: tree, gate set, the verify command; `CACHED ... (gate_cache)`), so a union
tree that pre-commit, pre-push or an earlier train already passed is not
re-tested; a FAIL is never persisted, `PERUN_GATE_CACHE=0` opts out. A failed
`gh pr merge` and every other gh retry use --backoff (default 30, doubling,
capped at 300 s). Parking a member never sleeps.

AUTHORITY AND SAFETY
--------------------
Merging needs the integration owner or a standing grant the owner recorded.
For `merge`, `--apply` requires `--grant <ref>` naming that decision (a link
or record id); this script only checks that it is present and echoes it on
every MERGED line, so it cannot verify that grant. `keystone` checks its
grant's git authorship, which is only as strong as commit metadata: without
signing (--require-signed, with a key the agent cannot use), an author identity
is spoofable by anyone who can write commits locally. Branch protection on the
grants file (owner-only review or push) is the real control; this check
catches mistakes and agent-written grants, not a determined forger. The
script never pushes: any `git push` it is asked to run raises HALT, so it cannot force-push a shared branch. --verify-cmd
runs PR code on this machine, which is why fork PRs are skipped by default.

OUTPUT AND EXIT CODES
---------------------
One line per action (ELIGIBLE, SKIP, PLAN, FAIL, FLAKY, PARK, GREEN, RED,
KEYSTONE, WOULD-MERGE, MERGED, KILL, WOULD-REVERT, REVERT, KEPT, PENDING, UNVERIFIED, WOULD-UPDATE, UPDATED, UPDATE-FAILED, DUP-FIX,
SIMILAR-FIX, WARN, NOOP, HALT, ERROR, DROP-FAILED, RUN, CANCELLED, DROPPED, CARRIED). Untrusted text (check
names, file names, forge errors) is stripped of control characters and
truncated.
  0  plan listed; union green; dry-run printed; members merged; nothing to do;
     a keystone landed even if its post-merge refresh then WARNs
  1  verify found no green union (every member parked); refresh had an update
     fail; dupes found a duplicated fix (a SIMILAR-FIX alone does not)
  2  usage or forge/git error (fail closed; nothing is guessed)
  3  HALT: base moved or rewritten, base red, another writer mid-train, a
     member failed at merge time, a member landed but the new base could
     not be verified, a refused push, or a keystone condition that does
     not hold

USAGE
-----
  merge_train.py plan   --base main [--repo OWNER/NAME] [--min-checks K]
  merge_train.py verify --base main --verify-cmd 'make test'
                        [--count-cmd CMD --cap N --marker-key size-budget-raise]
                        [--retries 2] [--backoff 30] [--gate-backoff 5] [--timeout 3600]
  merge_train.py merge  --base main [--apply --grant REF]
  merge_train.py partial-kill --base main [--apply] [--wait 3600]
  merge_train.py keystone --base main --pr N --verify-cmd CMD --only GLOB
                        [--only GLOB ...] [--owner-email E ...] [--require-signed] [--apply]
                        [--use-update-branch]
  merge_train.py refresh --base main [--since SHA] [--use-update-branch --apply]
  merge_train.py dupes  --base main [--similarity 0.9]
  merge_train.py --selftest
Common: --remote origin, --state PATH (default <git-common-dir>/merge-train.json).
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import date, datetime, timedelta, timezone

sys.dont_write_bytecode = True  # never litter __pycache__ into a checksummed skill tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import partial_pass as pp  # noqa: E402  (PARTIAL-PASS receipts, #1778)
import gh_rest  # noqa: E402  (curl fallback for gh api under the macOS-sandbox TLS failure)
import board_common as bc  # noqa: E402  (validate_repo, run_checks)
import focus_gate as fg  # noqa: E402  (resolve_owners, _owner_problem: the standing-grant owner check)
from refix_gate import load_fix_class_gate  # noqa: E402  (fix_class_gate's glob grammar)

_FCG = load_fix_class_gate()


def _load_gate_cache():
    """deep-code-review's `gate_cache.py` (the tree-keyed PASS cache pre-commit and pre-push share), or None when
    the sibling skill is not installed. Callers treat None as "no cache": the gate just runs."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "deep-code-review", "scripts", "gate_cache.py")
    if not os.path.isfile(path):
        return None
    try:
        spec = importlib.util.spec_from_file_location("gate_cache", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    except Exception:  # a broken cache script must not take the train down: no cache, the gate just runs
        return None
    return module


_GC = _load_gate_cache()

OK, RED, ERROR, HALT = 0, 1, 2, 3
GATE_CONTEXT = "perun/train-gate"
GREEN_CONCLUSIONS = {"success", "neutral", "skipped"}
PR_LIMIT = 200
MAX_BACKOFF = 300
PENDING = {"queued", "in_progress", "pending", "waiting", "requested"}  # a check run that has not completed
MAX_GRANT_DAYS = 30  # a class keystone grant may run at most this long
GRANTS_PATH = ".claude/KEYSTONE-GRANTS"  # the only file keystone grants are read from
TRUST_GIT = ["--no-replace-objects", "-c", "blame.ignoreRevsFile="]  # grant reads: no rewritten history
DUP_PAD = 5  # lines two hunks may sit apart and still be "the same region"
GIT_ID = ["-c", "user.name=merge-train", "-c", "user.email=merge-train@example.invalid"]
RATE_LIMIT_RE = re.compile(r"\b429\b|rate limit", re.I)  # gh's 429 / secondary-rate-limit wording


class Halt(Exception):
    """Stop all automation; a human or a fresh plan must decide what happens next."""


class ForgeError(Exception):
    """A forge or git call failed or returned something unusable; fail closed."""


class Cancelled(Exception):
    """A `<run-id>.cancel` file asked this run to stop; refs are released by run()'s cleanup."""


class Conflict(Exception):
    """A member did not merge cleanly into the union."""

    def __init__(self, member, files):
        super().__init__(member["number"])
        self.member, self.files = member, files


def default_runner(args, cwd=None, timeout=3600):
    """Run a command without a shell; return (returncode, stdout, stderr).

    Side-effects: spawns a subprocess in its OWN process group (new session).
    A missing binary is rc 127 and a timeout rc 124, returned rather than
    raised so callers fail closed uniformly. On timeout the whole group is
    killed, so a grandchild (a browser under a test runner) cannot outlive the
    timebox; only this call's own group is signalled, never anything else.
    """
    try:
        proc = subprocess.Popen(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                                start_new_session=True)
    except FileNotFoundError as exc:
        return 127, "", str(exc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
        proc.communicate()
        return 124, "", f"timed out after {timeout}s: {args[0]}"
    return gh_rest.fallback(args, proc.returncode, out, err)


def pid_alive(pid) -> bool:
    """True unless `pid` is certainly not a running process on this host.

    A process owned by another user (PermissionError) counts as alive, so the
    caller never deletes a live run's refs. Side-effect free (signal 0).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (PermissionError, OverflowError, ValueError):
        return True
    return True


def clean(text, limit=80) -> str:
    """Strip control characters and truncate untrusted text before printing it. Pure."""
    return re.sub(r"[\x00-\x1f\x7f]", "?", str(text))[:limit]


def names(members) -> str:
    """`#1,#2` for a member list (empty string for none). Pure."""
    return ",".join(f"#{m['number']}" for m in members)


class Train:
    """One merge-train invocation: forge/git I/O goes through `runner`, waits through `sleep`."""

    def __init__(self, args, runner, out, sleep):
        self.a, self.runner, self.out = args, runner, out
        self.drops = set()  # PR numbers named by consumed `<run-id>.drop-<pr>` files
        self.sleep = lambda secs: (sleep(secs), self.poll())  # every backoff wait is a cancel point
        self.repo_flag = ["--repo", args.repo] if args.repo else []
        self.base_sha = ""
        self.run_id = f"{os.getpid()}-{uuid.uuid4().hex[:12]}"  # never a per-process counter (#1139)
        self.verdicts = {}  # git tree SHA -> fails() verdict for this run: an identical tree is never re-tested
        self.refs = set()  # refs this run fetched into; dropped when the run ends
        self.state_path = args.state or self._default_state()
        self.state = self._load()
        self.grants_path = GRANTS_PATH

    # ---- plumbing -------------------------------------------------------
    def say(self, line):
        """Print one action line to the output stream."""
        print(line, file=self.out)

    def run(self, argv, cwd=None, ok=True, timeout=None):
        """Run argv through the runner; raise ForgeError on a non-zero rc when ok=True.

        Refuses every `git push` with HALT before the runner sees it: this tool
        never pushes, so it can never force-push a shared branch.
        """
        if argv[:1] == ["git"] and "push" in argv[1:]:
            raise Halt("refusing git push: merge_train never pushes (merges go through the forge API only)")
        rc, out, err = self.runner(argv, cwd=cwd, **({"timeout": timeout} if timeout else {}))
        if ok and rc != 0:
            raise ForgeError(f"{clean(' '.join(argv[:4]))} rc={rc}: {clean(err.strip(), 160)}")
        return rc, out, err

    def _default_state(self):
        """<git-common-dir>/merge-train.json, shared by every worktree of the repository."""
        _, out, _ = self.run(["git", "rev-parse", "--git-common-dir"])
        return os.path.join(os.path.abspath(out.strip()), "merge-train.json")

    def _load(self):
        """Read the state file; a missing file is empty state, an unreadable one fails closed."""
        try:
            with open(self.state_path, encoding="utf-8") as fh:
                return json.load(fh)
        except FileNotFoundError:
            return {}
        except (OSError, ValueError) as exc:
            raise ForgeError(f"unreadable state {self.state_path}: {exc}") from exc

    def save(self):
        """Write the state file atomically (temp file + rename)."""
        tmp = self.state_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.state, fh, indent=1, sort_keys=True)
        os.replace(tmp, self.state_path)

    def poll(self):
        """Consume `<run-id>.cancel` (raise Cancelled) and `<run-id>.drop-<pr>` (add to self.drops) in the state dir."""
        d = os.path.dirname(os.path.abspath(self.state_path))
        try:
            found = os.listdir(d)
        except OSError:
            return
        for f in found:
            m = re.fullmatch(re.escape(self.run_id) + r"\.(cancel|drop-(\d+))", f)
            if not m:
                continue
            try:
                os.remove(os.path.join(d, f))  # consumed once
            except OSError:
                continue
            if m.group(2):
                self.drops.add(int(m.group(2)))
            else:
                raise Cancelled

    def undrop(self, members):
        """Poll, then return `members` minus any dropped PR (one DROPPED line each)."""
        self.poll()
        for m in members:
            if m["number"] in self.drops:
                self.say(f"DROPPED #{m['number']} drop file")
        return [m for m in members if m["number"] not in self.drops]

    def rev(self, ref):
        """Resolve a git ref to its SHA."""
        return self.run(["git", "rev-parse", ref])[1].strip()

    def fetch(self, members=()):
        """Fetch the base and each member's PR head into this run's own refs.

        Returns (base SHA, members still safe to compare). #1139: `git ls-remote`
        is read first, then every ref is fetched with a forced refspec (`+src:dst`)
        into refs/merge-train/<run-id>/, a namespace unique to this run (pid +
        random UUID, never a cycle counter), so a restart never compares against
        a ref an earlier run left behind. A non-zero fetch raises ForgeError (the
        cycle stops, nothing is compared). A fetched ref that disagrees with
        ls-remote was raced: the whole read is retried with --retries/backoff;
        a base still disagreeing then raises ForgeError, while a member still
        disagreeing, or whose fetched head is not the head plan checked, is
        skipped alone (SKIP) so one PR's drift never aborts the cycle.
        """
        if not self.refs:
            self.sweep()
        for m in members:
            if type(m["number"]) is not int:
                raise ForgeError(f"PR number {clean(m['number'])!r} is not an integer; refusing to build a refspec")
        ns = f"refs/merge-train/{self.run_id}"
        base_src, base_dst = f"refs/heads/{self.a.base}", f"{ns}/base"
        src = {m["number"]: f"refs/pull/{m['number']:d}/head" for m in members}
        dst = {n: f"{ns}/pull-{n:d}" for n in src}
        attempts = self.a.retries + 1
        for i in range(attempts):
            if i:
                self.sleep(self.delay(i))
            _, out, _ = self.run(["git", "ls-remote", self.a.remote, base_src, *src.values()])
            remote = {ref: sha for sha, _, ref in (line.partition("\t") for line in out.splitlines())}
            live = [n for n in src if src[n] in remote]  # a vanished PR ref is skipped, not fetched
            self.refs.update([base_dst, *(dst[n] for n in live)])
            self.run(["git", "fetch", "--quiet", "--no-tags", self.a.remote, f"+{base_src}:{base_dst}",
                      *(f"+{src[n]}:{dst[n]}" for n in live)])
            base_sha = self.rev(base_dst)
            got = {n: self.rev(dst[n]) for n in live}
            raced = {n for n in live if got[n] != remote[src[n]]}
            if base_sha == remote.get(base_src) and not raced:
                break
        if base_sha != remote.get(base_src):
            raise ForgeError(f"fetched {base_src} at {base_sha[:7]} but {self.a.remote} has "
                             f"{clean(remote.get(base_src, 'nothing'))[:7]} after {attempts} tries; "
                             "stale or raced fetch, not compared")
        kept = []
        for m in members:
            n = m["number"]
            why = (f"no {src[n]} on {clean(self.a.remote)}" if n not in got
                   else f"stale or raced fetch after {attempts} tries" if n in raced
                   else f"head moved to {got[n][:7]} since plan" if got[n] != m["head"] else "")
            if why:
                self.say(f"SKIP #{n} {why}")
            else:
                kept.append(m)
        return base_sha, kept

    def sweep(self):
        """Delete refs/merge-train/<pid>-*/ namespaces left by crashed runs on this host.

        A namespace is removed only when its pid is not a live process; a live
        run's refs (or an unparseable name) are never touched. A reused pid keeps
        a dead namespace alive one more run, the safe direction.
        """
        out = self.run(["git", "for-each-ref", "--format=%(refname)", "refs/merge-train/"], ok=False)[1]
        for ref in out.split():
            m = re.fullmatch(r"refs/merge-train/(\d+)-[0-9a-f]+/[\w-]+", ref)
            if m and not pid_alive(int(m.group(1))):
                self.run(["git", "update-ref", "-d", ref], ok=False)

    def drop_refs(self):
        """Delete every ref this run fetched into; log DROP-FAILED per failure and never raise.

        Called from run()'s finally, so it must not break run()'s never-raises
        contract; a leftover ref is swept by a later run once this pid is dead.
        """
        for ref in sorted(self.refs):
            try:
                rc, _, err = self.run(["git", "update-ref", "-d", ref], ok=False)
                if rc:
                    self.say(f"DROP-FAILED {ref} rc={rc}: {clean(err.strip(), 120)}")
            except Exception as exc:  # noqa: BLE001 — cleanup must never mask the run's exit code
                self.say(f"DROP-FAILED {ref}: {clean(exc, 120)}")

    def delay(self, attempt, base=None):
        """Backoff before retry `attempt` (1-based): `base` (default --backoff) doubling, capped at MAX_BACKOFF."""
        return min((self.a.backoff if base is None else base) * 2 ** (attempt - 1), MAX_BACKOFF)

    def park(self, member, reason):
        """Exclude `member` at its current head from every later plan, persist it, print PARK."""
        self.state.setdefault("parked", {})[str(member["number"])] = {"head": member["head"], "reason": reason}
        self.save()
        self.say(f"PARK #{member['number']} {reason}")

    # ---- plan -----------------------------------------------------------
    def plan(self):
        """The `plan` subcommand: print eligibility, change nothing."""
        self.eligible()
        return OK

    def eligible(self):
        """Return eligible members [{number, head}] in PR-number order; one line per PR."""
        _, out, _ = self.run(["gh", "pr", "list", *self.repo_flag, "--base", self.a.base, "--state", "open",
                              "--limit", str(PR_LIMIT), "--json", "number,headRefOid,isDraft,mergeable,isCrossRepository"])
        prs = json.loads(out or "[]")
        if len(prs) >= PR_LIMIT:
            raise ForgeError(f"pr list hit the {PR_LIMIT} limit; refusing a truncated plan")
        heads = {str(p["number"]): p["headRefOid"] for p in prs}
        parked = {n: p for n, p in self.state.get("parked", {}).items() if heads.get(n) == p["head"]}
        self.state["parked"] = parked  # a new head is new information: it un-parks
        members, slot = [], None  # slot: the one PARTIAL-PASS member this train may carry (#1778)
        for pr in sorted(prs, key=lambda p: p["number"]):
            rcpt = pp.load(pr["number"], pr["headRefOid"], self.a.partial_dir)
            why = self._ineligible(pr, parked, rcpt["unchecked"] if rcpt else ())
            if not why and rcpt and self.state.get("partial"):  # one OUTSTANDING, not just one per train
                why = f"PARTIAL-PASS #{self.state['partial']['number']} merged and undecided (run partial-kill first)"
            elif not why and rcpt and slot:
                why = f"second PARTIAL-PASS (one per train; #{slot} holds the slot)"
            if why:
                self.say(f"SKIP #{pr['number']} {why}")
            else:
                members.append({"number": pr["number"], "head": pr["headRefOid"], **({"partial": rcpt["unchecked"]} if rcpt else {})})
                slot = slot or (pr["number"] if rcpt else None)
                self.say(f"ELIGIBLE #{pr['number']} {pr['headRefOid'][:7]}"
                         + (f" PARTIAL-PASS unchecked={clean(','.join(rcpt['unchecked']), 120)}" if rcpt else ""))
        self.say(f"PLAN base={self.a.base} members={names(members) or 'none'}")
        return members

    def _ineligible(self, pr, parked, waive=()):
        """'' when `pr` may join the train, else the reason it is skipped. `waive`: checks a PARTIAL-PASS receipt left unchecked."""
        if pr.get("isDraft"):
            return "draft"
        if pr.get("isCrossRepository") and not self.a.allow_forks:
            return "fork (verify would run its code here; --allow-forks)"
        if str(pr["number"]) in parked:
            return f"parked ({parked[str(pr['number'])]['reason']})"
        if pr.get("mergeable") != "MERGEABLE":
            return f"mergeable={clean(pr.get('mergeable'))}"
        passed, bad = self._checks(pr["headRefOid"], waive)
        if bad.rsplit("=", 1)[-1] in PENDING or not (passed or bad):
            passed, bad = self._carry(pr, passed, bad)
        elif not bad and passed >= self.a.min_checks:
            self.state.setdefault("greens", {})[str(pr["number"])] = {"head": pr["headRefOid"], "passed": passed}
        if bad:
            return f"check {bad}"
        return f"checks {passed}<{self.a.min_checks}" if passed < self.a.min_checks else ""

    def _carry(self, pr, passed, bad):
        """(passed, bad) unchanged, or the prior green head's receipt when only the base moved (equal patch-id)."""
        old = self.state.get("greens", {}).get(str(pr["number"]))
        new = pr["headRefOid"]
        if not old or old["head"] == new or any(r.get("status") == "completed" and r.get("conclusion") not in GREEN_CONCLUSIONS
                                                for r in self._latest(new).values()):
            return passed, bad  # a completed red check on the new head is never carried over
        if not self._same_patch(pr["number"], old["head"], new):
            return passed, bad
        self.say(f"CARRIED {old['head'][:7]}->{new[:7]} #{pr['number']}")
        return old["passed"], ""

    def _same_patch(self, number, old, new):
        """True only when the raw `git diff --binary` text of merge-base..head hashes the same for both heads (a patch-id
        would ignore whitespace and hunk position); an empty diff or any git failure is False."""
        ns = f"refs/merge-train/{self.run_id}"
        self.refs.update([f"{ns}/carry-base", f"{ns}/carry-{number}"])
        ids = []
        try:
            self.run(["git", "fetch", "--quiet", "--no-tags", self.a.remote, f"+refs/heads/{self.a.base}:{ns}/carry-base",
                      f"+refs/pull/{number:d}/head:{ns}/carry-{number}"])
            for head in (old, new):
                mb = self.run(["git", "merge-base", head, f"{ns}/carry-base"])[1].strip()
                diff = self.run(["git", "diff", "--binary", f"{mb}..{head}"])[1]
                ids.append(hashlib.sha256(diff.encode("utf-8", "surrogateescape")).hexdigest() if diff else "")
        except ForgeError:
            return False
        return bool(ids[0]) and ids[0] == ids[1]

    def _checks(self, sha, waive=()):
        """(latest-per-name success count, first non-green 'name=state' or ''). Names in `waive` are not judged."""
        latest = self._latest(sha)
        passed = 0
        for name in sorted(latest):
            r = latest[name]
            if name in waive and r.get("status") != "completed":
                continue  # a waived check is skipped only while it is missing or unfinished; one that ran is judged
            if r.get("status") != "completed" or r.get("conclusion") not in GREEN_CONCLUSIONS:
                return passed, clean(f"{name}={r.get('conclusion') or r.get('status')}")
            passed += r.get("conclusion") == "success"
        return passed, ""

    def _latest(self, sha):
        """{check name: its latest run} for `sha`; ForgeError when the list is truncated."""
        repo = self.a.repo or "{owner}/{repo}"
        _, out, _ = self.run(["gh", "api", f"repos/{repo}/commits/{sha}/check-runs?per_page=100"])
        data = json.loads(out)
        runs = data.get("check_runs") or []
        if data.get("total_count", len(runs)) > len(runs):
            raise ForgeError(f"{sha[:7]} has more than {len(runs)} check runs; not verified")
        latest = {}
        for r in runs:
            key = (r.get("started_at") or "", r.get("id") or 0)
            if r["name"] not in latest or key > latest[r["name"]][0]:
                latest[r["name"]] = (key, r)
        return {n: v[1] for n, v in latest.items()}

    # ---- verify ---------------------------------------------------------
    @contextmanager
    def tree(self, start, merges):
        """Throwaway detached worktree at `start` with `merges` merged in order."""
        tmp = tempfile.mkdtemp(prefix="merge-train-")
        wt = os.path.join(tmp, "wt")
        try:
            self.run(["git", "worktree", "add", "--quiet", "--detach", wt, start])
            for m in merges:
                rc, _, err = self.run(["git", *GIT_ID, "merge", "--no-ff", "--no-edit", "-m",
                                       f"merge-train: #{m['number']}", m["head"]], cwd=wt, ok=False)
                if rc:
                    files = self.run(["git", "diff", "--name-only", "--diff-filter=U"], cwd=wt, ok=False)[1].split()
                    self.run(["git", "merge", "--abort"], cwd=wt, ok=False)
                    if not files:
                        raise ForgeError(f"merge of #{m['number']} failed without conflicts: {clean(err.strip(), 160)}")
                    raise Conflict(m, files)
            yield wt
        finally:
            self.run(["git", "worktree", "remove", "--force", wt], ok=False)
            shutil.rmtree(tmp, ignore_errors=True)

    def fails(self, members, label):
        """'' when base+members passes the gate, else 'verify' or 'cap C>N'."""
        with self.tree(self.base_sha, members) as wt:
            sha = self.run(["git", "rev-parse", "HEAD^{tree}"], cwd=wt)[1].strip()
            if sha in self.verdicts:
                self.say(f"CACHED {label} tree {sha[:7]} verdict={self.verdicts[sha] or 'pass'}")
                return self.verdicts[sha]
            ctx = self._pass_cache_key(wt)
            if ctx and _GC.lookup(ctx):  # a PASS from any earlier run or stage (pre-commit, pre-push, a past train)
                self.say(f"CACHED {label} tree {sha[:7]} verdict=pass (gate_cache)")
                self.verdicts[sha] = ""
                return ""
            self.verdicts[sha] = why = self._gate(wt, label)
            if ctx and not why:  # only a PASS is persisted; a FAIL is re-tested every run
                _GC.store(ctx, "train verify", "train")
        return why

    def _pass_cache_key(self, wt):
        """gate_cache key for the union tree checked out in `wt`: None when the cache is absent, opted out
        (PERUN_GATE_CACHE=0) or `wt` is not provably that exact tree. The key text is the verify command, so the
        same command run by another stage shares it; a count/cap gate is part of the verdict, so it joins the text."""
        if _GC is None:
            return None
        text = self.a.verify_cmd + (f"\n# count: {self.a.count_cmd} <= {self.a.cap}" if self.a.count_cmd else "")
        try:
            return _GC.context(text, cwd=wt, rev="HEAD")
        except Exception:  # the cache must never be the reason the gate does not run
            return None

    def _gate(self, wt, label):
        """Run the gate (re-runs on failure) and the cap count once in `wt`: '' or 'verify' or 'cap C>N'."""
        attempts = self.a.retries + 1
        for i in range(attempts):
            if i:
                self.sleep(self.delay(i, self.a.gate_backoff))
            if self.run(["sh", "-c", self.a.verify_cmd], cwd=wt, ok=False, timeout=self.a.timeout)[0] == 0:
                if i:
                    self.say(f"FLAKY {label} passed on attempt {i + 1}/{attempts}")
                break
        else:
            self.say(f"FAIL {label} deterministic ({attempts}/{attempts} attempts)")
            return "verify"
        if self.a.count_cmd:
            count = self.count(wt)
            if count > self.a.cap:
                self.say(f"FAIL {label} cap {count}>{self.a.cap}")
                return f"cap {count}>{self.a.cap}"
        return ""

    def count(self, wt):
        """Run --count-cmd in `wt`; it must print exactly one integer (else fail closed)."""
        out = self.run(["sh", "-c", self.a.count_cmd], cwd=wt, timeout=self.a.timeout)[1].strip()
        if not re.fullmatch(r"-?\d+", out):
            raise ForgeError(f"--count-cmd must print one integer, got {clean(out)!r}")
        return int(out)

    def attribute(self, members):
        """#1106: `#N +D marker=...` per member; return [(member, reason)] with D > 0 and no marker."""
        guilty = []
        key = re.compile(rf"^{re.escape(self.a.marker_key)}:[ \t]*\S", re.M)
        for m in members:
            mb = self.run(["git", "merge-base", m["head"], self.base_sha])[1].strip()
            counts = []
            for sha in (m["head"], mb):
                with self.tree(sha, []) as wt:
                    counts.append(self.count(wt))
            delta = counts[0] - counts[1]
            marked = bool(key.search(self.run(["git", "log", "--format=%B", f"{mb}..{m['head']}"])[1]))
            self.say(f"#{m['number']} {delta:+d} marker={'present' if marked else 'none'}")
            if delta > 0 and not marked:
                guilty.append((m, f"ratchet {delta:+d} marker=none"))
        return guilty

    def bisect(self, members):
        """#1119 prefix bisection: the member whose inclusion first breaks the gate."""
        if self.fails([], "base"):
            raise Halt(f"base {self.base_sha[:7]} fails the gate on its own; no member is isolable (discharge a red base first)")
        lo, hi = 0, len(members)  # invariant: prefix lo passes, prefix hi fails
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.fails(members[:mid], f"prefix {names(members[:mid])}"):
                hi = mid
            else:
                lo = mid
        return members[hi - 1], f"breaks gate after {names(members[:hi - 1]) or 'base'}"

    def verify(self):
        """The `verify` subcommand: find the largest green union, parking culprits; record it."""
        members = self.eligible()
        self.base_sha, members = self.fetch(members)
        members = self.screen(members)  # a recorded, unlanded keystone parks its copies (#1142)
        parked_any = False
        while (members := self.undrop(members)):
            try:
                why = self.fails(members, f"union {names(members)}")
            except Conflict as c:
                self.park(c.member, "conflict " + ",".join(clean(f, 60) for f in c.files[:5]))
                members, parked_any = [m for m in members if m is not c.member], True
                continue  # #1134: rebuild at once, never a sleep per conflict
            kept = self.undrop(members)
            if len(kept) != len(members):  # dropped while the gate ran: re-plan the smaller union
                members = kept
                continue
            if not why:
                self.state.update(base=self.a.base, base_sha=self.base_sha, members=members)
                self.save()
                self.say(f"GREEN base={self.base_sha[:7]} members={names(members)}")
                return OK
            guilty = self.attribute(members) if why.startswith("cap") else []
            for m, reason in guilty or [self.bisect(members)]:
                self.park(m, reason)
                members, parked_any = [x for x in members if x is not m], True
        self.state.update(base=self.a.base, base_sha=self.base_sha, members=[])
        self.save()
        self.say("RED no green union: every member parked" if parked_any else "NOOP no eligible members")
        return RED if parked_any else OK

    def post_status(self, m, state):
        """Post commit status `perun/train-gate` (success|error) on member `m`'s head; True only when the post succeeded.

        Called only from the apply merge path, right before that member's merge, so the vouch is never stale. A failed
        post is a WARN (never raised, never claimed posted); --no-status skips it.
        """
        if self.a.no_status:
            return False
        repo = self.a.repo or "{owner}/{repo}"
        body = json.dumps({"state": state, "context": GATE_CONTEXT,
                           "description": f"train: {state} for union on {self.a.base}@{self.state['base_sha'][:7]}"})
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write(body)
        try:
            rc, _, err = self.run(["gh", "api", "-X", "POST", f"repos/{repo}/statuses/{m['head']}", "--input", fh.name], ok=False)
        finally:
            os.unlink(fh.name)
        if rc == 0:
            self.say(f"STATUS posted {GATE_CONTEXT}={state} on #{m['number']} {m['head'][:7]}")
            return True
        self.say(f"WARN {GATE_CONTEXT}={state} NOT posted on #{m['number']} {m['head'][:7]} ({clean(err.strip(), 120)}); "
                 "a base that requires it will block this merge")
        return False

    # ---- merge ----------------------------------------------------------
    def same_base(self, proved, current):
        """HALT unless `current` is the base SHA the union was proved on (#1137)."""
        if current == proved:
            return
        rc = self.run(["git", "merge-base", "--is-ancestor", proved, current], ok=False)[0]
        if rc == 0:
            raise Halt(f"base {self.a.base} moved {proved[:7]}->{current[:7]} since verify; re-plan "
                       "(never re-verify silently on a changed base)")
        if rc == 1:
            raise Halt(f"base {self.a.base} rewritten: {proved[:7]} is not an ancestor of {current[:7]} "
                       "(non-fast-forward, possible history rewrite); a human must clear this")
        raise ForgeError(f"cannot compare {proved[:7]} with {current[:7]} (rc={rc})")

    def still_ready(self, m):
        """'' when the PR is OPEN, at the recorded head, and MERGEABLE (UNKNOWN polled), else why not."""
        attempts = self.a.retries + 1
        for i in range(attempts):
            if i:
                self.sleep(self.delay(i))
            pr = json.loads(self.run(["gh", "pr", "view", str(m["number"]), *self.repo_flag,
                                      "--json", "state,headRefOid,mergeable"])[1])
            if pr.get("state") != "OPEN":
                return f"state={clean(pr.get('state'))}"
            if pr.get("headRefOid") != m["head"]:
                return f"head moved to {clean(pr.get('headRefOid'))[:7]}"
            if pr.get("mergeable") == "MERGEABLE":
                return ""
            if pr.get("mergeable") != "UNKNOWN":
                return f"mergeable={clean(pr.get('mergeable'))}"
        return f"mergeable=UNKNOWN after {attempts} polls"

    def merge_one(self, m, body=""):
        """Merge one member at its recorded head with bounded retries; '' on success, else why not.

        `body`, when given, becomes the merge commit's message body (the keystone grant trailer).
        """
        attempts, err = self.a.retries + 1, ""
        for i in range(attempts):
            if i:
                self.sleep(self.delay(i))
            self.poll()  # last cancel point before the irreversible call
            rc, _, err = self.run(["gh", "pr", "merge", str(m["number"]), *self.repo_flag, "--merge",
                                   "--match-head-commit", m["head"], *(["--body", body] if body else [])],
                                  ok=False)
            if rc == 0:
                if i:
                    self.say(f"FLAKY merge #{m['number']} landed on attempt {i + 1}/{attempts}")
                return ""
        return f"merge failed {attempts}x: {clean(err.strip().splitlines()[-1] if err.strip() else 'no stderr')}"

    def merge(self):
        """The `merge` subcommand: dry-run by default; with --apply land members back-to-back."""
        members = self.state.get("members") or []
        if self.state.get("base") != self.a.base or not self.state.get("base_sha"):
            raise ForgeError(f"no verified union for base {self.a.base} in {self.state_path}; run verify")
        if not members:
            self.say("NOOP nothing verified to merge")
            return OK
        held = [m["number"] for m in members if m.get("partial")]  # re-check (#1778): never trust the recorded plan
        if len(held) > 1 or (held and self.state.get("partial")):
            raise Halt(f"PARTIAL-PASS {names([m for m in members if m.get('partial')])} would be a second outstanding one"
                       + (f" (#{self.state['partial']['number']} undecided: run partial-kill)" if self.state.get("partial") else "")
                       + "; re-plan and re-verify")
        prev = self.fetch()[0]
        self.same_base(self.state["base_sha"], prev)
        self.poll()
        if not self.a.apply:
            for m in members:
                self.say(f"WOULD-MERGE #{m['number']} {m['head'][:7]} onto {self.a.base}@{prev[:7]}")
            self.say("DRY-RUN nothing merged; --apply --grant REF merges (integration owner or recorded standing grant)")
            return OK
        for i, m in enumerate(members):
            self.poll()
            if any(x["number"] in self.drops for x in members[i:]):
                self.state["members"] = []
                self.save()
                raise Halt(f"drop requested for {names([x for x in members[i:] if x['number'] in self.drops])}; "
                           "the remaining union was never verified: re-plan and re-verify")
            why = self.still_ready(m)
            posted = not why and self.post_status(m, "success")
            try:
                why = why or self.merge_one(m)
            except BaseException:  # interrupted or crashed between vouch and merge: never leave success on an unmerged head
                if posted:
                    self.post_status(m, "error") or self.post_status(m, "error")
                raise
            if why:
                if posted:  # overwrite the vouch: this head did not land (one retry; a failed post is a loud WARN)
                    self.post_status(m, "error") or self.post_status(m, "error")
                self.park(m, why)
                self.state["members"] = []
                self.save()
                raise Halt(f"#{m['number']} not merged ({why}); {names(members[i + 1:]) or 'no members'} "
                           "left unmerged: re-plan and re-verify")
            try:
                new = self.fetch()[0]
            except ForgeError as exc:  # the PR already landed: never leave it listed as unmerged
                self.say(f"MERGED #{m['number']} {m['head'][:7]} -> {self.a.base}@unverified grant={clean(self.a.grant)}")
                self.state["members"] = []
                self.save()
                raise Halt(f"#{m['number']} landed; base unverified ({exc}); "
                           f"{names(members[i + 1:]) or 'no members'} left unmerged: re-plan and re-verify") from exc
            except Cancelled:  # cancelled after the PR landed: record it, keep the rest, then stop
                self.say(f"MERGED #{m['number']} {m['head'][:7]} -> {self.a.base}@unverified grant={clean(self.a.grant)}")
                self.state["members"] = members[i + 1:]
                self.save()
                raise
            parents = self.run(["git", "rev-list", "--parents", "-n", "1", new])[1].split()[1:]
            if parents != [prev, m["head"]]:
                self.state["members"] = []
                self.save()
                raise Halt(f"base moved by another writer while merging #{m['number']} ({new[:7]} is not "
                           f"{prev[:7]}+#{m['number']}); {names(members[i + 1:]) or 'no members'} left unmerged")
            self.state.update(base_sha=new, members=members[i + 1:])
            if m.get("partial"):  # kill criterion (#1778): `partial-kill` reads this record
                self.state["partial"] = {"number": m["number"], "merge_sha": new, "unchecked": m["partial"],
                                         "merged_at": time.time()}
            self.save()
            self.say(f"MERGED #{m['number']} {m['head'][:7]} -> {self.a.base}@{new[:7]} grant={clean(self.a.grant)}"
                     + (f" PARTIAL-PASS unchecked={clean(','.join(m['partial']), 120)} kill={pp.KILL}" if m.get("partial") else ""))
            prev = new
        return OK

    def partial_kill(self):
        """The `partial-kill` subcommand: once a merged PARTIAL-PASS PR's unchecked checks have run on its merge commit,
        revert it if any failed (RED, GraphQL revertPullRequest opens the revert PR), keep it if all passed, else PENDING.
        Dry-run by default; --apply opens the revert PR. Clears the record once decided."""
        rec = self.state.get("partial")
        if not rec:
            self.say("NOOP no merged PARTIAL-PASS PR recorded")
            return OK
        n, latest = rec["number"], self._latest(rec["merge_sha"])
        runs = [latest.get(u) for u in rec["unchecked"]]
        bad = [f"{u}={r.get('conclusion') or r.get('status')}" for u, r in zip(rec["unchecked"], runs)
               if r and r.get("status") == "completed" and r.get("conclusion") not in GREEN_CONCLUSIONS]
        if not bad:
            on = f"on {rec['merge_sha'][:7]}"
            running = [u for u, r in zip(rec["unchecked"], runs) if r and r.get("status") != "completed"]
            # absent: still pending while CI may yet report it (no runs yet, or some still running) and the wait is
            # not up; once CI finished without it, or --wait expired, it never ran
            late = time.time() - rec.get("merged_at", 0) > self.a.wait
            ci_done = bool(latest) and all(r.get("status") == "completed" for r in latest.values())
            absent = [u for u, r in zip(rec["unchecked"], runs) if not r]
            waiting = running or (absent and not (ci_done or late))
            if waiting:
                self.say(f"PENDING #{n} unchecked checks not all finished {on}: {clean(', '.join(running or absent), 160)}")
                return OK
            # a skipped or neutral conclusion is green for admission but proves nothing here: never KEPT
            unproven = absent + [u for u, r in zip(rec["unchecked"], runs) if r and r.get("conclusion") != "success"]
            if unproven:
                self.say(f"UNVERIFIED #{n} not KEPT: {clean(', '.join(unproven), 160)} never ran or did not succeed {on}; "
                         f"decide by hand, then remove 'partial' from {self.state_path}")
                return RED
            self.state.pop("partial")
            self.save()
            self.say(f"KEPT #{n} unchecked checks passed {on}")
            return OK
        self.say(f"KILL #{n} unchecked check failed after merge: {clean(', '.join(bad), 160)}")
        if not self.a.apply:
            self.say(f"WOULD-REVERT #{n}; --apply opens the revert PR")
            return RED
        _, node, _ = self.run(["gh", "pr", "view", str(n), *self.repo_flag, "--json", "id", "--jq", ".id"])
        _, url, _ = self.run(["gh", "api", "graphql", "-f", "id=" + node.strip(), "-f", "query=mutation($id:ID!){revertPullRequest("
                              "input:{pullRequestId:$id}){revertPullRequest{url}}}", "--jq", ".data.revertPullRequest.revertPullRequest.url"])
        self.state.pop("partial")
        self.save()
        self.say(f"REVERT #{n} revert PR opened {clean(url.strip())}")
        return RED

    # ---- keystone -------------------------------------------------------
    def patch_ids(self, head):
        """Stable patch-ids of the non-merge commits in base..head (identical diffs share one id)."""
        # No bare pipe: a failed `git log` must fail the call, not feed patch-id nothing.
        script = 'log=$(git log -p --no-color --no-merges "$1") || exit 1; printf "%s\\n" "$log" | git patch-id --stable'
        out = self.run(["sh", "-c", script, "patch-id", f"{self.base_sha}..{head}"])[1]
        return {line.split()[0] for line in out.splitlines() if line.strip()}

    def changed(self, base, head):
        """Files changed in base...head, renames split into delete + add so a moved-in file shows its source."""
        return self.run(["git", "diff", "--name-only", "--no-renames", f"{base}...{head}"])[1].splitlines()

    def diff_patch(self, base, head):
        """The base...head diff as an applicable patch (renames split, binary hunks included)."""
        return self.run(["git", "diff", "--no-renames", "--binary", f"{base}...{head}"])[1]

    def contains(self, patch, tree):
        """True when `patch` reverse-applies to commit `tree` (the change is already in it); False when not.

        Uses a throwaway index, never the working tree. A setup failure raises ForgeError.
        """
        script = ('d=$(mktemp -d "${TMPDIR:-/tmp}/merge-train.XXXXXX") || exit 3; trap \'rm -rf "$d"\' EXIT; '
                  'GIT_INDEX_FILE="$d/index" git read-tree "$1" || exit 3; '
                  'GIT_INDEX_FILE="$d/index" git apply --cached --check -R "$2" 2>/dev/null')
        fd, path = tempfile.mkstemp(prefix="keystone-", suffix=".patch")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(patch)
            rc = self.run(["sh", "-c", script, "keystone-contains", tree, path], ok=False)[0]
        finally:
            os.remove(path)
        if rc not in (0, 1):
            raise ForgeError(f"cannot test {tree[:7]} for the keystone change (rc={rc})")
        return rc == 0

    def carries(self, rec, head):
        """'' when `head` holds no copy of keystone `rec`, else the park reason.

        A shared patch-id is a cherry-pick; a keystone diff that reverse-applies
        to the sibling's tree is a squashed or amended copy; any other edit to a
        keystone file may be a partial copy and waits for the keystone as well.
        """
        n = rec["pr"]
        if set(rec["patch_ids"]) & self.patch_ids(head):
            return f"carries a cherry-pick of keystone #{n}; rebase onto the base after it lands"
        touched = sorted(set(self.changed(self.base_sha, head)) & set(rec["files"]))
        if not touched:
            return ""
        if self.contains(rec["patch"], head):
            return f"carries a copy of keystone #{n}; drop it and rebase after it lands"
        return f"touches keystone #{n} file {clean(touched[0], 60)} (possible partial copy); rebase after it lands"

    def screen(self, members):
        """Park members carrying a copy of the recorded keystone until that keystone lands.

        Re-run on every verify, so a sibling that re-pushes (a new head un-parks
        it) is checked again. The record clears once the keystone has landed by
        any route: its head is an ancestor of the base, its PR is MERGED, or the
        base itself contains the keystone change (a squash or a hand-applied fix).
        """
        rec = self.state.get("keystone")
        if not rec:
            return members
        landed = (self.run(["git", "merge-base", "--is-ancestor", rec["head"], self.base_sha], ok=False)[0] == 0
                  or json.loads(self.run(["gh", "pr", "view", str(rec["pr"]), *self.repo_flag,
                                          "--json", "state"])[1]).get("state") == "MERGED"
                  or self.contains(rec["patch"], self.base_sha))
        if landed:
            self.state.pop("keystone")
            self.save()
            self.say(f"KEYSTONE #{rec['pr']} landed on {self.a.base}; sibling screen cleared")
            return members
        kept = []
        for m in members:
            why = m["number"] != rec["pr"] and self.carries(rec, m["head"])
            if why:
                self.park(m, why)
            else:
                kept.append(m)
        return kept

    def tgit(self, args, ok=True):
        """Run a trust-bearing git read: no replace refs, no blame ignore-revs file (as lane_guard does)."""
        return self.run(["git", *TRUST_GIT, *args], ok=ok)

    def git_fn(self):
        """A focus_gate GitRunner over `tgit` (raises focus_gate.GitError on failure)."""
        def call(args):
            rc, out, err = self.tgit(args, ok=False)
            if rc:
                raise fg.GitError(clean(err.strip(), 160) or f"git {args[0]} rc={rc}")
            return out
        return call

    def _line_owner(self, path, line, owners):
        """(blamed commit sha, problem) for line `line` of `path` at the base; problem '' when owner-authored."""
        blame = self.tgit(["blame", "--porcelain", "-L", f"{line},{line}", self.base_sha, "--", path])[1]
        sha = blame.split(" ", 1)[0]
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            return sha, f"cannot attribute {clean(path)}:{line}"
        try:
            return sha, fg._owner_problem(self.git_fn(), sha, owners, getattr(self.a, "require_signed", False))
        except fg.GitError as exc:
            return sha, f"cannot read {sha[:7]}: {exc}"

    def _class_problem(self, cls, sha):
        """'' when a class grant's expiry is set, not past, and at most MAX_GRANT_DAYS after its commit."""
        if not cls.get("expires"):
            return "class grant needs expires=YYYY-MM-DD"
        try:
            expires = date.fromisoformat(cls["expires"])
        except ValueError:
            return f"bad expires={clean(cls['expires'])}"
        if datetime.now(timezone.utc).date() > expires:
            return f"class grant expired on {expires}"
        stamp = self.tgit(["show", "-s", "--format=%cI", sha])[1].strip()[:10]
        try:
            made = date.fromisoformat(stamp)
        except ValueError:
            return f"cannot date {sha[:7]}"
        if (expires - made).days > MAX_GRANT_DAYS:
            return f"class grant runs more than {MAX_GRANT_DAYS} days ({made} to {expires})"
        return ""

    @staticmethod
    def parse_class(body):
        """(limits dict, problem) for `<glob> ... | expires=YYYY-MM-DD | max-files=N`. Pure."""
        parts = [p.strip() for p in body.split("|")]
        globs = [g for g in re.split(r"[\s,]+", parts[0]) if g]
        opts = dict(p.split("=", 1) for p in parts[1:] if "=" in p)
        if not globs:
            return None, "class limits name no globs"
        bad = next((glob_problem(g) for g in globs if glob_problem(g)), "")
        if bad:
            return None, bad
        if not re.fullmatch(r"[1-9]\d*", opts.get("max-files", "").strip()):
            return None, "class grant needs max-files=N (N >= 1)"
        return {"globs": globs, "max_files": int(opts["max-files"]), "expires": opts.get("expires", "").strip()}, ""

    def _candidate(self, path, line, row, rest, named, owners, head, files):
        """(problem, grant) for one grant line; grant = {"key", "kind", "desc"} when it authorises this keystone."""
        pin = re.fullmatch(r"@([0-9a-f]{7,40})", rest) if named else None
        limits = None
        if pin:
            if not head.startswith(pin.group(1)):
                return f"pinned to {pin.group(1)[:12]}, not head {head[:12]}", None
        elif named and not rest.startswith("|"):
            return "a named grant must pin @<sha> or carry class limits (| <globs> | expires= | max-files=)", None
        else:
            limits, why = self.parse_class(rest.lstrip("|").strip())
            if why:
                return why, None
        sha, why = self._line_owner(path, line, owners)
        if not why and limits:
            why = self._class_problem(limits, sha)
        if not why and limits:
            stray = [f for f in files if not glob_match(f, limits["globs"])]
            why = (f"{clean(stray[0])} outside the grant's globs" if stray else
                   f"{len(files)} files > max-files={limits['max_files']}" if len(files) > limits["max_files"] else "")
        if why:
            return why, None
        key = f"{sha}:{hashlib.sha256(row.strip().encode()).hexdigest()[:16]}"
        spent = self.tgit(["log", self.base_sha, "-F", f"--grep=Keystone-Grant: {key}", "--format=%H", "-n", "1"])[1]
        if spent.strip():
            return f"grant already used by merge {spent.strip()[:7]}; the owner must commit it again", None
        kind = "class" if limits and not named else "named"
        desc = (f"expires={limits['expires']} globs={','.join(limits['globs'])}" if limits else f"pin={pin.group(1)}")
        return "", {"key": key, "kind": kind, "desc": desc}

    def grant(self, n, owners, head, files):
        """('', grant) when the pinned grants file on the fetched base authorises keystone #n at `head`.

        Lines of GRANTS_PATH (never an agent-chosen path), each blamed to an
        owner email with no Co-authored-by trailer (focus_gate's check):
          keystone: #<n> @<sha>                                pins this PR's head
          keystone: #<n> | <globs> | expires=D | max-files=N   this PR, within limits
          keystone-class: <globs> | expires=D | max-files=N    one keystone of this shape
        Limits need an unexpired date at most MAX_GRANT_DAYS after the line's
        commit, globs with a literal directory prefix covering every changed
        file, and at most N files. Every grant is single-use: it is spent by
        the `Keystone-Grant: <commit>:<line-key>` trailer `--apply` writes into
        the merge commit, and a grant whose trailer is already in the base's
        history is refused until the owner commits the line again. Candidates
        for this PR are tried before classes; the first that passes wins, so a
        spent or non-covering class never blocks a usable one. Read-only.
        """
        if not owners:
            return "no owner identity (--owner-email, DCR_OWNER_EMAIL, or git config dcr.owner)", None
        path = self.grants_path
        rc, text, _ = self.tgit(["show", f"{self.base_sha}:{path}"], ok=False)
        if rc:
            return f"{clean(path)} is not committed on {self.a.base}@{self.base_sha[:7]}", None
        rows = text.splitlines()
        named = re.compile(rf"^\s*[-*]?\s*keystone:\s*#?{int(n)}(?!\d)\s*(.*)$", re.I)
        klass = re.compile(r"^\s*[-*]?\s*keystone-class:\s*(.*)$", re.I)
        cands = [(i, row, m.group(1).strip(), True) for i, row in enumerate(rows, 1) if (m := named.match(row))]
        cands += [(i, row, m.group(1).strip(), False) for i, row in enumerate(rows, 1) if (m := klass.match(row))]
        problems = []
        for i, row, rest, is_named in cands:
            why, found = self._candidate(path, i, row, rest, is_named, owners, head, files)
            if found:
                return "", found
            problems.append(f"{clean(path)}:{i}: {why}")
        return (problems[0] if problems else f"{clean(path)} has no 'keystone: #{n}' or 'keystone-class:' line"), None

    def keystone(self):
        """The `keystone` subcommand: prove the owner's pre-ratified red-base exception for one PR.

        Proves, in order: the PR is an open PR into --base that passes plan's own
        eligibility (non-draft, same-repo, MERGEABLE, checks green); every
        changed file matches --only; the pinned grants file authorises it
        (`grant`); the base fails --verify-cmd on its own (after retries, so a
        flake is not a red base); base + PR passes it. Then records the
        keystone for `verify` to screen against and parks every sibling that
        carries a copy (`carries`). A dry run spends nothing. With --apply it
        merges the keystone alone, writing the grant's trailer into the merge
        commit (which spends it), clears any recorded union, then runs
        `refresh` for the siblings. The merge has already landed by then, so
        a `refresh` failure is caught and printed as WARN, never raised: it
        must not turn a landed merge into an ERROR/HALT exit.
        """
        n = self.a.pr
        pr = json.loads(self.run(["gh", "pr", "view", str(n), *self.repo_flag, "--json",
                                  "state,headRefOid,mergeable,isDraft,isCrossRepository,baseRefName"])[1])
        why = ("state=" + clean(pr.get("state")) if pr.get("state") != "OPEN" else
               f"targets {clean(pr.get('baseRefName'))}, not {self.a.base}"
               if pr.get("baseRefName") != self.a.base else self._ineligible({**pr, "number": n}, {}))
        if why:
            raise Halt(f"keystone #{n} refused: {why}")
        k = {"number": n, "head": pr["headRefOid"]}
        siblings = [m for m in self.open_prs() if m["number"] != n]
        self.base_sha, kept = self.fetch([k, *siblings])
        if k not in kept:
            raise Halt(f"keystone #{n} refused: its head could not be fetched as planned")
        siblings = [s for s in kept if s is not k]
        files = self.changed(self.base_sha, k["head"])
        stray = [f for f in files if not glob_match(f, self.a.only)]
        if not files or stray:
            raise Halt(f"keystone #{n} refused: " + (f"{clean(stray[0])} outside --only" if stray else "empty diff"))
        owners, warning = fg.resolve_owners(self.a.owner_email, self.git_fn())
        if warning:
            self.say(f"WARN {warning}")
        why, grant = self.grant(n, owners, k["head"], files)
        if why:
            raise Halt(f"keystone #{n} refused: grant {why}")
        self.say(f"GRANT {grant['kind']} {grant['key'][:7]} {grant['desc']}")
        if not self.fails([], "base"):
            raise Halt(f"keystone #{n} refused: base {self.base_sha[:7]} is green; no exception needed, "
                       "use the normal merge path")
        try:
            still_red = self.fails([k], f"keystone #{n}")
        except Conflict as c:
            raise Halt(f"keystone #{n} conflicts with the base ({clean(c.files[0], 60)}); rebase it") from c
        if still_red:
            raise Halt(f"keystone #{n} does not green the base in a union run; not a keystone")
        self.say(f"KEYSTONE #{n} base={self.base_sha[:7]} red alone, green with #{n}; files={len(files)}")
        rec = {"pr": n, "head": k["head"], "files": files, "patch_ids": sorted(self.patch_ids(k["head"])),
               "patch": self.diff_patch(self.base_sha, k["head"])}
        self.state["keystone"] = rec
        self.save()
        for s in siblings:
            why = self.carries(rec, s["head"])
            if why:
                self.park(s, why)
        if not self.a.apply:
            self.say(f"WOULD-MERGE #{n} {k['head'][:7]} alone onto {self.a.base}@{self.base_sha[:7]}")
            self.say("DRY-RUN nothing merged, grant not spent; --apply merges the keystone alone")
            return OK
        prev = self.fetch()[0]
        self.same_base(self.base_sha, prev)
        why = self.still_ready(k) or self.merge_one(k, body=f"Keystone-Grant: {grant['key']}")
        if why:
            raise Halt(f"keystone #{n} not merged ({why})")
        self.state["members"] = []  # the base is about to move: any recorded union is void
        self.save()
        try:
            new = self.fetch()[0]
        except ForgeError as exc:  # the keystone already landed: say so, then stop
            self.say(f"MERGED #{n} {k['head'][:7]} -> {self.a.base}@unverified grant={grant['key'][:7]}")
            raise Halt(f"keystone #{n} landed; base unverified ({exc}); siblings re-plan") from exc
        if self.run(["git", "rev-list", "--parents", "-n", "1", new])[1].split()[1:] != [prev, k["head"]]:
            raise Halt(f"base moved by another writer while merging keystone #{n}")
        self.state.update(base=self.a.base, base_sha=new, members=[])  # siblings re-plan on the new base
        self.state.pop("keystone", None)
        self.save()
        self.say(f"MERGED #{n} {k['head'][:7]} -> {self.a.base}@{new[:7]} grant={grant['key'][:7]}")
        try:
            self.refresh()
        except ForgeError as exc:  # the merge already landed; a refresh error must not look like a failed merge
            self.say(f"WARN keystone #{n} landed but refresh failed ({clean(exc, 200)}); run refresh separately")
        return OK

    # ---- refresh / dupes --------------------------------------------------
    def open_prs(self):
        """Open PRs into --base as [{number, head, isDraft, isCrossRepository}], PR-number order.

        A truncated list fails closed.
        """
        _, out, _ = self.run(["gh", "pr", "list", *self.repo_flag, "--base", self.a.base, "--state", "open",
                              "--limit", str(PR_LIMIT), "--json", "number,headRefOid,isDraft,isCrossRepository"])
        rows = json.loads(out or "[]")
        if len(rows) >= PR_LIMIT:
            raise ForgeError(f"pr list hit the {PR_LIMIT} limit; refusing a truncated scan")
        return sorted(({"number": r["number"], "head": r["headRefOid"], "isDraft": r["isDraft"],
                        "isCrossRepository": r["isCrossRepository"]} for r in rows), key=lambda m: m["number"])

    def refresh(self):
        """The `refresh` subcommand (also keystone --apply's last step): update PRs behind a landed fix.

        A CI re-run reuses the PR's old merge commit, so a PR stays red after the
        fix lands until its branch is updated. Cost default: for each open PR
        whose head lacks --since (default: the fetched base head) it prints the
        local `gh pr checkout` + fetch + merge + push commands, for the
        branch's own owner to run on their next push (spends zero extra CI
        runs). Pass
        --use-update-branch to instead print/run one `gh pr update-branch` per
        PR (--apply runs them, a merge commit each, never --rebase) — each call
        costs one CI run, so this is opt-in. A draft PR is skipped
        (--include-drafts admits it) and a fork PR is skipped
        (--allow-forks admits it) — update-branch would run on a PR this
        script never otherwise touches. The keystone screen runs first, and a
        PR parked for a keystone is skipped: it must drop its copy of the fix,
        not merge the fix in twice. Applied update-branch calls are spaced
        --backoff apart (gh secondary-rate-limits a burst); a
        429/secondary-rate-limit response is retried on the --retries/--backoff
        schedule, any other failure is not. Returns RED when any
        --use-update-branch update failed (every other PR is still tried),
        else OK.
        """
        self.base_sha, members = self.fetch(self.open_prs())
        fix = getattr(self.a, "since", "") or self.base_sha
        if self.run(["git", "merge-base", "--is-ancestor", fix, self.base_sha], ok=False)[0]:
            raise ForgeError(f"--since {clean(fix)} is not on {self.a.base}@{self.base_sha[:7]}")
        parked = self.state.get("parked", {})
        failed = behind = applied = 0
        for m in self.screen(members):
            n, why = m["number"], parked.get(str(m["number"]), {})
            if why.get("head") == m["head"] and "keystone #" in why.get("reason", ""):
                self.say(f"SKIP #{n} {clean(why['reason'], 120)}")
                continue
            if m.get("isDraft") and not getattr(self.a, "include_drafts", False):
                self.say(f"SKIP #{n} draft (--include-drafts admits it)")
                continue
            if m.get("isCrossRepository") and not self.a.allow_forks:
                self.say(f"SKIP #{n} fork (--allow-forks admits it)")
                continue
            rc = self.run(["git", "merge-base", "--is-ancestor", fix, m["head"]], ok=False)[0]
            if rc not in (0, 1):
                raise ForgeError(f"cannot tell whether #{n} contains {fix[:7]} (rc={rc})")
            if rc == 0:
                self.say(f"SKIP #{n} already contains {self.a.base}@{fix[:7]}")
                continue
            behind += 1
            if not getattr(self.a, "use_update_branch", False):
                checkout = " ".join(["gh", "pr", "checkout", str(n), *self.repo_flag])
                self.say(f"LOCAL #{n} behind {self.a.base}@{fix[:7]}: {checkout} && "
                         f"git fetch {self.a.remote} {self.a.base} && "
                         f"git merge {self.a.remote}/{self.a.base} && git push  "
                         "(run this on your own next push; --use-update-branch costs one CI run per PR instead)")
                continue
            cmd = ["gh", "pr", "update-branch", str(n), *self.repo_flag]
            if not self.a.apply:
                self.say(f"WOULD-UPDATE #{n} behind {self.a.base}@{fix[:7]}: {' '.join(cmd)}")
                continue
            if applied:
                self.sleep(self.a.backoff)  # throttle between calls, not just between retries
            applied += 1
            attempts = self.a.retries + 1
            for i in range(attempts):
                if i:
                    self.sleep(self.delay(i))
                rc, _, err = self.run(cmd, ok=False)
                if rc == 0 or not RATE_LIMIT_RE.search(err):
                    break
            failed += bool(rc)
            self.say(f"UPDATE-FAILED #{n} rc={rc}: {clean(err.strip(), 160)}" if rc
                     else f"UPDATED #{n} merged {self.a.base}@{fix[:7]} in; CI now tests a new merge commit")
        if not behind:
            self.say(f"NOOP no open PR is behind {self.a.base}@{fix[:7]}")
        elif not getattr(self.a, "use_update_branch", False):
            self.say("LOCAL each PR owner runs the printed commands on their own next push; "
                     "--use-update-branch opts into gh pr update-branch (one CI run per PR)")
        elif not self.a.apply:
            self.say("DRY-RUN nothing updated; --apply runs each gh pr update-branch (a re-run would reuse the old merge)")
        return RED if failed else OK

    def dupes(self):
        """The `dupes` subcommand: flag one fix carried by several open PRs. Read-only; RED on any DUP-FIX
        (a SIMILAR-FIX is printed for review but never RED by itself)."""
        self.base_sha, members = self.fetch(self.open_prs())
        diffs = {m["number"]: self.run(["git", "diff", "-U0", "--no-renames", "--no-color",
                                        f"{self.base_sha}...{m['head']}"])[1] for m in members}
        groups, similars = duplicate_fixes(diffs, self.a.similarity)
        for prs, paths in groups:
            others = ",".join(f"#{n}" for n in prs[1:])
            self.say(f"DUP-FIX {','.join(f'#{n}' for n in prs)} canonical=#{prs[0]} "
                     f"files={','.join(clean(p, 80) for p in paths)}")
            self.say(f"one fix, one PR: {others} drop their copy and rebase on #{prs[0]}")
        for a, b, path in similars:
            self.say(f"SIMILAR-FIX #{a},#{b} file={clean(path, 80)} review manually, not auto-grouped")
        if not groups and not similars:
            self.say(f"NOOP no fix is carried by two open PRs into {self.a.base}")
        return RED if groups else OK


def diff_hunks(diff):
    """{path: [(start, end, plus, minus)]} from `git diff -U0` output. Pure.

    `start`/`end` bound the hunk's pre-image lines; `plus`/`minus` are its
    `+`/`-` lines (each side joined separately) with whitespace runs
    collapsed, so a re-indented copy still compares equal. A body line such
    as a removed `-- note` (printed `--- note`) is never taken for a file
    header, because headers are read only before a file's first hunk. Binary
    files have no hunks and are ignored.
    """
    out, path, old, body, cur = {}, None, None, False, None
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            path, old, body, cur = None, None, False, None
        elif not body and line.startswith("--- "):
            old = line[6:] if line.startswith("--- a/") else None
        elif not body and line.startswith("+++ "):
            path = line[6:] if line.startswith("+++ b/") else old
        elif line.startswith("@@ ") and path:
            m = re.match(r"@@ -(\d+)(?:,(\d+))? ", line)
            if m:
                start = int(m.group(1))
                body, cur = True, [start, start + max(int(m.group(2) or 1), 1), [], []]
                out.setdefault(path, []).append(cur)
        elif body and cur and line[:1] in ("+", "-"):
            (cur[2] if line[0] == "+" else cur[3]).append(" ".join(line[1:].split()))
    return {p: [(a, b, "\n".join(pl), "\n".join(ml)) for a, b, pl, ml in hs] for p, hs in out.items()}


def duplicate_fixes(diffs, threshold):
    """(duplicates, similars) among the open PRs' `git diff -U0` texts. Pure.

    `duplicates`: [(PR numbers ascending, [paths])], one entry per set of
    >= 2 PRs carrying the identical fix; the first number is the canonical
    (earliest) PR. `similars`: [(pr_a, pr_b, path)] ascending pairs that
    overlap but are not identical — reported for human review, never grouped
    or treated as a duplicate.

    Two PRs match on a file when a hunk of each overlaps the other (within
    DUP_PAD lines) on the same side: their POST-image (`+` lines) for an
    ordinary edit, or their pre-image (`-` lines) only when both hunks are a
    pure deletion (no `+` lines) — a deletion and a same-line edit are not
    the same fix, and comparing the pre-image of an edit would match any two
    different fixes to the same line (they share the line being fixed, not
    the fix). A match needs identical (whitespace-normalized) text for
    `duplicates`; a difflib ratio >= `threshold` but not identical lands in
    `similars` instead. Duplicate matches are grouped transitively per file;
    files whose groups hold the same PRs are listed together.
    """
    hunks = {n: diff_hunks(d) for n, d in diffs.items()}
    groups, similars = {}, []
    for path in sorted({p for h in hunks.values() for p in h}):
        prs = sorted(n for n in hunks if path in hunks[n])
        root = {n: n for n in prs}

        def find(n):
            while root[n] != n:
                n = root[n]
            return n
        for i, a in enumerate(prs):
            for b in prs[i + 1:]:
                exact = near = False
                for x0, x1, xp, xm in hunks[a][path]:
                    for y0, y1, yp, ym in hunks[b][path]:
                        if not (x0 - DUP_PAD < y1 and y0 - DUP_PAD < x1) or bool(xp) != bool(yp):
                            continue
                        xt, yt = (xp, yp) if xp else (xm, ym)
                        if xt == yt:
                            exact = True
                        elif difflib.SequenceMatcher(None, xt, yt).ratio() >= threshold:
                            near = True
                if exact:
                    root[max(find(a), find(b))] = min(find(a), find(b))
                elif near:
                    similars.append((a, b, path))
        sets = {}
        for n in prs:
            sets.setdefault(find(n), []).append(n)
        for members in sets.values():
            if len(members) > 1:
                groups.setdefault(tuple(members), []).append(path)
    return sorted(groups.items()), sorted(similars)


def glob_problem(glob):
    """'' when `glob` starts with a literal directory (`src/clock*.py`); else why not. Pure.

    `*` and `?` never cross `/` (fix_class_gate's grammar), and a glob with no
    literal directory (`*.py`, `s*`, `**`, `*/x`) could reach any file.
    """
    top, sep, _ = glob.partition("/")
    if not sep or not top or re.search(r"[*?\[]", top):
        return f"glob {glob!r} needs a literal directory prefix (e.g. src/clock*.py)"
    return ""


def glob_match(path, globs):
    """True when `path` matches one of `globs` in fix_class_gate's grammar (`*` stays within a segment)."""
    if _FCG is None:
        raise ForgeError("deep-code-review scripts/fix_class_gate.py not found; cannot match globs")
    return any(_FCG._glob_to_regex(g).match(path) for g in globs)


def build_parser():
    """Argument parser: plan / verify / merge / keystone / refresh / dupes subcommands plus --selftest."""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--base", required=True, help="target branch the PRs merge into")
    common.add_argument("--repo", default="", help="OWNER/NAME (default: gh infers from the checkout)")
    common.add_argument("--remote", default="origin")
    common.add_argument("--state", default="", help="state file (default <git-common-dir>/merge-train.json)")
    common.add_argument("--min-checks", type=int, default=1, help="K: latest successful check runs required")
    common.add_argument("--no-status", action="store_true", help=f"do not post the {GATE_CONTEXT} commit status before each apply merge")
    common.add_argument("--allow-forks", action="store_true", help="admit fork PRs (their code runs locally)")
    common.add_argument("--retries", type=int, default=2, help="bounded re-runs for a flaky step")
    common.add_argument("--backoff", type=float, default=30.0, help="first retry delay in seconds (doubles, max 300)")
    common.add_argument("--gate-backoff", type=float, default=5.0,
                        help="first delay before re-running a failing --verify-cmd (doubles, max 300)")
    common.add_argument("--partial-dir", default=None, help="PARTIAL-PASS receipts dir (default $PARTIAL_DIR or .perun/partial)")
    p = argparse.ArgumentParser(description="Verify several green PRs as one union, then land them back-to-back.")
    p.add_argument("--selftest", action="store_true", help="run offline self-tests against a fake forge")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("plan", parents=[common])
    v = sub.add_parser("verify", parents=[common])
    v.add_argument("--verify-cmd", required=True, help="gate command run once in the union tree (sh -c)")
    v.add_argument("--count-cmd", default="", help="prints one integer: a numeric ratchet count")
    v.add_argument("--cap", type=int, default=None, help="maximum allowed --count-cmd value")
    v.add_argument("--marker-key", default="size-budget-raise", help="trailer key recording a deliberate raise")
    v.add_argument("--timeout", type=int, default=3600, help="seconds per gate command")
    m = sub.add_parser("merge", parents=[common])
    m.add_argument("--apply", action="store_true", help="actually merge (default is a dry run)")
    m.add_argument("--grant", default="", help="the owner's decision or recorded standing grant authorising this merge")
    pk = sub.add_parser("partial-kill", parents=[common])
    pk.add_argument("--apply", action="store_true", help="open the revert PR (default is a dry run)")
    pk.add_argument("--wait", type=float, default=3600.0, help="seconds after the merge before a still-absent unchecked check is UNVERIFIED")
    k = sub.add_parser("keystone", parents=[common])
    k.add_argument("--pr", type=int, required=True, help="the keystone PR that fixes the red base")
    k.add_argument("--verify-cmd", required=True, help="the failing gate, run on the base alone and on base + PR")
    k.add_argument("--only", action="append", required=True,
                   help="glob of a file the fix may touch (repeatable); any other changed file refuses")
    k.add_argument("--require-signed", action="store_true",
                   help="also require a good signature (%%G? = G) on the grant line's commit")
    k.add_argument("--owner-email", action="append", default=[],
                   help="owner email (repeatable); else DCR_OWNER_EMAIL, else git config dcr.owner")
    k.add_argument("--apply", action="store_true", help="actually merge the keystone (default is a dry run)")
    k.add_argument("--use-update-branch", action="store_true",
                    help="post-merge refresh runs gh pr update-branch instead of printing local commands: "
                         "costs one CI run per PR")
    k.add_argument("--timeout", type=int, default=3600, help="seconds per gate command")
    k.set_defaults(count_cmd="")
    r = sub.add_parser("refresh", parents=[common])
    r.add_argument("--since", default="", help="the landed fix commit (default: the base head)")
    r.add_argument("--apply", action="store_true",
                    help="with --use-update-branch, run gh pr update-branch (default prints local commands)")
    r.add_argument("--use-update-branch", action="store_true",
                    help="run gh pr update-branch instead of printing local commands: costs one CI run per PR")
    r.add_argument("--include-drafts", action="store_true", help="also update-branch a draft PR (default: skip it)")
    d = sub.add_parser("dupes", parents=[common])
    d.add_argument("--similarity", type=float, default=0.9, help="minimum normalized hunk similarity, 0 < s <= 1")
    return p


def run(argv, runner=default_runner, out=sys.stdout, sleep=time.sleep) -> int:
    """Parse argv and execute one subcommand. Returns the exit code; never raises."""
    parser = build_parser()
    a = parser.parse_args(argv)
    if a.cmd is None:
        parser.print_usage(out)
        return ERROR
    problems = []
    if a.repo and not bc.validate_repo(a.repo):
        problems.append("--repo must be OWNER/NAME")
    if a.min_checks < 1:
        problems.append("--min-checks must be >= 1 (zero checks is never green)")
    if a.retries < 0 or a.backoff < 0 or a.gate_backoff < 0:
        problems.append("--retries/--backoff/--gate-backoff must be >= 0")
    if a.cmd == "verify" and bool(a.count_cmd) != (a.cap is not None):
        problems.append("--count-cmd and --cap go together")
    if a.cmd == "merge" and a.apply and not a.grant.strip():
        problems.append("--apply needs --grant naming the integration owner's decision or a recorded standing grant")
    if a.cmd == "keystone":
        problems += [glob_problem(g) for g in a.only if glob_problem(g)]
    if a.cmd == "refresh" and a.since.startswith("-"):
        problems.append("--since must be a commit, not an option")
    if a.cmd == "dupes" and not 0 < a.similarity <= 1:
        problems.append("--similarity must be in (0, 1]")
    if problems:
        print("ERROR " + "; ".join(problems), file=out)
        return ERROR
    train = None
    try:
        train = Train(a, runner, out, sleep)
        train.say(f"RUN {train.run_id}")
        return getattr(train, a.cmd.replace("-", "_"))()
    except Halt as exc:
        print(f"HALT {exc}", file=out)
        return HALT
    except Cancelled:
        print("CANCELLED run cancelled by request; refs released", file=out)
        return OK
    except (ForgeError, ValueError, KeyError, TypeError) as exc:
        print(f"ERROR {clean(exc, 240)} (not verified)", file=out)
        return ERROR
    finally:
        if train:
            train.drop_refs()


# ---- selftest: a fake forge + git, no network, no real repository ----------
class FakeForge:
    """Simulates the gh + git calls merge_train makes; records every call and sleep."""

    def __init__(self, n=4):
        self.hist = ["B0"]  # linear base history, tip last
        self.prs = {i: {"head": f"h{i}", "isDraft": False, "mergeable": "MERGEABLE", "isCrossRepository": False,
                        "state": "OPEN", "runs": [_run("ci", "success"), _run("lint", "success")]}
                    for i in range(1, n + 1)}
        self.bad = set()  # a union containing any of these fails verify
        self.flaky_left = 0  # the next N verify runs fail, then pass
        self.conflicts = set()  # these conflict when merged after any other member
        self.delta, self.marked = {}, set()
        self.view_override, self.merge_fail, self.intruder = {}, set(), False
        self.trees, self.calls, self.sleeps, self.gates = {}, [], [], []
        self.fail_prefix, self.parents, self.remote_override = None, {}, {}
        self.pushed, self.after_merge = {}, {}  # heads pushed after plan; remote refs changed by a merge
        self.red_base, self.fix, self.pids, self.files = False, set(), {}, {}  # keystone scenario
        self.contains, self.grant_text, self.grant_meta = set(), None, ""  # trees holding the fix; grant record
        self.grant_blame, self.grant_date = "a" * 40, datetime.now(timezone.utc).date().isoformat()
        self.bodies = []  # merge commit bodies written by `gh pr merge --body`
        self.based, self.udiffs, self.update_fail = {}, {}, set()  # refresh / dupes scenarios
        self.statuses, self.status_fail = [], False  # gate-status POST paths; simulate a rejected post
        self.dpid = {}  # head -> patch-id of merge-base..head (receipt carry)

    def base(self):
        return self.hist[-1]

    def __call__(self, args, cwd=None, timeout=None):
        self.calls.append(args)
        if self.fail_prefix and args[:len(self.fail_prefix)] == self.fail_prefix:
            return 1, "", "simulated outage"
        a = [args[0], *args[5:]] if args[1:5] == GIT_ID else args
        a = [a[0], *a[4:]] if a[1:4] == TRUST_GIT else a
        if a[:3] == ["gh", "pr", "list"]:
            rows = [{"number": n, "headRefOid": p["head"], **{k: p[k] for k in ("isDraft", "mergeable", "isCrossRepository")}}
                    for n, p in self.prs.items() if p["state"] == "OPEN"]
            return 0, json.dumps(rows), ""
        if a[:4] == ["gh", "api", "-X", "POST"]:
            with open(a[a.index("--input") + 1]) as fh:
                self.statuses.append((a[4], json.load(fh)))
            return (1, "", "HTTP 403: Resource not accessible") if self.status_fail else (0, "{}", "")
        if a[:2] == ["gh", "api"]:
            sha = a[2].split("/commits/")[1].split("/")[0]
            runs = next(p["runs"] for p in self.prs.values() if p["head"] == sha)
            return 0, json.dumps({"total_count": len(runs), "check_runs": runs}), ""
        if a[:3] == ["gh", "pr", "view"]:
            p = self.prs[int(a[3])]
            row = {"state": p["state"], "headRefOid": p["head"], "mergeable": p["mergeable"],
                   "isDraft": p["isDraft"], "isCrossRepository": p["isCrossRepository"], "baseRefName": "main"}
            row.update(self.view_override.get(int(a[3]), {}))
            return 0, json.dumps(row), ""
        if a[:3] == ["gh", "pr", "merge"]:
            n = int(a[3])
            if "--body" in a:
                self.bodies.append(a[a.index("--body") + 1])
            if n in self.merge_fail:
                return 1, "", "GraphQL: Pull request is not mergeable"
            if self.intruder:
                self.hist.append("X9")
            self.hist.append(f"M{n}")
            self.parents[f"M{n}"] = [self.hist[-2], self.prs[n]["head"]]
            self.prs[n]["state"] = "MERGED"
            self.remote_override.update(self.after_merge)
            return 0, "", ""
        if a[:3] == ["gh", "pr", "update-branch"]:
            return (1, "", "GraphQL: merge conflict") if int(a[3]) in self.update_fail else (0, "", "")
        if a[:3] == ["git", "diff", "-U0"]:
            return 0, self.udiffs.get(a[-1].split("...")[1], ""), ""
        if a[:2] in (["git", "fetch"], ["git", "update-ref"], ["git", "for-each-ref"]) or a[:3] in (
                ["git", "worktree", "remove"], ["git", "merge", "--abort"]):
            return 0, "", ""
        if a[:2] == ["git", "ls-remote"]:
            now = {"refs/heads/main": self.base(),
                   **{f"refs/pull/{n}/head": self.pushed.get(n, p["head"]) for n, p in self.prs.items()}}
            now.update(self.remote_override)
            return 0, "".join(f"{now[r]}\t{r}\n" for r in a[3:] if now.get(r)), ""
        if a[:3] == ["git", "rev-parse", "HEAD^{tree}"]:  # same start + same merged members = same tree
            t = self.trees[cwd]
            return 0, f"T{t['start']}-{'-'.join(map(str, sorted(t['merged'])))}\n", ""
        if a[:2] == ["git", "rev-parse"] and "/pull-" in a[2]:
            n = int(a[2].rsplit("-", 1)[1])
            return 0, self.pushed.get(n, self.prs[n]["head"]) + "\n", ""
        if a[:2] == ["git", "rev-parse"]:
            return 0, self.base() + "\n", ""
        if a[:3] == ["git", "worktree", "add"]:
            self.trees[a[5]] = {"start": a[6], "merged": []}
            return 0, "", ""
        if a[:2] == ["git", "merge"] and cwd:
            n = next((k for k, p in self.prs.items() if p["head"] == a[-1]), None) or int(a[-1][1:])
            if n in self.conflicts and self.trees[cwd]["merged"]:
                self.trees[cwd]["conflict"] = True
                return 1, "", "CONFLICT"
            self.trees[cwd]["merged"].append(n)
            return 0, "", ""
        if a[:4] == ["git", "diff", "--name-only", "--no-renames"] and cwd is None:
            head = a[4].split("...")[1]
            default = ["src/clock.py"] if head == self.prs[1]["head"] else [f"src/{head}.py"]
            return 0, "\n".join(self.files.get(head, default)) + "\n", ""
        if a[:4] == ["git", "diff", "--no-renames", "--binary"]:
            return 0, "PATCH\n", ""
        if a[:2] == ["sh", "-c"] and cwd is None and a[3] == "patch-id":
            head = a[-1].split("..")[1]
            return 0, "".join(f"{pid} {head}\n" for pid in self.pids.get(head, [])), ""
        if a[:3] == ["git", "diff", "--binary"]:  # receipt carry: raw diff text of merge-base..head
            return 0, self.dpid.get(a[3].split("..")[1], ""), ""
        if a[:2] == ["sh", "-c"] and cwd is None and a[3] == "keystone-contains":
            return (0 if a[4] in self.contains else 1), "", ""
        if a[:4] == ["git", "show", "-s", "--format=%cI"]:
            return 0, f"{self.grant_date}T12:00:00+00:00\n", ""
        if a[:3] == ["git", "show", "-s"]:
            return 0, self.grant_meta, ""
        if a[:2] == ["git", "show"]:
            return (0, self.grant_text, "") if self.grant_text is not None else (128, "", "fatal: path not in tree")
        if a[:2] == ["git", "log"] and any(x.startswith("--grep=") for x in a):
            needle = next(x for x in a if x.startswith("--grep="))[len("--grep="):]
            return 0, ("c" * 40 + "\n" if any(needle in b for b in self.bodies) else ""), ""
        if a[:2] == ["git", "blame"]:
            return 0, self.grant_blame + " 1 1 1\n", ""
        if a[:2] == ["git", "config"]:
            return 1, "", ""
        if a[:2] == ["git", "diff"]:
            return 0, "src/shared.py\n" if self.trees[cwd].pop("conflict", False) else "", ""
        if a[:3] == ["git", "merge-base", "--is-ancestor"]:
            if a[4] not in self.hist and a[4] in {p["head"] for p in self.prs.values()}:
                # a PR head holds only the base commits it branched from (or was updated onto)
                return (0 if a[3] in self.based.get(a[4], {"B0"}) else 1), "", ""
            return (0 if a[3] in self.hist else 1), "", ""
        if a[:2] == ["git", "merge-base"]:
            return 0, f"mb{a[2][1:]}\n", ""
        if a[:2] == ["git", "log"]:
            n = int(a[3].split("..h")[1])
            return 0, ("feat: x\n\nsize-budget-raise: a.md 1->2 reason\n" if n in self.marked else "feat: x\n"), ""
        if a[:2] == ["git", "rev-list"]:
            return 0, " ".join([a[-1], *self.parents.get(a[-1], ["?"])]), ""
        if a[:2] == ["sh", "-c"]:
            t = self.trees[cwd]
            if a[2] == "count":
                start = t["start"]
                own = self.delta.get(int(start[1:]), 0) if start.startswith("h") else 0
                return 0, str(10 + own + sum(self.delta.get(m, 0) for m in t["merged"])) + "\n", ""
            self.gates.append(tuple(t["merged"]))
            if self.flaky_left:
                self.flaky_left -= 1
                return 1, "", ""
            if self.red_base and not self.fix & set(t["merged"]):
                return 1, "", ""
            return (1 if self.bad & set(t["merged"]) else 0), "", ""
        return 99, "", f"fake: unexpected {args}"


def _run(name, conclusion, started="2026-01-01T00:00:00Z", rid=1, status="completed"):
    return {"name": name, "status": status, "conclusion": conclusion, "started_at": started, "id": rid}


def _selftest() -> int:
    import io

    tmp = tempfile.mkdtemp(prefix="merge-train-selftest-")

    def go(forge, *argv, state="s.json"):
        buf = io.StringIO()
        rc = run([*argv, "--base", "main", "--state", os.path.join(tmp, state), "--backoff", "5"],
                 runner=forge, out=buf, sleep=forge.sleeps.append)
        return rc, buf.getvalue()

    def fresh(state):
        p = os.path.join(tmp, state)
        if os.path.exists(p):
            os.remove(p)
        return state

    def verified(forge, state):
        rc, out = go(forge, "verify", "--verify-cmd", "t", state=fresh(state))
        assert rc == OK, out
        return state

    def plan_filters():
        f = FakeForge(7)
        f.prs[2]["isDraft"] = True
        f.prs[3]["runs"] = [_run("ci", "success", rid=1), _run("ci", "failure", "2026-01-02T00:00:00Z", 2), _run("lint", "success")]
        f.prs[4]["runs"] = [_run("ci", "failure", rid=1), _run("ci", "success", "2026-01-02T00:00:00Z", 2), _run("lint", "success")]
        f.prs[5]["mergeable"] = "CONFLICTING"
        f.prs[6]["runs"] = [_run("ci", "success")]
        f.prs[7]["isCrossRepository"] = True
        rc, out = go(f, "plan", "--min-checks", "2", state=fresh("plan.json"))
        want = ["ELIGIBLE #1 h1", "SKIP #2 draft", "SKIP #3 check ci=failure", "ELIGIBLE #4 h4",
                "SKIP #5 mergeable=CONFLICTING", "SKIP #6 checks 1<2", "SKIP #7 fork", "PLAN base=main members=#1,#4"]
        return rc == OK and all(w in out for w in want), out

    def culprit_among_four_is_isolated_and_stays_parked():
        f = FakeForge(4)
        f.bad = {3}
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("c.json"))
        # union fails; base passes; prefix #1,#2 passes; prefix #1,#2,#3 fails with #4 held out; rebuilt union passes
        runs = list(f.gates)
        want_runs = [(1, 2, 3, 4)] * 3 + [()] + [(1, 2)] + [(1, 2, 3)] * 3 + [(1, 2, 4)]
        ok1 = (rc == OK and "PARK #3 breaks gate after #1,#2" in out and "GREEN base=B0 members=#1,#2,#4" in out
               and runs == want_runs)
        rc2, out2 = go(f, "verify", "--verify-cmd", "t", state="c.json")
        ok2 = rc2 == OK and "SKIP #3 parked (breaks gate after #1,#2)" in out2 and f.gates[-1] == (1, 2, 4)
        f.prs[3]["head"] = "h3b"  # a new push is new information: it un-parks
        rc3, out3 = go(f, "plan", state="c.json")
        return ok1 and ok2 and rc3 == OK and "ELIGIBLE #3 h3b" in out3, (out, runs, out2, out3)

    def conflicts_all_parked_in_one_cycle_without_sleeping():
        f = FakeForge(4)
        f.conflicts = {2, 3, 4}
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("k.json"))
        ok = (rc == OK and all(f"PARK #{n} conflict src/shared.py" in out for n in (2, 3, 4))
              and "GREEN base=B0 members=#1" in out and f.sleeps == [] and f.gates == [(1,)])
        return ok, (out, f.sleeps, f.gates)

    def flaky_passes_on_retry_with_bounded_backoff():
        f = FakeForge(2)
        f.flaky_left = 2
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("f.json"))
        return (rc == OK and "FLAKY union #1,#2 passed on attempt 3/3" in out and "PARK" not in out
                and f.sleeps == [5, 10]), (out, f.sleeps)

    def deterministic_failure_parks_member():
        f = FakeForge(2)
        f.bad = {2}
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("d.json"))
        return (rc == OK and "FAIL union #1,#2 deterministic (3/3 attempts)" in out
                and "PARK #2 breaks gate after #1" in out and "GREEN base=B0 members=#1" in out), out

    def all_members_bad_is_red():
        f = FakeForge(2)
        f.bad = {1, 2}
        rc, out = go(f, "verify", "--verify-cmd", "t", "--retries", "0", state=fresh("r.json"))
        return rc == RED and "RED no green union" in out, out

    def red_base_halts():
        f = FakeForge(2)
        f.flaky_left = 99
        rc, out = go(f, "verify", "--verify-cmd", "t", "--retries", "0", state=fresh("rb.json"))
        return rc == HALT and "fails the gate on its own" in out, out

    def ratchet_overshoot_attributed_per_member():
        f = FakeForge(3)
        f.delta, f.marked = {1: 0, 2: 3, 3: 1}, {3}
        rc, out = go(f, "verify", "--verify-cmd", "t", "--count-cmd", "count", "--cap", "12", state=fresh("a.json"))
        want = ["FAIL union #1,#2,#3 cap 14>12", "#1 +0 marker=none", "#2 +3 marker=none", "#3 +1 marker=present",
                "PARK #2 ratchet +3 marker=none", "GREEN base=B0 members=#1,#3"]
        return rc == OK and all(w in out for w in want), out

    def dry_run_is_default():
        f = FakeForge(2)
        st = verified(f, "dr.json")
        rc, out = go(f, "merge", state=st)
        merged = [c for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        return rc == OK and "WOULD-MERGE #1 h1" in out and "DRY-RUN" in out and not merged, out

    def apply_needs_grant():
        rc, out = go(FakeForge(1), "merge", "--apply", state="dr.json")
        return rc == ERROR and "--grant" in out, out

    def apply_merges_back_to_back():
        f = FakeForge(2)
        st = verified(f, "ap.json")
        rc, out = go(f, "merge", "--apply", "--grant", "owner-grant-1", state=st)
        merged = [c[3] for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        again_rc, again = go(f, "merge", "--apply", "--grant", "owner-grant-1", state=st)
        return (rc == OK and merged == ["1", "2"] and "MERGED #2 h2 -> main@M2 grant=owner-grant-1" in out
                and all("--merge" in c for c in f.calls if c[:3] == ["gh", "pr", "merge"])
                and again_rc == OK and "NOOP" in again), (out, merged, again)

    def st(f):
        return [(p.rsplit("/", 1)[1], d["state"], d["context"]) for p, d in f.statuses]

    def verify_and_dry_run_post_nothing():
        f = FakeForge(2)
        stt = verified(f, "gs.json")
        rc, out = go(f, "merge", state=stt)
        return rc == OK and "DRY-RUN" in out and not f.statuses, (f.statuses, out)

    def apply_posts_success_then_merges():
        f = FakeForge(2)
        stt = verified(f, "ap.json")
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=stt)
        order = [("s", c[4].rsplit("/", 1)[1]) if c[:2] == ["gh", "api"] else ("m", c[3]) for c in f.calls
                 if (c[:2] == ["gh", "api"] and "POST" in c) or c[:3] == ["gh", "pr", "merge"]]
        return (rc == OK and st(f) == [("h1", "success", "perun/train-gate"), ("h2", "success", "perun/train-gate")]
                and order == [("s", "h1"), ("m", "1"), ("s", "h2"), ("m", "2")]
                and "B0" in f.statuses[0][1]["description"]), (f.statuses, order, out)

    def base_moved_after_verify_posts_nothing():
        f = FakeForge(2)
        stt = verified(f, "bmv.json")
        f.hist.append("B1")
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=stt)
        return rc == HALT and not f.statuses, out

    def failed_merge_overwrites_with_error():
        f = FakeForge(2)
        stt = verified(f, "fm.json")
        f.merge_fail = {1}
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=stt)
        return rc == HALT and st(f) == [("h1", "success", "perun/train-gate"), ("h1", "error", "perun/train-gate")], (st(f), out)

    def no_status_flag_posts_nothing():
        f = FakeForge(2)
        stt = verified(f, "ns.json")
        rc, out = go(f, "merge", "--apply", "--grant", "g", "--no-status", state=stt)
        return rc == OK and "MERGED #2" in out and not f.statuses and "STATUS" not in out, out

    def failed_status_post_warns_never_claims_posted():
        f = FakeForge(2)
        f.status_fail = True
        stt = verified(f, "sf.json")
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=stt)
        return rc == OK and "WARN perun/train-gate=success NOT posted on #1" in out and "STATUS posted" not in out, out

    def base_moved_halts_without_reverify():
        f = FakeForge(2)
        st = verified(f, "bm.json")
        f.hist.append("B1")  # someone else landed a commit (fast-forward)
        before = len(f.gates)
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=st)
        merged = [c for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        return (rc == HALT and "moved B0->B1" in out and "re-plan" in out and not merged
                and len(f.gates) == before), out

    def base_rewritten_halts():
        f = FakeForge(2)
        st = verified(f, "rw.json")
        f.hist = ["Z0"]  # force-pushed: B0 is no longer in history
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=st)
        merged = [c for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        return rc == HALT and "rewritten" in out and "non-fast-forward" in out and not merged, out

    def intruder_mid_train_halts():
        f = FakeForge(2)
        st = verified(f, "in.json")
        f.intruder = True
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=st)
        merged = [c[3] for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        return rc == HALT and "another writer" in out and merged == ["1"], out

    def merge_time_conflict_parks_and_halts():
        f = FakeForge(3)
        st = verified(f, "mc.json")
        f.view_override = {2: {"mergeable": "CONFLICTING"}}
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=st)
        merged = [c[3] for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        return (rc == HALT and "PARK #2 mergeable=CONFLICTING" in out and "#3 left unmerged" in out
                and merged == ["1"]), out

    def unknown_mergeable_polls_then_parks():
        f = FakeForge(1)
        st = verified(f, "uk.json")
        f.view_override = {1: {"mergeable": "UNKNOWN"}}
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=st)
        return rc == HALT and "mergeable=UNKNOWN after 3 polls" in out and f.sleeps == [5, 10], (out, f.sleeps)

    def push_is_refused_before_the_runner():
        f = FakeForge(1)
        a = build_parser().parse_args(["plan", "--base", "main", "--state", os.path.join(tmp, "p.json")])
        t = Train(a, f, io.StringIO(), f.sleeps.append)
        try:
            t.run(["git", "push", "--force", "origin", "main"])
            return False, "no HALT"
        except Halt:
            return not any("push" in c for c in f.calls), f.calls

    def forge_outage_fails_closed():
        f = FakeForge(1)
        f.fail_prefix = ["gh", "pr", "list"]
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("o.json"))
        return rc == ERROR and "not verified" in out and not f.gates, out

    def untrusted_text_is_sanitised():
        return clean("a\x1b[31mb\nc") == "a?[31mb?c", clean("a\x1b[31mb\nc")

    def real_repos():
        """A real 'remote' repo (main + refs/pull/1/head) and an empty local repo pointing at it."""
        root = tempfile.mkdtemp(dir=tmp)
        src, local = os.path.join(root, "src"), os.path.join(root, "local")

        def git(*args, cwd=src):
            rc, out, err = default_runner(["git", *GIT_ID, *args], cwd=cwd)
            assert rc == 0, err
            return out.strip()
        for d in (src, local):
            git("init", "--quiet", d, cwd=root)
        git("commit", "--quiet", "--allow-empty", "-m", "base")
        git("branch", "-M", "main")
        git("update-ref", "refs/pull/1/head", git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "pr v1"))
        git("remote", "add", "origin", src, cwd=local)
        return git, local, lambda args, cwd=None, **kw: default_runner(args, cwd=cwd or local, **kw)

    def real_train(runner, out=None):
        a = build_parser().parse_args(["plan", "--base", "main", "--state", os.path.join(tmp, "rt.json")])
        return Train(a, runner, out or io.StringIO(), lambda s: None)

    def dead_pid():
        proc = subprocess.Popen([sys.executable, "-c", ""])
        proc.wait()
        return proc.pid

    def restart_after_crash_fetches_fresh_and_sweeps_dead_refs():
        git, local, runner = real_repos()
        v1 = git("rev-parse", "refs/pull/1/head")
        crashed = real_train(runner)
        crashed.run_id = f"{dead_pid()}-0123456789ab"  # a run whose process died without dropping its refs
        crashed.fetch([{"number": 1, "head": v1}])
        git("update-ref", f"refs/merge-train/{os.getpid()}-live/base", v1, cwd=local)  # a live run's ref
        v2 = git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "pr v2")  # non-fast-forward to v1
        git("update-ref", "refs/pull/1/head", v2)
        fresh_run = real_train(runner)
        _, kept = fresh_run.fetch([{"number": 1, "head": v2}])
        got = fresh_run.rev(f"refs/merge-train/{fresh_run.run_id}/pull-1")
        swept = f"refs/merge-train/{crashed.run_id}/" not in git("for-each-ref", "refs/merge-train/", cwd=local)
        fresh_run.drop_refs()
        left = git("for-each-ref", "--format=%(refname)", "refs/merge-train/", cwd=local)
        return (fresh_run.run_id != crashed.run_id and got == v2 and len(kept) == 1 and swept
                and left == f"refs/merge-train/{os.getpid()}-live/base"), (got, v2, kept, swept, left)

    def same_run_refetch_updates_non_fast_forward_ref():
        git, _, runner = real_repos()
        t = real_train(runner)
        t.fetch([{"number": 1, "head": git("rev-parse", "refs/pull/1/head")}])
        v2 = git("commit-tree", "HEAD^{tree}", "-p", "HEAD", "-m", "pr v2")
        git("update-ref", "refs/pull/1/head", v2)
        _, kept = t.fetch([{"number": 1, "head": v2}])
        got = t.rev(f"refs/merge-train/{t.run_id}/pull-1")
        t.drop_refs()
        return got == v2 and len(kept) == 1, (got, v2, kept)

    def failed_fetch_halts_cycle():
        git, local, runner = real_repos()
        t = real_train(runner)
        git("commit", "--quiet", "--allow-empty", "-m", "local", cwd=local)
        git("update-ref", f"refs/merge-train/{t.run_id}", "HEAD", cwd=local)  # blocks refs/merge-train/<run>/...
        seen = []
        t.runner = lambda args, cwd=None, **kw: seen.append(args[:2]) or runner(args, cwd=cwd, **kw)
        try:
            t.fetch([{"number": 1, "head": git("rev-parse", "refs/pull/1/head")}])
            real_ok = False
        except ForgeError as exc:
            real_ok = "git fetch" in str(exc)
        ordered = ["git", "ls-remote"] in seen and seen.index(["git", "ls-remote"]) < seen.index(["git", "fetch"])
        f = FakeForge(2)
        f.fail_prefix = ["git", "fetch"]
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("ff.json"))
        return real_ok and ordered and rc == ERROR and not f.gates and "GREEN" not in out, (real_ok, seen, out)

    def drifted_member_is_skipped_not_the_cycle():
        f = FakeForge(2)
        f.pushed = {2: "h2b"}  # #2 was pushed after plan read its checks
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("dm.json"))
        return (rc == OK and "SKIP #2 head moved to h2b since plan" in out and "GREEN base=B0 members=#1" in out
                and f.sleeps == []), (out, f.sleeps)

    def raced_member_retried_then_skipped():
        f = FakeForge(2)
        f.remote_override = {"refs/pull/2/head": "h2new"}  # the remote keeps disagreeing with the fetched ref
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("sf.json"))
        return (rc == OK and "SKIP #2 stale or raced fetch" in out and "GREEN base=B0 members=#1" in out
                and f.sleeps == [5, 10]), (out, f.sleeps)

    def vanished_pr_ref_is_skipped_not_fetched():
        f = FakeForge(2)
        f.remote_override = {"refs/pull/2/head": None}  # ls-remote no longer lists #2's head
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("vr.json"))
        fetched = [c for c in f.calls if c[:2] == ["git", "fetch"]]
        return (rc == OK and "SKIP #2 no refs/pull/2/head on origin" in out and "GREEN base=B0 members=#1" in out
                and not any("refs/pull/2/head" in " ".join(c) for c in fetched)), (out, fetched)

    def raced_base_retried_then_errors():
        f = FakeForge(2)
        f.remote_override = {"refs/heads/main": "B9"}
        rc, out = go(f, "verify", "--verify-cmd", "t", state=fresh("rbf.json"))
        return (rc == ERROR and "stale or raced fetch" in out and not f.gates and f.sleeps == [5, 10]), (out, f.sleeps)

    def drop_failure_is_logged_and_never_raises():
        results = []
        for mode in ("rc", "raise"):
            f = FakeForge(1)

            def flaky_drop(args, cwd=None, _f=f, _mode=mode, **kw):
                if args[:2] == ["git", "update-ref"]:
                    if _mode == "raise":
                        raise RuntimeError("disk gone")
                    return 1, "", "cannot lock ref"
                return _f(args, cwd=cwd, **kw)
            flaky_drop.sleeps = f.sleeps
            rc, out = go(flaky_drop, "verify", "--verify-cmd", "t", state=fresh(f"df-{mode}.json"))
            results.append((rc, out))
        return all(rc == OK and "DROP-FAILED" in out for rc, out in results), results

    def post_merge_fetch_mismatch_halts_after_merged_line():
        f = FakeForge(2)
        st = verified(f, "pm.json")
        f.after_merge = {"refs/heads/main": "B9"}  # the post-merge base cannot be proved
        rc, out = go(f, "merge", "--apply", "--grant", "g", state=st)
        merged = [c[3] for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        with open(os.path.join(tmp, st), encoding="utf-8") as fh:
            left = json.load(fh)["members"]
        return (rc == HALT and merged == ["1"] and "#1 landed; base unverified" in out and left == []
                and 0 <= out.find("MERGED #1") < out.find("HALT")), (out, merged, left)

    def non_int_pr_number_is_rejected():
        f = FakeForge(1)
        t = real_train(f)
        try:
            t.fetch([{"number": "1:refs/heads/main", "head": "h1"}])
            return False, "accepted"
        except ForgeError:
            return not any(c[:2] == ["git", "fetch"] for c in f.calls), f.calls

    OWNER = "owner@example.com"
    K1 = "a1b2c3d4e5f60718"  # the keystone PR's head: hex, so a named grant can pin it
    today = datetime.now(timezone.utc).date()

    def class_body(days=10, globs="src/clock*.py", max_files="1", expires=True):
        exp = f" | expires={(today + timedelta(days=days)).isoformat()}" if expires else ""
        return f"{globs}{exp} | max-files={max_files}"

    def class_line(**kw):
        return f"keystone-class: {class_body(**kw)}\n"

    def line_key(row, blame="a" * 40):
        return f"{blame}:{hashlib.sha256(row.strip().encode()).hexdigest()[:16]}"

    def keystone_forge():
        f = FakeForge(3)  # #1 is the keystone; #3 carries a cherry-pick of it
        f.prs[1]["head"] = K1
        f.red_base, f.fix = True, {1}
        f.pids = {K1: ["pk"], "h2": ["p2"], "h3": ["p3", "pk"]}
        f.grant_text = f"keystone: #1 @{K1[:10]}\n"
        f.grant_meta = f"{OWNER}\x1fN\x1f"
        return f

    def ks(f, *extra, state="ks.json", pr="1", keep=False):
        return go(f, "keystone", "--pr", pr, "--verify-cmd", "t", "--only", "src/clock*.py",
                  "--owner-email", OWNER, "--retries", "0", *extra, state=state if keep else fresh(state))

    def keystone_proves_parks_cherry_pick_and_dry_runs():
        f = keystone_forge()
        rc, out = ks(f)
        merged = [c for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        want = ["KEYSTONE #1 base=B0 red alone, green with #1", "PARK #3 carries a cherry-pick of keystone #1",
                f"WOULD-MERGE #1 {K1[:7]} alone", "DRY-RUN"]
        return (rc == OK and all(w in out for w in want) and "PARK #2" not in out and not merged
                and f.gates == [(), (1,)]), out

    def keystone_apply_merges_alone_spends_grant_in_merge_commit():
        f = keystone_forge()
        rc, out = ks(f, "--apply", state="ka.json")
        merges = [c for c in f.calls if c[:3] == ["gh", "pr", "merge"]]
        rc2, out2 = go(f, "plan", state="ka.json")
        f.prs[3]["head"] = "h3b"  # rebased onto the new base: the duplicate patch is gone
        rc3, out3 = go(f, "plan", state="ka.json")
        with open(os.path.join(tmp, "ka.json"), encoding="utf-8") as fh:
            st = json.load(fh)
        trailer = f"Keystone-Grant: {line_key(f'keystone: #1 @{K1[:10]}')}"
        return (rc == OK and [c[3] for c in merges] == ["1"] and trailer in merges[0]
                and f"MERGED #1 {K1[:7]} -> main@M1" in out and "keystone" not in st
                and "keystone_grants_used" not in st
                and rc2 == OK and "SKIP #3 parked (carries a cherry-pick" in out2
                and rc3 == OK and "ELIGIBLE #3 h3b" in out3), (out, out2, out3, merges)

    def keystone_refused_on_green_base():
        f = keystone_forge()
        f.red_base = False
        rc, out = ks(f)
        return rc == HALT and "base B0 is green" in out, out

    def keystone_refused_when_union_stays_red():
        f = keystone_forge()
        f.fix = set()
        rc, out = ks(f)
        return rc == HALT and "does not green the base" in out, out

    def keystone_refused_outside_only_before_any_gate():
        f = keystone_forge()
        f.files = {K1: ["src/clock.py", "docs/notes.md"]}
        rc, out = ks(f)
        g = keystone_forge()
        g.files = {K1: ["src/sub/clock.py"]}  # `*` never crosses `/`
        rc2, out2 = ks(g)
        listed = [c for c in f.calls if c[:3] == ["git", "diff", "--name-only"]]
        return (rc == HALT and "docs/notes.md outside --only" in out and not f.gates
                and rc2 == HALT and "src/sub/clock.py outside --only" in out2 and not g.gates
                and all("--no-renames" in c for c in listed) and listed), (out, out2)

    def keystone_refused_wrong_target_branch():
        f = keystone_forge()
        f.view_override = {1: {"baseRefName": "release"}}
        rc, out = ks(f)
        return rc == HALT and "targets release" in out and not f.gates, out

    def keystone_runs_eligibility_before_any_gate():
        f = keystone_forge()
        f.prs[1]["mergeable"] = "CONFLICTING"
        rc, out = ks(f)
        g = keystone_forge()
        g.prs[1]["runs"] = [_run("ci", "failure")]
        rc2, out2 = ks(g)
        return (rc == HALT and "mergeable=CONFLICTING" in out and "WOULD-MERGE" not in out and not f.gates
                and rc2 == HALT and "check ci=failure" in out2 and not g.gates), (out, out2)

    def keystone_grant_owner_authored_pinned_and_hardened():
        cases_ = [("grant_meta", "intruder@example.com\x1fN\x1f", "is not the owner", ()),
                  ("grant_meta", f"{OWNER}\x1fN\x1fAgent <agent@example.com>", "Co-authored-by", ()),
                  ("grant_text", "keystone: #12 @a1b2c3d\n", "no 'keystone: #1' or 'keystone-class:' line", ()),
                  ("grant_text", "keystone: #1\n", "must pin @<sha> or carry class limits", ()),
                  ("grant_text", "keystone: #1 @deadbeef\n", "pinned to deadbeef", ()),
                  ("grant_text", None, "is not committed on main", ()),
                  ("grant_meta", f"{OWNER}\x1fN\x1f", "no good signature", ("--require-signed",))]
        outs, ok = [], True
        for attr, value, want, extra in cases_:
            f = keystone_forge()
            setattr(f, attr, value)
            rc, out = ks(f, *extra)
            outs.append(out)
            ok = ok and rc == HALT and want in out and not f.gates
        f = keystone_forge()
        f.grant_meta = f"{OWNER}\x1fG\x1f"
        rc, out = ks(f, "--require-signed")
        ok = ok and rc == OK
        trusted = [c for c in f.calls if c[:1] == ["git"] and ("blame" in c or "show" in c or "--grep" in " ".join(c))]
        shows = [c for c in f.calls if "show" in c and "-s" not in c]
        ok = ok and trusted and all(c[1:4] == TRUST_GIT for c in trusted)
        ok = ok and shows and all(c[-1] == f"B0:{GRANTS_PATH}" for c in shows)
        saved = os.environ.pop("DCR_OWNER_EMAIL", None)
        try:
            g = keystone_forge()
            rc, out = go(g, "keystone", "--pr", "1", "--verify-cmd", "t", "--only", "src/clock*.py",
                         "--retries", "0", state=fresh("kn.json"))
        finally:
            if saved is not None:
                os.environ["DCR_OWNER_EMAIL"] = saved
        outs.append(out)
        return ok and rc == HALT and "no owner identity" in out and not g.gates, outs

    def keystone_parks_squash_copies_and_touchers():
        f = keystone_forge()
        f.files = {"h2": ["src/clock.py", "src/h2.py"], "h3": ["src/clock.py"]}
        f.pids = {K1: ["pk"], "h2": ["p2"], "h3": ["p3"]}  # no shared patch-id: a squash / edited copy
        f.contains = {"h2"}  # the keystone diff reverse-applies on #2's tree
        rc, out = ks(f)
        return (rc == OK and "PARK #2 carries a copy of keystone #1" in out
                and "PARK #3 touches keystone #1 file src/clock.py" in out), out

    def keystone_record_screens_repushed_siblings_until_it_lands():
        f = keystone_forge()
        rc, out = ks(f, state="kr.json")
        f.prs[3]["head"], f.pids["h3b"] = "h3b", ["p3", "pk"]  # re-push that still carries the copy
        rc2, out2 = go(f, "verify", "--verify-cmd", "t", "--retries", "0", state="kr.json")
        f.hist.append("M1")  # the keystone's change reached the base outside this tool
        f.red_base, f.contains = False, {"M1"}
        f.prs[3]["head"], f.pids["h3c"] = "h3c", ["p3", "pk"]
        rc3, out3 = go(f, "verify", "--verify-cmd", "t", "--retries", "0", state="kr.json")
        return (rc == OK and rc2 == OK and "PARK #3 carries a cherry-pick of keystone #1" in out2
                and "GREEN base=B0 members=#1,#2" in out2
                and rc3 == OK and "KEYSTONE #1 landed" in out3 and "PARK #3" not in out3), (out2, out3)

    def keystone_record_clears_on_merged_state_or_ancestor_head():
        outs, ok = [], True
        for how in ("merged", "ancestor"):
            f = keystone_forge()
            ks(f, state="kc2.json")
            if how == "merged":
                f.prs[1]["state"] = "MERGED"
            else:
                f.hist.append(K1)  # the keystone head is now reachable from the base
            f.red_base = False
            f.prs[3]["head"], f.pids["h3b"] = "h3b", ["p3", "pk"]
            rc, out = go(f, "verify", "--verify-cmd", "t", "--retries", "0", state="kc2.json")
            outs.append(out)
            ok = ok and rc == OK and "KEYSTONE #1 landed" in out and "PARK #3" not in out
        return ok, outs

    def keystone_conflict_halts_cleanly():
        f = keystone_forge()
        real = f.__call__

        def conflicting(args, cwd=None, timeout=None):
            if args[1:6] == [*GIT_ID, "merge"] and cwd and args[-1] == K1:
                f.calls.append(args)
                f.trees[cwd]["conflict"] = True
                return 1, "", "CONFLICT"
            return real(args, cwd=cwd, timeout=timeout)
        buf = io.StringIO()
        rc = run(["keystone", "--pr", "1", "--verify-cmd", "t", "--only", "src/clock*.py",
                  "--owner-email", OWNER, "--retries", "0", "--base", "main",
                  "--state", os.path.join(tmp, fresh("kc.json"))],
                 runner=conflicting, out=buf, sleep=f.sleeps.append)
        return rc == HALT and "conflicts with the base (src/shared.py)" in buf.getvalue(), buf.getvalue()

    def keystone_globs_need_a_literal_directory_prefix():
        outs, ok = [], True
        for glob in ("*.py", "s*", "**", "*/clock.py"):
            rc, out = go(keystone_forge(), "keystone", "--pr", "1", "--verify-cmd", "t", "--only", glob)
            outs.append(out)
            ok = ok and rc == ERROR and "needs a literal directory prefix" in out
        f = keystone_forge()
        f.grant_text = class_line(globs="*.py")
        rc, out = ks(f)
        outs.append(out)
        return ok and rc == HALT and "needs a literal directory prefix" in out and not f.gates, outs

    def class_grant_spent_only_by_apply_until_a_new_owner_commit():
        f = keystone_forge()
        f.grant_text, f.fix = class_line(), {1, 2}
        f.files = {"h2": ["src/clock.py"]}
        f.pids = {K1: ["pk"], "h2": ["p2"], "h3": ["p3"]}
        rc, out = ks(f, state="cg.json")
        rc2, out2 = ks(f, state="cg2.json", pr="2")  # a dry run spends nothing
        dry_bodies = list(f.bodies)
        rc3, out3 = ks(f, "--apply", state="cg3.json")  # --apply spends the grant in the merge commit
        f.red_base = True  # keep the base red for the second keystone's proof
        rc4, out4 = ks(f, state="cg4.json", pr="2")
        f.grant_blame = "b" * 40  # the owner re-commits the class line: a new grant
        rc5, out5 = ks(f, state="cg5.json", pr="2")
        return (rc == OK and "GRANT class" in out and rc2 == OK and "KEYSTONE #2" in out2 and dry_bodies == []
                and rc3 == OK and rc4 == HALT and "grant already used by merge" in out4
                and rc5 == OK and "KEYSTONE #2" in out5), (out, out2, out3, out4, out5)

    def class_grant_refusals():
        cases_ = [(class_line(days=-1), None, "expired"),
                  (class_line(days=31), None, "more than 30 days"),
                  (class_line(expires=False), None, "needs expires=YYYY-MM-DD"),
                  (class_line(max_files="0"), None, "needs max-files"),
                  (class_line(), ["src/clock.py", "src/clock2.py"], "2 files > max-files=1"),
                  (class_line(globs="lib/*.py"), None, "src/clock.py outside the grant's globs")]
        outs, ok = [], True
        for text, files, want in cases_:
            f = keystone_forge()
            f.grant_text = text
            if files:
                f.files = {K1: files}
            rc, out = ks(f, state="cr.json")
            outs.append(out)
            ok = ok and rc == HALT and want in out and not f.gates
        return ok, outs

    def class_grant_picks_the_unused_class_that_covers_the_files():
        f = keystone_forge()
        spent_row = class_line(globs="src/clock.py")
        f.grant_text = class_line(globs="lib/x*.py") + spent_row + class_line(globs="src/c*.py")
        f.bodies = [f"merge\n\nKeystone-Grant: {line_key(spent_row)}"]
        rc, out = ks(f)
        return rc == OK and "GRANT class" in out and "globs=src/c*.py" in out, out

    def keystone_git_helpers_on_a_real_repo():
        repo = tempfile.mkdtemp(dir=tmp)

        def git(*args, who=OWNER):
            rc, out, err = default_runner(["git", "-c", "user.name=T", "-c", f"user.email={who}",
                                           "-c", "commit.gpgsign=false", *args], cwd=repo)
            assert rc == 0, err
            return out.strip()

        def write(path, text):
            os.makedirs(os.path.dirname(os.path.join(repo, path)) or repo, exist_ok=True)
            with open(os.path.join(repo, path), "w", encoding="utf-8") as fh:
                fh.write(text)
        git("init", "--quiet", "-b", "main")
        write("src/clock.py", "a\nb\nold\nc\nd\n")
        write("docs/old.py", "helper\n")
        owner_grant = (f"keystone: #1 | {class_body(max_files='2')}\n"
                       + class_line(globs="docs/*.md"))
        write(GRANTS_PATH, owner_grant)
        git("add", "-A")
        git("commit", "--quiet", "-m", "base with the owner's keystone grants")
        write(GRANTS_PATH, owner_grant + f"keystone: #2 | {class_body()}\n")
        git("commit", "--quiet", "-am", "widen\n\nCo-authored-by: Agent <agent@example.com>")
        base = git("rev-parse", "HEAD")

        def branch(name, *edits):
            git("checkout", "--quiet", "-B", name, base)
            for path, text in edits:
                if text is None:
                    git("mv", "docs/old.py", path)
                else:
                    write(path, text)
            git("add", "-A")
            git("commit", "--quiet", "-m", name)
            return git("rev-parse", "HEAD")
        k = branch("k", ("src/clock.py", "a\nb\nfixed\nc\nd\n"))
        ren = branch("ren", ("src/clock_helper.py", None))
        squash = branch("sq", ("src/clock.py", "a\nb\nfixed\nc\nd\n"), ("other.txt", "x\n"))
        toucher = branch("touch", ("src/clock.py", "a\nb\nsomething else\nc\nd\n"))
        clean_ = branch("clean", ("c.txt", "c\n"))
        t = real_train(lambda args, cwd=None, **kw: default_runner(args, cwd=cwd or repo, **kw))
        t.base_sha = base
        patch = t.diff_patch(base, k)
        rec = {"pr": 1, "head": k, "files": t.changed(base, k), "patch_ids": sorted(t.patch_ids(k)),
               "patch": patch}
        files = ["src/clock.py"]
        class_grant = t.grant(9, [OWNER], k, ["docs/a.md"])
        results = {
            "rename-lists-source": "docs/old.py" in t.changed(base, ren),
            "squash-copy": t.carries(rec, squash).startswith("carries a copy"),
            "toucher": t.carries(rec, toucher).startswith("touches keystone #1 file src/clock.py"),
            "clean": t.carries(rec, clean_) == "",
            "base-lacks-fix": not t.contains(patch, base),
            "keystone-has-fix": t.contains(patch, k),
            "named-with-limits-ok": t.grant(1, [OWNER], k, files)[0] == "",
            "grant-coauthored": "Co-authored-by" in t.grant(2, [OWNER], k, files)[0],
            "grant-non-owner": "is not the owner" in t.grant(1, ["other@example.com"], k, files)[0],
            "class-ok": class_grant[0] == "" and class_grant[1]["kind"] == "class",
        }
        git("checkout", "--quiet", "-B", "landed", base)
        git("commit", "--quiet", "--allow-empty", "-m", f"Merge keystone\n\nKeystone-Grant: {class_grant[1]['key']}")
        t.base_sha = git("rev-parse", "HEAD")
        results["class-spent-by-trailer"] = "grant already used by merge" in t.grant(9, [OWNER], k, ["docs/a.md"])[0]
        t.grants_path = "missing.md"
        results["grants-file-missing"] = "is not committed" in t.grant(1, [OWNER], k, files)[0]
        return all(results.values()), results

    def refresh_forge():
        f = FakeForge(3)
        f.hist.append("F1")  # a fix landed on the base after every PR branched
        f.based = {"h1": {"B0", "F1"}}  # #1 was already updated onto it
        return f

    def refresh_default_prints_local_commands_no_ci_cost():
        f = refresh_forge()
        rc, out = go(f, "refresh", "--apply", state=fresh("rf.json"))  # --apply alone: still local, no cost
        calls = [c for c in f.calls if c[:3] in (["gh", "pr", "update-branch"], ["gh", "pr", "checkout"])]
        want = ["SKIP #1 already contains main@F1", "LOCAL #2 behind main@F1: gh pr checkout 2",
                "LOCAL #3 behind main@F1: gh pr checkout 3", "--use-update-branch opts into"]
        return rc == OK and all(w in out for w in want) and not calls, out

    def refresh_local_command_is_exact_and_carries_repo_flag():
        f = refresh_forge()
        rc, out = go(f, "refresh", state=fresh("rfx.json"))
        rc2, out2 = go(f, "refresh", "--repo", "acme/widgets", state=fresh("rfxr.json"))
        want = ("LOCAL #2 behind main@F1: gh pr checkout 2 && git fetch origin main && "
                "git merge origin/main && git push  (run this on your own next push; "
                "--use-update-branch costs one CI run per PR instead)")
        want_repo = ("LOCAL #2 behind main@F1: gh pr checkout 2 --repo acme/widgets && git fetch origin main && "
                     "git merge origin/main && git push  (run this on your own next push; "
                     "--use-update-branch costs one CI run per PR instead)")
        return rc == OK and want in out and rc2 == OK and want_repo in out2, (out, out2)

    def refresh_use_update_branch_dry_run_prints_gh_command():
        f = refresh_forge()
        rc, out = go(f, "refresh", "--use-update-branch", state=fresh("rf.json"))
        updates = [c for c in f.calls if c[:3] == ["gh", "pr", "update-branch"]]
        want = ["SKIP #1 already contains main@F1", "WOULD-UPDATE #2 behind main@F1: gh pr update-branch 2",
                "WOULD-UPDATE #3 behind main@F1: gh pr update-branch 3", "DRY-RUN"]
        return rc == OK and all(w in out for w in want) and not updates, out

    def refresh_apply_updates_and_reports_each_failure():
        f = refresh_forge()
        f.update_fail = {2}
        rc, out = go(f, "refresh", "--use-update-branch", "--apply", "--repo", "acme/widgets", state=fresh("rf.json"))
        updates = [c[3:] for c in f.calls if c[:3] == ["gh", "pr", "update-branch"]]
        return (rc == RED and updates == [["2", "--repo", "acme/widgets"], ["3", "--repo", "acme/widgets"]]
                and "UPDATE-FAILED #2" in out and "UPDATED #3" in out), out

    def refresh_since_pins_the_fix_commit():
        f = refresh_forge()
        f.hist.append("B2")  # an unrelated commit after the fix
        rc, out = go(f, "refresh", "--since", "F1", state=fresh("rf.json"))
        rc2, out2 = go(f, "refresh", "--since", "Z9", state=fresh("rf.json"))
        rc4, out4 = go(f, "refresh", "--since=--output=x", state=fresh("rf.json"))
        rc3, out3 = go(f, "refresh", state=fresh("rf.json"))  # default: the base head
        return (rc == OK and "SKIP #1 already contains main@F1" in out and "LOCAL #2" in out
                and rc2 == ERROR and "not on main" in out2 and rc4 == ERROR and "not an option" in out4
                and rc3 == OK and "LOCAL #1 behind main@B2" in out3), (out, out2, out3)

    def keystone_apply_refresh_follows_local_default_no_ci_cost():
        f = keystone_forge()
        rc, out = ks(f, "--apply", state="kf.json")
        calls = [c for c in f.calls if c[:3] == ["gh", "pr", "update-branch"]]
        return (rc == OK and not calls and "LOCAL #2" in out
                and "SKIP #3 carries a cherry-pick of keystone #1" in out), out

    def keystone_use_update_branch_opts_into_gh_update_branch():
        # parity: keystone's own --use-update-branch (not just refresh's) opts
        # its post-merge refresh into gh pr update-branch.
        f = keystone_forge()
        rc, out = ks(f, "--use-update-branch", "--apply", state="kuub.json")
        updates = [c[3] for c in f.calls if c[:3] == ["gh", "pr", "update-branch"]]
        return rc == OK and updates == ["2"] and "UPDATED #2" in out and "LOCAL #2" not in out, out

    def keystone_apply_refresh_failure_is_warn_not_error():
        # #1130 a post-merge refresh error (e.g. a truncated PR list) used to
        # propagate as ERROR, making a keystone that DID land look failed.
        f = keystone_forge()
        seen = {"list": 0}

        def runner(args, cwd=None, timeout=None):
            if args[:3] == ["gh", "pr", "list"]:
                seen["list"] += 1
                if seen["list"] > 1:  # refresh's own open_prs(), after the merge landed
                    return 0, json.dumps([{}] * 210), ""
            return f(args, cwd=cwd, timeout=timeout)
        buf = io.StringIO()
        rc = run(["keystone", "--base", "main", "--pr", "1", "--verify-cmd", "t", "--only", "src/clock*.py",
                  "--owner-email", OWNER, "--retries", "0", "--apply", "--backoff", "5",
                  "--state", os.path.join(tmp, fresh("kwarn.json"))],
                 runner=runner, out=buf, sleep=f.sleeps.append)
        out = buf.getvalue()
        return (rc == OK and "MERGED #1" in out
                and "WARN keystone #1 landed but refresh failed" in out
                and "pr list hit the 200 limit" in out), out

    def refresh_skips_draft_and_fork_prs():
        f = refresh_forge()
        f.prs[2]["isDraft"] = True
        f.prs[3]["isCrossRepository"] = True
        rc, out = go(f, "refresh", state=fresh("rfdf.json"))
        rc2, out2 = go(f, "refresh", "--include-drafts", "--allow-forks", state=fresh("rfdf.json"))
        return (rc == OK and "SKIP #2 draft" in out and "SKIP #3 fork" in out
                and "LOCAL #2" not in out and "LOCAL #3" not in out
                and "LOCAL #2" in out2 and "LOCAL #3" in out2), (out, out2)

    def refresh_throttles_and_retries_rate_limit():
        f = refresh_forge()
        attempts = {"n": 0}

        def runner(args, cwd=None, timeout=None):
            if args[:3] == ["gh", "pr", "update-branch"] and args[3] == "2":
                attempts["n"] += 1
                if attempts["n"] == 1:
                    return 1, "", "API rate limit exceeded (429)"
            return f(args, cwd=cwd, timeout=timeout)
        buf = io.StringIO()
        rc = run(["refresh", "--use-update-branch", "--apply", "--base", "main", "--retries", "1", "--backoff", "3",
                  "--state", os.path.join(tmp, fresh("rtl.json"))], runner=runner, out=buf, sleep=f.sleeps.append)
        out = buf.getvalue()
        return (rc == OK and attempts["n"] == 2 and "UPDATED #2" in out and "UPDATED #3" in out
                and 3 in f.sleeps), (out, f.sleeps)

    def udiff(path, start, old, new):
        return (f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
                f"@@ -{start} +{start} @@\n-{old}\n+{new}\n")

    CLOCK, OLD, NEW = "tests/test_clock.py", "    assert year == 2025", "    assert year == today().year"
    DUPES = {
        2: udiff(CLOCK, 10, OLD, NEW),
        3: udiff(CLOCK, 10, OLD, "    skip()"),  # same region, a different fix
        4: udiff(CLOCK, 11, OLD, NEW) + udiff("src/other.py", 3, "a", "b"),  # a copy plus its own work
        5: udiff(CLOCK, 10, OLD, "    assert  year == today().year "),  # whitespace-only variant
        6: udiff("tests/test_date.py", 10, OLD, NEW),  # the same text in another file
        7: udiff(CLOCK, 200, OLD, NEW),  # the same text in a far region
    }

    def duplicate_fixes_groups_near_identical_hunks():
        groups, similars = duplicate_fixes(DUPES, 0.9)
        return groups == [((2, 4, 5), [CLOCK])], (groups, similars)

    def duplicate_fixes_different_fixes_to_same_line_not_grouped():
        # #1130 the old scorer matched the shared pre-image ("x = 1") too, so two
        # different one-line fixes to the same line ("-> 2" vs "-> 3") falsely
        # grouped as one; only the post-image may decide a duplicate.
        diffs = {1: udiff("x.py", 5, "x = 1", "x = 2"), 2: udiff("x.py", 5, "x = 1", "x = 3")}
        groups, similars = duplicate_fixes(diffs, 0.9)
        return groups == [], (groups, similars)

    def duplicate_fixes_pure_deletion_compares_pre_image():
        deldiff = lambda path, start, old: (  # noqa: E731
            f"diff --git a/{path} b/{path}\nindex 1..2 100644\n--- a/{path}\n+++ b/{path}\n"
            f"@@ -{start} @@\n-{old}\n")
        # two pure deletions of the same line are a duplicate (no post-image to compare)
        dels = {1: deldiff("x.py", 5, "dead()"), 2: deldiff("x.py", 5, "dead()")}
        del_groups, _ = duplicate_fixes(dels, 0.9)
        # a pure deletion and an edit of the same line are different fixes, never grouped
        mixed = {1: deldiff("x.py", 5, "dead()"), 2: udiff("x.py", 5, "dead()", "live()")}
        mixed_groups, _ = duplicate_fixes(mixed, 0.9)
        return del_groups == [((1, 2), ["x.py"])] and mixed_groups == [], (del_groups, mixed_groups)

    def dupes_names_the_earliest_pr_canonical():
        f = FakeForge(7)
        f.udiffs = {f"h{n}": d for n, d in DUPES.items()}
        rc, out = go(f, "dupes", state=fresh("du.json"))
        g = FakeForge(2)
        rc2, out2 = go(g, "dupes", state=fresh("du.json"))
        return (rc == RED and f"DUP-FIX #2,#4,#5 canonical=#2 files={CLOCK}" in out
                and "one fix, one PR: #4,#5 drop their copy and rebase on #2" in out
                and rc2 == OK and "NOOP" in out2), (out, out2)

    def duplicate_fixes_parses_real_git_diff():
        repo = tempfile.mkdtemp(dir=tmp)

        def git(*args):
            rc, out, err = default_runner(["git", "-c", "user.name=T", "-c", "user.email=t@example.com",
                                           "-c", "commit.gpgsign=false", *args], cwd=repo)
            assert rc == 0, err
            return out

        def branch(name, text):
            git("checkout", "--quiet", "-B", name, "main")
            with open(os.path.join(repo, "t.py"), "w", encoding="utf-8") as fh:
                fh.write(text)
            git("commit", "--quiet", "-am", name)
        git("init", "--quiet", "-b", "main")
        with open(os.path.join(repo, "t.py"), "w", encoding="utf-8") as fh:
            fh.write("a\n-- note\nold\nz\n")  # a removed "-- note" shows as "--- note" inside the hunk
        git("add", "-A")
        git("commit", "--quiet", "-m", "base")
        branch("one", "a\n-- note fixed\nnew\nz\n")
        branch("two", "a\n-- note  fixed\nnew \nz\n")
        branch("three", "a\n-- note\nsomething else entirely\nz\n")
        diffs = {n: git("diff", "-U0", "--no-renames", "--no-color", f"main...{b}")
                 for n, b in ((1, "one"), (2, "two"), (3, "three"))}
        groups, similars = duplicate_fixes(diffs, 0.9)
        return groups == [((1, 2), ["t.py"])], (groups, similars, diffs)

    def listen(buf, suffix):
        """Runner hook: on the first `git ls-remote`, drop `<run-id>.<suffix>` into the state dir (the run id is read from `RUN`)."""
        def hook(args, cwd=None, timeout=None, _done=[]):  # noqa: B006 — one use per test
            if args[:2] == ["git", "ls-remote"] and not _done:
                _done.append(1)
                open(os.path.join(tmp, re.search(r"RUN (\S+)", buf.getvalue()).group(1) + suffix), "w").close()
        return hook

    def cancel_mid_wait_releases_and_exits_zero():
        f = FakeForge(1)
        st = verified(f, "cx.json")
        f.view_override = {1: {"mergeable": "UNKNOWN"}}  # still_ready backs off, which is a cancel point
        buf = io.StringIO()

        def sleeper(_):
            open(os.path.join(tmp, re.search(r"RUN (\S+)", buf.getvalue()).group(1) + ".cancel"), "w").close()

        rc = run(["merge", "--apply", "--grant", "g", "--base", "main", "--state", os.path.join(tmp, st), "--backoff", "5"],
                 runner=f, out=buf, sleep=sleeper)
        out = buf.getvalue()
        return (rc == OK and "CANCELLED" in out and not any(c[:3] == ["gh", "pr", "merge"] for c in f.calls)
                and any(c[:3] == ["git", "update-ref", "-d"] for c in f.calls)
                and not [n for n in os.listdir(tmp) if n.endswith(".cancel")]), (rc, out)

    def drop_file_removes_member_and_replans():
        f, buf = FakeForge(3), io.StringIO()
        hook = listen(buf, ".drop-2")
        runner = lambda args, cwd=None, timeout=None: (hook(args), f(args, cwd=cwd, timeout=timeout))[1]  # noqa: E731
        rc = run(["verify", "--verify-cmd", "t", "--base", "main", "--state", os.path.join(tmp, fresh("dr.json")),
                  "--backoff", "5"], runner=runner, out=buf, sleep=f.sleeps.append)
        out = buf.getvalue()
        with open(os.path.join(tmp, "dr.json")) as fh:
            kept = [m["number"] for m in json.load(fh)["members"]]
        return (rc == OK and "DROPPED #2" in out and "GREEN base=B0 members=#1,#3" in out and kept == [1, 3]
                and f.gates == [(1, 3)] and not [n for n in os.listdir(tmp) if ".drop-" in n]), (out, f.gates)

    def carry_setup(runs):
        f = FakeForge(1)
        st = verified(f, "cr.json")  # records h1 as green
        f.prs[1]["head"], f.prs[1]["runs"] = "h1b", runs
        return f, st

    def receipt_carries_only_on_equal_patch_id():
        f, st = carry_setup([_run("ci", None, status="in_progress")])
        f.dpid = {"h1": "pidA", "h1b": "pidA"}
        rc, out = go(f, "plan", state=st)
        return (rc == OK and "CARRIED h1->h1b #1" in out and "ELIGIBLE #1 h1b" in out), out

    def changed_patch_id_or_red_check_does_not_carry():
        pend = _run("ci", None, status="in_progress")

        def plan_out(runs, old, new):
            f, st = carry_setup(runs)
            f.dpid = {"h1": old, "h1b": new}
            return go(f, "plan", state=st)[1]

        control = plan_out([pend], "+x = 1\n", "+x = 1\n")  # same setup as the negatives, equal diff: carries
        changed = plan_out([pend], "+x = 1\n", "+x = 2\n")  # a real change, not a base-merge-only move
        spaced = plan_out([pend], "+x = 1\n", "+x = 1 \n")  # whitespace-only change: a patch-id would match, raw diff does not
        red = plan_out([_run("ci", "failure")], "+x = 1\n", "+x = 1\n")  # own red check: never carried
        mixed = plan_out([pend, _run("lint", "failure")], "+x = 1\n", "+x = 1\n")  # pending sorts first, red still blocks
        return ("CARRIED h1->h1b #1" in control and "ELIGIBLE #1 h1b" in control
                and "CARRIED" not in changed and "SKIP #1 check ci=in_progress" in changed
                and "CARRIED" not in spaced and "SKIP #1 check ci=in_progress" in spaced
                and "CARRIED" not in red and "SKIP #1 check ci=failure" in red
                and "CARRIED" not in mixed and "SKIP #1" in mixed), (control, changed, spaced, red, mixed)

    cases = [
        ("plan-filters-latest-check-per-name-and-K", plan_filters),
        ("culprit-among-four-isolated-and-stays-parked", culprit_among_four_is_isolated_and_stays_parked),
        ("conflicts-all-parked-in-one-cycle-no-sleep", conflicts_all_parked_in_one_cycle_without_sleeping),
        ("flaky-passes-on-retry-bounded-backoff", flaky_passes_on_retry_with_bounded_backoff),
        ("deterministic-failure-parks-member", deterministic_failure_parks_member),
        ("all-members-bad-is-red", all_members_bad_is_red),
        ("red-base-halts", red_base_halts),
        ("verify-and-dry-run-post-no-status", verify_and_dry_run_post_nothing),
        ("apply-posts-success-then-merges", apply_posts_success_then_merges),
        ("base-moved-after-verify-posts-nothing", base_moved_after_verify_posts_nothing),
        ("failed-merge-overwrites-with-error", failed_merge_overwrites_with_error),
        ("no-status-flag-posts-nothing", no_status_flag_posts_nothing),
        ("failed-status-post-warns-never-claims-posted", failed_status_post_warns_never_claims_posted),
        ("ratchet-overshoot-attributed-per-member", ratchet_overshoot_attributed_per_member),
        ("dry-run-is-default", dry_run_is_default),
        ("apply-needs-grant", apply_needs_grant),
        ("apply-merges-back-to-back", apply_merges_back_to_back),
        ("base-moved-halts-without-reverify", base_moved_halts_without_reverify),
        ("base-rewritten-halts", base_rewritten_halts),
        ("intruder-mid-train-halts", intruder_mid_train_halts),
        ("merge-time-conflict-parks-and-halts", merge_time_conflict_parks_and_halts),
        ("unknown-mergeable-polls-then-parks", unknown_mergeable_polls_then_parks),
        ("push-refused-before-runner", push_is_refused_before_the_runner),
        ("forge-outage-fails-closed", forge_outage_fails_closed),
        ("untrusted-text-sanitised", untrusted_text_is_sanitised),
        ("restart-after-crash-fetches-fresh-and-sweeps-dead-refs", restart_after_crash_fetches_fresh_and_sweeps_dead_refs),
        ("same-run-refetch-updates-non-fast-forward-ref", same_run_refetch_updates_non_fast_forward_ref),
        ("failed-fetch-halts-cycle", failed_fetch_halts_cycle),
        ("drifted-member-skipped-not-the-cycle", drifted_member_is_skipped_not_the_cycle),
        ("raced-member-retried-then-skipped", raced_member_retried_then_skipped),
        ("vanished-pr-ref-skipped-not-fetched", vanished_pr_ref_is_skipped_not_fetched),
        ("raced-base-retried-then-errors", raced_base_retried_then_errors),
        ("drop-failure-logged-never-raises", drop_failure_is_logged_and_never_raises),
        ("post-merge-fetch-mismatch-halts-after-merged-line", post_merge_fetch_mismatch_halts_after_merged_line),
        ("non-int-pr-number-rejected", non_int_pr_number_is_rejected),
        ("keystone-proves-parks-cherry-pick-dry-runs", keystone_proves_parks_cherry_pick_and_dry_runs),
        ("keystone-apply-spends-grant-in-merge-commit", keystone_apply_merges_alone_spends_grant_in_merge_commit),
        ("keystone-refused-on-green-base", keystone_refused_on_green_base),
        ("keystone-refused-when-union-stays-red", keystone_refused_when_union_stays_red),
        ("keystone-refused-outside-only-before-gate", keystone_refused_outside_only_before_any_gate),
        ("keystone-refused-wrong-target-branch", keystone_refused_wrong_target_branch),
        ("keystone-runs-eligibility-before-any-gate", keystone_runs_eligibility_before_any_gate),
        ("keystone-grant-owner-pinned-hardened", keystone_grant_owner_authored_pinned_and_hardened),
        ("keystone-parks-squash-copies-and-touchers", keystone_parks_squash_copies_and_touchers),
        ("keystone-record-screens-repushed-siblings", keystone_record_screens_repushed_siblings_until_it_lands),
        ("keystone-record-clears-merged-or-ancestor", keystone_record_clears_on_merged_state_or_ancestor_head),
        ("keystone-conflict-halts-cleanly", keystone_conflict_halts_cleanly),
        ("keystone-globs-need-literal-directory", keystone_globs_need_a_literal_directory_prefix),
        ("class-grant-spent-only-by-apply", class_grant_spent_only_by_apply_until_a_new_owner_commit),
        ("class-grant-refusals", class_grant_refusals),
        ("class-grant-picks-unused-covering-class", class_grant_picks_the_unused_class_that_covers_the_files),
        ("keystone-git-helpers-on-a-real-repo", keystone_git_helpers_on_a_real_repo),
        ("refresh-default-prints-local-no-ci-cost", refresh_default_prints_local_commands_no_ci_cost),
        ("refresh-local-command-exact-repo-flag", refresh_local_command_is_exact_and_carries_repo_flag),
        ("refresh-use-update-branch-dry-run", refresh_use_update_branch_dry_run_prints_gh_command),
        ("refresh-apply-updates-reports-failures", refresh_apply_updates_and_reports_each_failure),
        ("refresh-since-pins-the-fix-commit", refresh_since_pins_the_fix_commit),
        ("keystone-apply-refresh-local-default", keystone_apply_refresh_follows_local_default_no_ci_cost),
        ("keystone-use-update-branch-parity", keystone_use_update_branch_opts_into_gh_update_branch),
        ("duplicate-fixes-groups-near-identical", duplicate_fixes_groups_near_identical_hunks),
        ("dupes-names-earliest-canonical", dupes_names_the_earliest_pr_canonical),
        ("duplicate-fixes-parses-real-git-diff", duplicate_fixes_parses_real_git_diff),
        ("duplicate-fixes-different-fixes-not-grouped", duplicate_fixes_different_fixes_to_same_line_not_grouped),
        ("duplicate-fixes-pure-deletion-pre-image", duplicate_fixes_pure_deletion_compares_pre_image),
        ("keystone-apply-refresh-failure-is-warn-not-error", keystone_apply_refresh_failure_is_warn_not_error),
        ("refresh-skips-draft-and-fork-prs", refresh_skips_draft_and_fork_prs),
        ("refresh-throttles-and-retries-rate-limit", refresh_throttles_and_retries_rate_limit),
        ("cancel-mid-wait-releases-and-exits-zero", cancel_mid_wait_releases_and_exits_zero),
        ("drop-file-removes-member-and-replans", drop_file_removes_member_and_replans),
        ("receipt-carries-only-on-equal-patch-id", receipt_carries_only_on_equal_patch_id),
        ("changed-patch-id-or-red-check-does-not-carry", changed_patch_id_or_red_check_does_not_carry),
    ]
    try:
        return bc.run_checks("merge_train", cases)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv=None) -> int:
    """CLI entry point. Returns the process exit code."""
    argv = sys.argv[1:] if argv is None else argv
    if "--selftest" in argv:
        return _selftest()
    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
