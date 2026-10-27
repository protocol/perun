#!/usr/bin/env python3
"""perun_auto_update.py — keep an installed Perun current with no manual step and no restart.

Wired by `install.sh --apply-operating-layer` as a SessionStart and a UserPromptSubmit hook (the
second is the periodic check for long sessions). Claude Code live-reloads skills and settings, so
an update applied mid-session takes effect without a restart.

Hook mode (no args): returns at once. Skips when the policy key `auto_update` is `off` or when the
per-project stamp under `$XDG_CACHE_HOME/perun/auto-update/` (default `~/.cache`) is younger than 6h;
otherwise touches the stamp and spawns `--run` detached (new session, stdio to /dev/null), so no
network wait ever lands on the session start path. Prints nothing (hook stdout would enter context).

`--run [--target DIR]` (the background worker, also runnable by hand): under one machine-wide
flock, it reads `.claude/.perun-install.json` (`version`, `remote`), skips when the target has a
merge, rebase, cherry-pick or train lock (`MERGE_HEAD`, `CHERRY_PICK_HEAD`, `rebase-merge/`,
`rebase-apply/`, `train-land.lock` in its own or common git dir; in a linked `worktrees/*/` dir only a
`train-land.lock` under 24h old), when a Perun-managed
file differs from the hash install recorded, or when `git status` shows uncommitted changes to a
managed path or `.claude/settings.local.json`. It finds the newest `vX.Y.Z` tag on the remote
(`git ls-remote`); when it is newer it fetches the tag into a cache clone
(`$XDG_CACHE_HOME/perun/src`) without `--force` (a local tag that moved is refused), aborts unless
the tag's commit is an ancestor of the remote's `main` and the tree's `SHA256SUMS` verifies, then
runs that tag's `scripts/update-installed.sh TARGET` (`DCR_NO_PULL=1`), which replays the recorded
install flags. SHA256SUMS covers the skill files only (not install.sh or scripts/) and ships in the same tag, so it
proves skill-file integrity (no corrupt or partial checkout), not authenticity: trust rests on the repository owner's tags and `main`. install.sh keeps existing user
settings, writes a `.bak` and skill backups. When the policy key `auto_update_pr` is `on` (default), after a
successful update or an up-to-date check the worker also opens a `perun/update-v<ver>` PR (see `update_pr`) so the
Perun copy committed on the default branch catches up; it never auto-merges and never touches the checkout. Every worker run appends one line to
`$XDG_CACHE_HOME/perun/auto-update.log`. Exit 0 always in hook mode; `--run` exits 0 on
skip/up-to-date/updated, 1 when the update itself failed.

A target with `.claude/.dcr-install-flags` but no marker is a legacy install: `legacy_marker` takes the version from the
installed SKILL.md (inside a closed frontmatter block only) and the canonical remote, and the update writes the real
marker. Only git locks and an uncommitted `settings.local.json` skip a legacy install; uncommitted skill edits are
preserved by install.sh's backup, not by a skip. A cache clone whose origin is not the canonical remote is a logged skip.
Stdlib only; a missing marker, remote or parseable version is a logged skip, never a guess.
"""
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perun_policy  # noqa: E402

THROTTLE = 6 * 3600
STALE_LOCK = 24 * 3600  # a lock in a linked worktree older than this is leftover, not a live operation
SKIP_WARN_AT = 3  # consecutive skips with the same reason before behind_warn surfaces it
CANONICAL_REMOTE = "https://github.com/protocol/perun.git"  # same as install.sh's fallback
LEGACY_REMOTE = "https://github.com/remigiusz-antczak/deep-code-review.git"  # pre-move home: accepted only to migrate to CANONICAL_REMOTE


def _norm(url: str) -> str:
    return url.strip().rstrip("/").removesuffix(".git")


def is_canonical(url: str) -> bool:
    """True for the canonical or the legacy remote (exact match modulo a trailing `/` or `.git`); any other URL is foreign."""
    return _norm(url) in (_norm(CANONICAL_REMOTE), _norm(LEGACY_REMOTE))
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def cache() -> Path:
    """Perun's user cache dir: `$XDG_CACHE_HOME/perun`, else `~/.cache/perun` (same root as perun_policy)."""
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "perun"


def log(target: Path, msg: str) -> None:
    """Append one timestamped line for `target` to the local log (credentials in URLs redacted: `://user:token@` ->
    `://***@`). Side effect: creates the cache dir."""
    msg = re.sub(r"://[^/@\s]+@", "://***@", msg)
    cache().mkdir(parents=True, exist_ok=True)
    with open(cache() / "auto-update.log", "a") as f:
        f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S%z')} {target} {msg}\n")


def stamp(target: Path) -> Path:
    """Per-project throttle stamp; the name hashes the absolute path so projects never share one."""
    return cache() / "auto-update" / (hashlib.sha256(str(target).encode()).hexdigest()[:16] + ".stamp")


def enabled(target: Path, key: str = "auto_update") -> bool:
    """True when the policy found from `target` has `<key>: on`. A malformed policy fails closed (False)."""
    try:
        return perun_policy.load(perun_policy.find_policy(str(target)))[key] == "on"
    except ValueError:
        return False


def hook(target: Path, now: float | None = None) -> bool:
    """Hook fast path: True when a background worker was spawned. No network, no git, no waiting."""
    now = time.time() if now is None else now
    s = stamp(target)
    if not enabled(target) or (s.is_file() and now - s.stat().st_mtime < THROTTLE):
        return False
    s.parent.mkdir(parents=True, exist_ok=True)
    s.write_text(f"{int(now)}\n")  # before the spawn, so a second session in the window does not double-run
    subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--run", "--target", str(target)], start_new_session=True,
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return True


def version(s: str) -> tuple | None:
    """`1.2.3` or `v1.2.3` as an int tuple; None for anything else."""
    m = TAG.match(s if s.startswith("v") else "v" + s)
    return tuple(int(x) for x in m.groups()) if m else None


def git(*args: str, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], capture_output=True, text=True, timeout=timeout,
                          env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})


LOCKS = ("MERGE_HEAD", "CHERRY_PICK_HEAD", "rebase-merge", "rebase-apply", "train-land.lock")


def _newest(lock: Path) -> float:
    """Latest mtime of `lock` and, for a directory lock (rebase-merge), its direct children, so an operation
    still being worked on is not called stale. A path that vanished or cannot be read counts as fresh (now)."""
    try:
        return max(p.stat().st_mtime for p in [lock, *(lock.iterdir() if lock.is_dir() else [])])
    except OSError:
        return time.time()


def blocker(target: Path, marker: dict) -> str:
    """Why an update must wait ('' when clear): a merge/rebase/cherry-pick/train lock in this checkout's own or
    common git dir, a train lock under 24h old in a linked worktree (a linked worktree's own merge or rebase never blocks), a managed file edited since install, or uncommitted git changes to a managed path
    or `.claude/settings.local.json` (untracked files do not count; other settings files are never written by an
    update, so their edits do not block)."""
    gd = git("-C", str(target), "rev-parse", "--absolute-git-dir", "--git-common-dir")
    if gd.returncode == 0:
        own, common = gd.stdout.split("\n")[:2]
        common = target / common  # relative to the -C dir when not absolute; an absolute path wins in `/`
        mine = {Path(own).resolve(), common.resolve()}
        linked = {d for d in (common / "worktrees").glob("*") if d.resolve() not in mine}
        for d in [Path(own), common, *sorted(linked)]:
            for lock in LOCKS:
                if (d / lock).exists():
                    # a lane merging or rebasing in its own linked worktree has its own checkout: the update never
                    # writes there, and in a busy fleet one such merge is always in progress. Only a train lock counts.
                    if d in linked and (lock != "train-land.lock" or time.time() - _newest(d / lock) > STALE_LOCK):
                        log(target, f"ignoring {lock} in linked worktree {d}")
                        continue
                    return f"{lock} present in {d}"
    files = [(Path(d) / f, h) for d, fs in marker.get("skills", {}).items() for f, h in fs.items()]
    if marker.get("agent"):
        files.append((Path(marker["agent"]["path"]), marker["agent"]["sha"]))
    for rel, h in files:
        p = target / rel
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
            return f"dirty Perun-managed file {rel}"
    clean = {str(rel) for rel, _ in files}  # sha matched the marker: an install over an older commit, not a user edit
    paths = [*marker.get("skills", {}), *([marker["agent"]["path"]] if marker.get("agent") else []),
             ".claude/settings.local.json"]  # the one settings file an update rewrites; a team's tracked settings.json is never touched
    # --relative + -z: names relative to target and unquoted, so a subdirectory target or a path with spaces compares exactly
    st = git("-C", str(target), "diff", "--name-only", "-z", "--relative", "HEAD", "--", *paths)
    left = [l for l in st.stdout.split("\0") if l and l not in clean] if st.returncode == 0 else []
    return f"uncommitted changes: {left[0]}" if left else ""


def skips(target: Path, why: str | None) -> int:
    """Consecutive-skip counter for `target` in the cache dir: record one more skip for `why`, or clear it when
    `why` is empty. Returns the count of consecutive skips with the same reason (0 when cleared)."""
    f = stamp(target).with_suffix(".skips")
    n, _, prev = f.read_text().partition("\n") if f.is_file() else ("0", "", "")
    if not why:
        f.unlink(missing_ok=True)
        return 0
    n = int(n) + 1 if prev == why and n.isdigit() else 1
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(f"{n}\n{why}")
    return n


VER = ".claude/skills/deep-code-review/VERSION"


def pr_base(target: Path) -> str:
    """Policy `auto_update_pr_base` ('' when unset or the policy is malformed)."""
    try:
        return perun_policy.load(perun_policy.find_policy(str(target)))["auto_update_pr_base"]
    except ValueError:
        return ""


def default_ref(target: Path) -> str:
    """The integration branch as a ref: policy `auto_update_pr_base` as `origin/<base>` when set (never guessed:
    '' if that branch is not on origin), else `origin/HEAD`'s target, `origin/main`, `origin/master`; '' when none exists."""
    base = pr_base(target)
    if base:
        return f"origin/{base}" if git("-C", str(target), "rev-parse", "-q", "--verify", f"refs/remotes/origin/{base}").returncode == 0 else ""
    h = git("-C", str(target), "symbolic-ref", "-q", "--short", "refs/remotes/origin/HEAD")
    for ref in ([h.stdout.strip()] if h.returncode == 0 else []) + ["origin/main", "origin/master"]:
        if git("-C", str(target), "rev-parse", "-q", "--verify", ref).returncode == 0:
            return ref
    return ""


def committed_behind(target: Path) -> tuple | None:
    """`(committed, installed)` version strings when the Perun copy committed on the default branch is older
    than the working tree's; None when current, unreadable, no default ref, or no install marker (not an install). Local refs only, no network."""
    # only an INSTALLED target: Perun's own source repo is ahead of its default branch on every release branch
    if not (target / ".claude" / ".perun-install.json").is_file():
        return None
    ref = default_ref(target)
    try:
        have = (target / VER).read_text().strip()
    except OSError:
        return None
    r = git("-C", str(target), "show", f"{ref}:{VER}", timeout=5) if ref else None
    if not r or r.returncode != 0 or not version(have) or not version(r.stdout.strip()):
        return None
    return (r.stdout.strip(), have) if version(r.stdout.strip()) < version(have) else None


def behind_warn(target: Path) -> str | None:
    """The WARN line for `committed_behind` and/or an auto-update blocked `SKIP_WARN_AT`+ runs in a row for one
    reason (see `skips`), joined with `; ` on one line; None when neither."""
    b = committed_behind(target)
    f = stamp(target).with_suffix(".skips")
    n, _, why = f.read_text().partition("\n") if f.is_file() and enabled(target) else ("0", "", "")
    parts = [b and f"committed Perun v{b[0]} < installed v{b[1]}: lanes in other worktrees run old skills; "
             "open/merge the perun/update PR",
             n.isdigit() and int(n) >= SKIP_WARN_AT and f"auto-update skipped {n} runs in a row: {why}"]
    parts = [x for x in parts if x]
    return "WARN: " + "; ".join(parts) if parts else None


def pr_open(branch: str, cwd: Path) -> bool | None:
    """True when an OPEN PR for `branch` exists, False when none, None when unknown (gh missing or failing)."""
    try:
        r = subprocess.run(["gh", "pr", "list", "--head", branch, "--state", "open", "--json", "number"],
                           capture_output=True, text=True, timeout=60, cwd=cwd)
        return bool(json.loads(r.stdout)) if r.returncode == 0 else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def pr_create(branch: str, base: str, ver: str, cwd: Path) -> str:
    """Open the PR; '' on success else the failure line. `gh pr create`, falling back to the gh_rest.py curl path
    (`gh api -X POST .../pulls`) when gh fails or is missing (e.g. the sandbox TLS error)."""
    title, body = f"Update Perun skills to v{ver}", "Automated Perun update. Review and merge; nothing here auto-merges."
    try:
        if subprocess.run(["gh", "pr", "create", "--head", branch, "--base", base, "--title", title, "--body", body],
                          capture_output=True, text=True, timeout=120, cwd=cwd).returncode == 0:
            return ""
    except (OSError, subprocess.SubprocessError):
        pass  # gh missing or hung: the REST path below
    import gh_rest
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"title": title, "body": body, "head": branch, "base": base}, f)
    args = ["gh", "api", "-X", "POST", "repos/{owner}/{repo}/pulls", "--input", f.name]
    try:
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=120, cwd=cwd)
            rc, out, err = r.returncode, r.stdout, r.stderr
        except (OSError, subprocess.SubprocessError):
            rc, out, err = 1, "", "failed to verify certificate"  # gh unusable: force the curl path
        cwd0 = os.getcwd()
        os.chdir(cwd)  # gh_rest resolves {owner}/{repo} from the cwd's origin
        try:
            rc, out, err = gh_rest.fallback(args, rc, out, err)
        finally:
            os.chdir(cwd0)
    finally:
        os.unlink(f.name)
    return "" if rc == 0 else (err.strip().splitlines() or ["?"])[-1]


HOOK_TIMEOUT = 1800  # commit/push run the repo's own hooks (never bypassed); bound them


def managed_files(target: Path, marker: dict) -> list:
    """Repo-relative files the marker recorded as installed (skill-file hashes plus slash commands) that exist in
    `target` as regular, non-symlink files inside it. Untracked user files, symlinks and `..`/absolute paths never qualify."""
    root, out = target.resolve(), []
    rels = [f"{d}/{f}" for d, fs in marker.get("skills", {}).items() for f in fs] + list(marker.get("files", {}))
    for rel in rels:
        pr = Path(rel)
        p = target / pr
        if pr.is_absolute() or ".." in pr.parts or p.is_symlink() or not p.is_file() or not p.resolve().is_relative_to(root):
            continue
        out.append(rel)
    return out


def update_pr(target: Path) -> str:
    """Land the installed Perun on the default branch as a PR; returns the one-line outcome for the log.
    Never touches `target`'s checkout: works in a throwaway detached worktree off `origin/<default>`, copies only
    the marker-recorded managed files (`managed_files`), stages exactly those paths, commits, pushes
    `perun/update-v<ver>` (never forced) and opens a PR (never merged). Idempotent: skips when the committed
    version is already >= installed, when an OPEN PR for the branch exists, or when the copy changes nothing; a
    branch pushed earlier whose PR creation failed is retried (PR only). Commit/push hooks are never bypassed, but
    time out after HOOK_TIMEOUT: the worktree is removed and the outcome is `hooks timed out`."""
    try:
        marker = json.loads((target / ".claude/.perun-install.json").read_text())
        ver = (target / VER).read_text().strip()
    except (OSError, ValueError):
        return "pr skip: no readable marker or VERSION"
    if not version(ver):
        return "pr skip: unparseable installed version"
    top = git("-C", str(target), "rev-parse", "--show-toplevel").stdout.strip()
    if not top or os.path.realpath(top) != os.path.realpath(target):  # not a repo root (a dir nested in a parent repo counts as non-git)
        return "pr skip: target is not a git repo (global install)"
    if git("-C", str(target), "fetch", "-q", "origin", timeout=300).returncode != 0:
        return "pr skip: fetch origin failed"
    ref = default_ref(target)
    if not ref:
        b = pr_base(target)
        return f"pr skip: auto_update_pr_base {b!r} not found on origin" if b else "pr skip: no default branch ref"
    if not committed_behind(target):
        return f"pr skip: committed version on {ref} is not behind {ver}"
    branch, base = f"perun/update-v{ver}", ref.split("/", 1)[1]
    if pr_open(branch, target):
        return f"pr skip: open PR for {branch} exists"
    if git("-C", str(target), "ls-remote", "--heads", "origin", branch).stdout.strip():  # pushed, PR missing: retry the PR only
        err = pr_create(branch, base, ver, target)
        return f"pr failed: create: {err}" if err else f"pr opened: {branch} -> {base} (branch already pushed)"
    paths = managed_files(target, marker)
    if not paths:
        return "pr skip: no managed files recorded"
    with tempfile.TemporaryDirectory(prefix="perun-pr-") as tmp:
        wt = Path(tmp) / "wt"
        if git("-C", str(target), "worktree", "add", "-q", "--detach", str(wt), ref).returncode != 0:
            return "pr failed: worktree add"
        try:
            for rel in paths:
                (wt / rel).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target / rel, wt / rel)
            git("-C", str(wt), "add", "--", *paths)
            if not git("-C", str(wt), "diff", "--cached", "--name-only").stdout.strip():
                return "pr skip: managed paths already match the default branch"
            c = git("-C", str(wt), "-c", "user.name=perun-auto-update", "-c", "user.email=perun-auto-update@users.noreply.github.com",
                    "commit", "-q", "-m", f"Update Perun skills to v{ver}", timeout=HOOK_TIMEOUT)
            if c.returncode != 0:
                return f"pr failed: commit: {(c.stderr.strip().splitlines() or ['?'])[-1]}"
            p = git("-C", str(wt), "push", "-q", "origin", f"HEAD:refs/heads/{branch}", timeout=HOOK_TIMEOUT)
            if p.returncode != 0:
                return f"pr failed: push: {(p.stderr.strip().splitlines() or ['?'])[-1]}"
            err = pr_create(branch, base, ver, wt)
            return f"pr failed: create: {err}" if err else f"pr opened: {branch} -> {base}"
        except subprocess.TimeoutExpired:
            return "pr failed: hooks timed out"
        finally:
            git("-C", str(target), "worktree", "remove", "--force", str(wt))
            git("-C", str(target), "worktree", "prune")


def pr_step(target: Path) -> None:
    """Run `update_pr` when policy `auto_update_pr` is on; log the outcome; never raises."""
    if not enabled(target, "auto_update_pr"):
        return
    try:
        log(target, update_pr(target))
    except Exception as e:  # silent to the agent: the log is the only record
        log(target, f"pr failed: {type(e).__name__}: {e}")


def verify_sums(src: Path) -> str:
    """'' when every `SHA256SUMS` line in the checkout matches; else the first mismatch. Missing file fails."""
    sums = src / "SHA256SUMS"
    if not sums.is_file():
        return "no SHA256SUMS"
    for line in sums.read_text().splitlines():
        h, _, rel = line.partition("  ")
        p = src / rel
        if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest() != h:
            return f"SHA256SUMS mismatch: {rel}"
    return ""


def legacy_marker(target: Path) -> dict | None:
    """Synthetic marker for a pre-`.perun-install.json` install (the target has `.claude/.dcr-install-flags`): the
    installed deep-code-review SKILL.md frontmatter `version:` plus the canonical remote. It carries no `skills`
    hashes, so hash-drift cannot be checked and `blocker` guards only the git locks and an uncommitted
    `.claude/settings.local.json`; uncommitted edits to the skill files are preserved by install.sh's backup of the
    skill dirs it replaces, not by a skip. None when it is not an install, the version is unreadable, or SKILL.md
    has no properly closed `---` frontmatter block (`version:` is parsed only inside it). The update then writes
    the real marker, so this path is one-time."""
    if not (target / ".claude/.dcr-install-flags").is_file():
        return None
    try:
        text = (target / ".claude/skills/deep-code-review/SKILL.md").read_text()
    except OSError:
        return None
    fm = re.match(r"---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", text, re.S)
    m = fm and re.search(r"^\s*version:\s*[\"']?([0-9.]+)", fm.group(1), re.M)
    return {"version": m.group(1), "remote": CANONICAL_REMOTE} if m and version(m.group(1)) else None


RULES = ("reply_cap", "decision_gate", "handback_cap", "subagent_start_inject", "lane_liveness")  # install.sh --global-rules copies these


def announce_rules(src: Path, target: Path) -> None:
    """After an update: when the machine-wide rules copies differ from the new source, record the owner command (host_installer.py) and log the `! ` line. Fails open."""
    try:
        home = Path.home() / ".claude/perun-rules"
        scripts = src / ".claude/skills/agentic-delivery/scripts"
        if home.is_dir() and any((home / f"{n}.py").read_bytes() != (scripts / f"{n}.py").read_bytes() for n in RULES if (home / f"{n}.py").exists()):
            sys.path.insert(0, str(Path(__file__).resolve().parent))
            import host_installer
            log(target, "global rules out of date, owner runs: " + host_installer.announce("global-rules", src))
    except Exception as e:
        log(target, f"installer announce skipped: {e}")


def run(target: Path) -> int:
    """Background worker body (see module doc). Returns 0 skip/current/updated, 1 failed update."""
    cache().mkdir(parents=True, exist_ok=True)
    with open(cache() / "auto-update.lock", "w") as lk:
        fcntl.flock(lk, fcntl.LOCK_EX)  # one worker per machine: the cache clone is shared
        mf = target / ".claude/.perun-install.json"
        legacy = False
        try:
            marker = json.loads(mf.read_text())
        except (OSError, ValueError):
            legacy = not mf.exists()
            marker = legacy_marker(target) if legacy else None
            if marker is None:
                log(target, "skip: no readable install marker")
                return 0
            log(target, f"legacy install (no .perun-install.json): treating as {marker['version']} from {marker['remote']}")
        remote = marker.get("remote")
        have = version(marker.get("version") or "")
        if not remote or have is None:
            log(target, "skip: install marker has no remote or version (reinstall once to record them)")
            return 0
        if is_canonical(remote):  # a legacy-home install migrates: fetch from the canonical remote, not the old one
            remote = CANONICAL_REMOTE
        why = blocker(target, marker)
        skips(target, why)
        if why:
            log(target, f"skip: {why}")
            return 0
        src = cache() / "src"
        if legacy and (src / ".git").is_dir():  # install.sh records the clone's origin: a legacy install must never inherit a foreign one
            o = git("-C", str(src), "remote", "get-url", "origin").stdout.strip()
            if not is_canonical(o):
                log(target, f"skip: cache clone origin {o or '(none)'} is not the canonical remote")
                return 0
        ls = git("ls-remote", "--tags", "--refs", remote)
        if ls.returncode != 0:
            log(target, f"skip: cannot list tags on {remote}")
            return 0
        tags = [r.split("refs/tags/", 1)[1] for r in ls.stdout.split() if r.startswith("refs/tags/")]
        newest = max((t for t in tags if version(t)), key=version, default=None)
        if newest is None or version(newest) <= have:
            log(target, f"up to date at {marker['version']}")
            pr_step(target)  # also here: a past update may never have reached the default branch
            return 0
        steps =([] if (src / ".git").is_dir() else [["clone", "-q", "--no-checkout", remote, str(src)]]) + [
            ["-C", str(src), "fetch", "-q", remote, f"refs/tags/{newest}:refs/tags/{newest}",
             "+refs/heads/main:refs/remotes/origin/main"],  # no --force on tags: a moved tag is refused
            ["-C", str(src), "-c", "advice.detachedHead=false", "checkout", "-q", "-f", "--detach", newest]]
        for step in steps:
            r = git(*step, timeout=600)
            if r.returncode != 0:
                log(target, f"failed {marker['version']} -> {newest}: git {next(x for x in step if x in ('clone', 'fetch', 'checkout'))}: "
                    f"{(r.stderr.strip().splitlines() or ['?'])[-1]}")
                return 1
        why = ("" if git("-C", str(src), "merge-base", "--is-ancestor", f"refs/tags/{newest}",
                         "refs/remotes/origin/main").returncode == 0 else f"{newest} is not an ancestor of main")
        why = why or verify_sums(src)
        if why:
            log(target, f"failed {marker['version']} -> {newest}: aborted, {why}")
            return 1
        r = subprocess.run(["bash", str(src / "scripts/update-installed.sh"), str(target)], capture_output=True,
                           text=True, timeout=600, env={**os.environ, "DCR_NO_PULL": "1", "PERUN_REMOTE": remote})  # install.sh re-records this, not the clone origin
        if r.returncode != 0:
            log(target, f"failed {marker['version']} -> {newest}: update-installed.sh exit {r.returncode}: "
                f"{((r.stderr or r.stdout).strip().splitlines() or ['?'])[-1]}")
            return 1
        log(target, f"updated {marker['version']} -> {newest} (backups: .claude/settings.local.json.bak.*, skill-backups/)")
        announce_rules(src, target)
        pr_step(target)
        return 0


def main(argv: list) -> int:
    target = Path(argv[argv.index("--target") + 1] if "--target" in argv
                  else os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()).resolve()
    if "--run" in argv:
        try:
            return run(target)
        except (OSError, subprocess.TimeoutExpired) as e:
            log(target, f"failed: {type(e).__name__}: {e}")
            return 1
    try:
        hook(target)
    except OSError:
        pass  # a hook must never break session start
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
