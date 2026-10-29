#!/usr/bin/env python3
"""lkg.py — last-known-good (LKG) pointer: the newest commit on which the full ci-tests suite passed.

`record [sha]` (run after the suite is green; sha defaults to HEAD) writes {"sha", "utc"} to `<landing cache>/<repo>.lkg.json`
(the landing watchdog's state dir, PERUN_LANDING_DIR or $XDG_CACHE_HOME/perun/landing-watchdog), keyed on the git common dir so
worktrees share one pointer. Written atomically; it survives the watchdog's stamp pruning (ends in `.lkg.json`). `check <sha>` exits 0 only when <sha> IS the LKG, else 1 with the
untested gap (commits since the LKG; also 1 when none is recorded). `age` prints the LKG age in hours. `verdict <file>` exits 0 only for a green receipt of the current HEAD (`status` pass, `sha` HEAD, runner blob match; else 1, "rerun"). `path` prints the pointer file; run-ci-tests.sh reads its own fresh receipt back with `verdict`. Side effects: `record` overwrites the pointer.
Provenance: `record` stores `runner`, the blob of `scripts/run-ci-tests.sh` at the sha, and REFUSES (ValueError, exit 1) when the working-tree copy differs from it (a stale or edited runner
is not the gate that HEAD defines); `check` rejects a receipt whose `runner` is missing or not that sha's blob. Repos without the runner skip both.
Affected receipts (never the pointer; written only through `record_affected_cli`, the entry run-ci-tests.sh --affected uses, not a subcommand; BASE TREE SUITE=RC..., RC `-` = selected, not run) are
written as `<hash>.<tree12>.affected.json` {kind "affected", sha, tree, base, runner, suites, rc, utc} to the first writable of `<git common dir>/perun`, `$TMPDIR/perun`, the landing cache dir (the agent sandbox denies ~/.cache); reads take the newest across all three. run-ci-tests.sh --affected writes one per run,
pass or fail, only when the tree is unchanged after the suites; `tree` prints the working-tree tree hash it keys on (`git add -A` into a temp copy of the index: tracked, staged and untracked-unignored files, the real index and HEAD
untouched). `affected-check <tree> [BASE]` exits 0 only for an rc 0 receipt of that tree whose `runner` (blob of scripts/run-ci-tests.sh as run) is the tree's and that covers, at rc 0, every suite `run-ci-tests.sh --list-affected BASE`
re-derives for this tree (BASE default: the receipt's); 1 = refused; 3 = could not verify (no receipt and no writable receipt dir, a receipt file that cannot be read, or the re-derivation failed). handback.py --body-file uses it to refuse an unbacked test claim.
Files older than 7 days are pruned on write.
Policy: `lkg_gate` shadow|enforce|off (land-release.sh, default shadow), `lkg_stale_h` (hours >= 0, 0 = off) for the watchdog alarm.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import landing_watchdog as lw  # noqa: E402


def _common(cwd="."):
    return os.path.realpath(os.path.join(cwd, lw._run(["git", "rev-parse", "--git-common-dir"], cwd)))


def _key(cwd="."):
    return hashlib.sha1(_common(cwd).encode()).hexdigest()[:16]


def path(cwd="."):
    return os.path.join(os.path.dirname(lw.cache_file(cwd)), _key(cwd) + ".lkg.json")


def tilde(e):
    """str(e) with the home dir shown as ~: error text reaches hand-backs and logs, which must not carry absolute home paths."""
    home = os.path.expanduser("~")
    return str(e).replace(home, "~") if len(home) > 1 else str(e)


RUNNER = "scripts/run-ci-tests.sh"


def runner_blob(sha, cwd="."):
    """Blob id of the gate runner at `sha`, or '' when that commit has none; RuntimeError on any other git failure (fail closed)."""
    r = subprocess.run(["git", "ls-tree", sha, "--", RUNNER], cwd=cwd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"git ls-tree {sha[:12]} failed: {r.stderr.strip()[:200]}")
    return r.stdout.split()[2] if r.stdout.strip() else ""


def work_runner(cwd="."):
    """Blob id of the working-tree gate runner as it would run, or '' when it is missing."""
    return subprocess.run(["git", "hash-object", "--no-filters", RUNNER], cwd=cwd, capture_output=True, text=True).stdout.strip()


def record(cwd=".", sha=None, now=None):
    """Write the pointer for `sha` (default HEAD) and return it; ValueError when the working-tree runner is not the one at `sha`."""
    sha = lw._run(["git", "rev-parse", "--verify", (sha or "HEAD") + "^{commit}"], cwd).strip()
    rec = {"sha": sha, "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time())), "runner": runner_blob(sha, cwd), "status": "pass"}
    if rec["runner"]:
        have = work_runner(cwd)
        if have != rec["runner"]:
            raise ValueError(f"stale runner: working-tree {RUNNER} ({have[:12] or 'missing'}) is not {sha[:12]}'s ({rec['runner'][:12]}); rerun the gate from that commit's script")
    tmp = f"{path(cwd)}.{os.getpid()}.tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f)
    os.replace(tmp, path(cwd))
    return rec


def read(cwd="."):
    """The recorded pointer, or None when absent or unreadable."""
    try:
        with open(path(cwd)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def age_h(cwd=".", now=None):
    """Hours since the LKG was recorded, or None when there is none."""
    rec = read(cwd)
    return None if not rec else ((now or time.time()) - lw._ts(rec["utc"])) / 3600


def check(sha, cwd="."):
    """(ok, message): ok only when `sha` is the LKG; otherwise the message names the untested gap."""
    rec = read(cwd)
    if not rec:
        return False, "no last-known-good recorded"
    if rec["sha"] == sha:
        want = runner_blob(sha, cwd)
        if want and rec.get("runner") != want:
            return False, f"{sha[:12]} receipt rejected: runner provenance {(rec.get('runner') or 'missing')[:12]} is not {RUNNER} at that commit ({want[:12]}); rerun it"
        return True, f"{sha[:12]} is the last-known-good ({rec['utc']})"
    r = subprocess.run(["git", "rev-list", "--count", f"{rec['sha']}..{sha}"], cwd=cwd, capture_output=True, text=True)
    anc = subprocess.run(["git", "merge-base", "--is-ancestor", rec["sha"], sha], cwd=cwd, capture_output=True).returncode == 0
    gap = f"{r.stdout.strip()} untested commits since" if anc else "not a descendant of"
    return False, f"{sha[:12]} is not the last-known-good: {gap} {rec['sha'][:12]} ({rec['utc']})"


def verdict(path, cwd="."):
    """(ok, message): ok only for a green receipt of HEAD: `status` == "pass", `sha` == HEAD, and (when the repo has the runner) `runner` == its blob at HEAD. Unreadable, red, shaless, stale or unprovenanced fails closed with "rerun"."""
    try:
        with open(path) as f:
            rec = json.load(f)
        sha = rec["sha"]
    except (OSError, ValueError, KeyError, TypeError):
        return False, f"{path}: unreadable or no recorded sha; rerun"
    head = lw._run(["git", "rev-parse", "HEAD"], cwd).strip()
    if sha != head:
        return False, f"{path}: verdict is for {str(sha)[:12]}, HEAD is {head[:12]}; rerun"
    if rec.get("status") != "pass":
        return False, f"{path}: verdict at HEAD {head[:12]} is not a pass (status {rec.get('status')!r}); rerun"
    want = runner_blob(head, cwd)
    if want and rec.get("runner") != want:
        return False, f"{path}: runner provenance {(rec.get('runner') or 'missing')[:12]} is not {RUNNER} at HEAD ({want[:12]}); rerun"
    return True, f"{path}: pass verdict matches HEAD {head[:12]}"


def work_tree(cwd="."):
    """Tree hash of the working tree as `git add -A && git commit` would record it (tracked, staged and untracked-unignored files); the real index is untouched."""
    idx = os.path.join(cwd, lw._run(["git", "rev-parse", "--git-path", "index"], cwd))
    with tempfile.TemporaryDirectory() as d:
        tmp = os.path.join(d, "index")
        if os.path.exists(idx):
            shutil.copy2(idx, tmp)  # keeps the index mtime: git's racy-stat check compares it to file mtimes, and a fresh mtime would let a same-size same-second edit pass as unchanged
        env = {**os.environ, "GIT_INDEX_FILE": tmp}
        for c in (["add", "-A"], ["write-tree"]):
            r = subprocess.run(["git", *c], cwd=cwd, env=env, capture_output=True, text=True, timeout=300)
            if r.returncode:
                raise RuntimeError(f"git {c[0]} failed: {r.stderr.strip()[:200]}")
        return r.stdout.strip()


def receipt_dirs(cwd="."):
    """Affected-receipt dirs, most preferred first: <git common dir>/perun, $TMPDIR/perun, the landing cache dir. The agent sandbox denies ~/.cache, so it is last."""
    ds = [os.path.join(_common(cwd), "perun"), os.path.join(os.environ.get("TMPDIR") or "/tmp", "perun")]
    try:
        ds.append(os.path.dirname(lw.cache_file(cwd)))
    except OSError:
        pass
    return ds


def _writable(d):
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        with tempfile.TemporaryFile(dir=d):
            return True
    except OSError:
        return False


def affected_name(tree, cwd="."):
    return f"{_key(cwd)}.{tree[:12]}.affected.json"


def record_affected(base, tree, suites, cwd=".", now=None):
    """Write the kind=affected receipt for working-tree `tree` to the first writable receipt dir; suites maps suite -> rc (None = selected, not run). Never touches the LKG pointer.
    Returns it; OSError (no path in the text) when no dir is writable."""
    rec = {"kind": "affected", "sha": lw._run(["git", "rev-parse", "--verify", "HEAD^{commit}"], cwd), "tree": tree, "base": base, "runner": work_runner(cwd), "suites": suites,
           "rc": int(any(v != 0 for v in suites.values())), "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now or time.time()))}
    for d in receipt_dirs(cwd):
        p = os.path.join(d, affected_name(tree, cwd))
        tmp = f"{p}.{os.getpid()}.tmp"
        try:
            os.makedirs(d, mode=0o700, exist_ok=True)
            with open(tmp, "w") as f:
                json.dump(rec, f)
            os.replace(tmp, p)
        except OSError:
            continue
        try:
            for n in os.listdir(d):  # prune receipts of long-gone trees
                if n.endswith(".affected.json") and time.time() - os.path.getmtime(os.path.join(d, n)) > 7 * 86400:
                    os.remove(os.path.join(d, n))
        except OSError:
            pass
        return rec
    raise OSError("no writable receipt dir (git common dir, TMPDIR, cache dir)")


def record_affected_cli(args, cwd="."):
    """Internal entry of run-ci-tests.sh --affected, deliberately not a lkg.py subcommand: args = BASE TREE SUITE=RC... (RC `-` = selected, not run). Exit code; prints the error, never a traceback."""
    try:
        record_affected(args[0], args[1], {k: None if v == "-" else int(v) for k, _, v in (a.rpartition("=") for a in args[2:])}, cwd)
    except (IndexError, ValueError, RuntimeError, OSError) as e:
        print(f"lkg: {tilde(e)}", file=sys.stderr)
        return 1
    return 0


def _receipt(tree, cwd="."):
    """(the newest well-formed kind=affected receipt for `tree` across every receipt dir, or None; whether a receipt file for it exists but cannot be read).
    A receipt missing kind, tree, base, suites or utc, or with the wrong types, is skipped, so callers never meet a KeyError."""
    recs, unreadable = [], False
    for d in receipt_dirs(cwd):
        p = os.path.join(d, affected_name(tree, cwd))
        try:
            with open(p) as f:
                r = json.load(f)
        except OSError:
            unreadable = unreadable or os.path.lexists(p)  # a missing or blocked dir is no receipt; a file that is there but cannot be opened is unreadable
            continue
        except ValueError:
            continue
        if isinstance(r, dict) and r.get("kind") == "affected" and r.get("tree") == tree and isinstance(r.get("suites"), dict) and isinstance(r.get("base"), str) and isinstance(r.get("utc"), str):
            recs.append(r)
    return max(recs, key=lambda r: r["utc"], default=None), unreadable


def selected(base, cwd="."):
    """Suites the runner's dry mode (`--list-affected BASE`: no gates, no suites run) selects for the working tree; RuntimeError when it cannot say."""
    r = subprocess.run(["bash", RUNNER, "--list-affected", base], cwd=cwd, capture_output=True, text=True, timeout=300)
    if r.returncode or not re.search(r"^affected: \d+ of \d+ tests", r.stdout, re.M):
        raise RuntimeError(f"cannot re-derive the affected selection against {base[:12]}: {r.stdout.strip()[-120:] or r.stderr.strip()[-120:]}")
    return [n[len("selected: "):] for n in r.stdout.splitlines() if n.startswith("selected: ")]


def affected_check(tree, cwd=".", base=None):
    """(ok, message). ok True only for a kind=affected receipt of `tree` with rc 0 that names the runner blob this tree has and covers, at rc 0, every suite the runner re-derives for this
    tree against `base` (default: the receipt's own); repos without the runner skip those two. False + why when refused. None = could not verify: no receipt and no writable receipt dir
    (nothing could have been recorded, so an honest claim must not read as a false one), or the re-derivation failed.
    ponytail: the local receipt stops honest, stale and partial over-claims; a deliberate forgery (a hand-written record call) needs CI proof, and CI is the authority, so no signing key."""
    rec, unreadable = _receipt(tree, cwd)
    if rec is None:
        if unreadable:
            return None, "could not verify: a receipt for this tree exists but cannot be read"
        if any(_writable(d) for d in receipt_dirs(cwd)):
            return False, "no receipt for this tree"
        return None, "could not verify: no writable receipt location, so none could have been recorded"
    bad = [k for k, v in rec["suites"].items() if v != 0]
    if rec.get("rc") != 0 or bad:
        return False, "receipt for this tree failed: " + (", ".join(f"{k} rc={'not run' if rec['suites'][k] is None else rec['suites'][k]}" for k in bad) or f"rc {rec.get('rc')}")
    try:
        want = runner_blob(tree, cwd)
        if want and rec.get("runner") != want:
            return False, f"receipt runner {(rec.get('runner') or 'missing')[:12]} is not {RUNNER} in this tree ({want[:12]}); rerun it"
        if want:
            if work_tree(cwd) != tree:
                return False, "worktree is not the receipt's tree, so the selection cannot be re-derived; hand back from a clean checkout of that commit"
            miss = [s for s in selected(base or rec["base"], cwd) if rec["suites"].get(s) != 0]
            if miss:
                return False, "receipt lacks selected suite(s) at rc 0: " + ", ".join(miss)
    except (OSError, RuntimeError, subprocess.SubprocessError) as e:
        return None, f"could not verify: {tilde(e)}"
    return True, f"tree {tree[:12]}: affected pass, {len(rec['suites'])} suites vs {str(rec['base'])[:12]} ({rec['utc']})"


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    if cmd == "record":
        try:
            print(json.dumps(record(sha=argv[2] if len(argv) > 2 else None)))
        except (ValueError, RuntimeError) as e:
            print(f"lkg: {tilde(e)}", file=sys.stderr)
            return 1
    elif cmd == "check" and len(argv) > 2:
        ok, msg = check(argv[2])
        print(msg)
        return 0 if ok else 1
    elif cmd == "verdict" and len(argv) > 2:
        ok, msg = verdict(argv[2])
        print(msg)
        return 0 if ok else 1
    elif cmd == "tree":
        print(work_tree())
    elif cmd == "affected-check" and len(argv) > 2:
        ok, msg = affected_check(argv[2], base=argv[3] if len(argv) > 3 else None)
        print(msg)
        return 3 if ok is None else 0 if ok else 1
    elif cmd == "path":
        print(path())
    elif cmd == "age":
        a = age_h()
        print("none" if a is None else f"{a:.1f}")
    else:
        print("usage: lkg.py record [sha] | check <sha> | verdict <file> | tree | affected-check <tree> [BASE] | path | age", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
