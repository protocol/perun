#!/usr/bin/env python3
"""review_gate.py — pre-merge gate: every PR needs an independent deep-code-review DIFF pass plus an evil-twin check.

  review_gate.py check <pr> --head SHA [--repo R]   exit 0 ok / off / warn-only; exit 1 only in enforce mode
  review_gate.py receipt <pr> --reviewer R --author A --head SHA   write the receipt file

Evidence, either of:
  1. receipt file `$REVIEW_DIR/<pr>.json` (default `.perun/reviews/`) with reviewer, author, head, diff_pass and
     evil_twin all set; written by `receipt` after the reviewer agent finishes both passes.
  2. a PR comment holding `<!-- perun-review reviewer=R author=A head=SHA diff=pass evil-twin=pass -->`.
`reviewer`/`author` are run ids; a marker from a different GitHub login than the PR author is noted as stronger
evidence, a same-account one logs "same-account review: run-id separation only". The gate proves an independent
review RUN on the current head, not a different human. The reviewer must be non-empty and differ (case-insensitive) from the author (and from the GitHub PR author when
the comment path is used), and `head` must match the PR head being merged (prefix match, 7+ chars), so a review
of an older push covers a newer one only when the diff since the reviewed head touches no tier-1 path (tier_gate.py,
templates/review-tiers.tsv; commit missing locally or any error = stale, re-review). This is an honest-process receipt, not a forgery-proof signature.

Policy `review_gate` (`.perun/policy.json`): `warn` (default, this release: prints WARN, never blocks),
`enforce` (a PR with no evidence exits 1), `off` (opt out; silent). A malformed policy or a failing `gh` is
treated as no evidence, never a crash. Side effects: `receipt` writes one file; `check` runs `gh pr view` only
when no valid receipt exists. Env: GH (default gh), REVIEW_DIR.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402
import perun_policy  # noqa: E402
import tier_gate  # noqa: E402

MARKER = re.compile(r"<!--\s*perun-review\s+reviewer=(\S+)\s+author=(\S+)\s+head=([0-9a-f]{7,40})\s+diff=pass\s+evil-twin=pass\s*-->")


def _same_head(a: str, b: str) -> bool:
    return bool(a) and bool(b) and len(a) >= 7 and len(b) >= 7 and (a.startswith(b) or b.startswith(a))


def _frontmatter(ref: str, path: str) -> str:
    """The `---` block at the top of `path` at `ref` ("" when the file or block is absent)."""
    out = subprocess.run(["git", "show", f"{ref}:{path}"], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL).stdout
    m = re.match(r"---\r?\n(.*?)\r?\n---", out, re.S)
    return m.group(1) if m else ""


def _tier1_free(old: str, new: str) -> bool:
    """True when `git diff old new` touches no tier-1 path (templates/review-tiers.tsv) and leaves every changed SKILL.md's
    frontmatter block identical (tool grants live there, as a `tools:` line or a list under `allowed-tools:`). --no-renames lists
    a rename's old path too, so moving a tier-1 file into references/ stays tier 1. Any failure (non-hex ref, commit not local,
    git or tiers file unreadable) is False: an unprovable delta needs a fresh review."""
    if not (re.fullmatch(r"[0-9a-f]{7,40}", old or "") and re.fullmatch(r"[0-9a-f]{7,40}", new or "")):
        return False
    try:
        rows = tier_gate.load_tiers(tier_gate.DEFAULT_TIERS)
        out = subprocess.run(["git", "diff", "--no-renames", "--name-only", old, new], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        paths = [p for p in out.stdout.splitlines() if p]
        return out.returncode == 0 and all(tier_gate.tier_of(p, rows) != 1 for p in paths) \
            and all(_frontmatter(old, p) == _frontmatter(new, p) for p in paths if p.rsplit("/", 1)[-1] == "SKILL.md")
    except (OSError, subprocess.SubprocessError, tier_gate.TierError):
        return False


def valid(reviewer: str, author: str, head: str, want_head: str, gh_author: str = "") -> bool:
    """Independent (reviewer != author, != GitHub PR author) and covering the head being merged: the reviewed head itself, or
    one pushed after it whose diff since the reviewed head touches no tier-1 path (a fix push needs no second review)."""
    r = (reviewer or "").strip().lower()
    return bool(r) and r != (author or "").strip().lower() and r != gh_author.lower() \
        and (_same_head(head, want_head) or _tier1_free(head, want_head))


def has_evidence(pr: str, head: str = "", repo: str = "", review_dir: Path | None = None) -> bool:
    d = review_dir or Path(os.environ.get("REVIEW_DIR", ".perun/reviews"))
    try:
        r = json.loads((d / f"{pr}.json").read_text())
        if r.get("diff_pass") is True and r.get("evil_twin") is True and valid(
                str(r.get("reviewer", "")), str(r.get("author", "")), str(r.get("head", "")), head):
            return True
    except (OSError, ValueError, AttributeError):
        pass
    cmd = [os.environ.get("GH", "gh"), "pr", "view", pr, "--json", "author,comments"] + (["--repo", repo] if repo else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        data = json.loads(out.stdout) if out.returncode == 0 else {}
        if out.returncode and gh_rest.TLS.search(out.stderr or ""):
            print("review_gate: gh TLS failure (OSStatus -26276), no REST fallback for `gh pr view`; treated as no evidence", file=sys.stderr)
        gh_author = ((data.get("author") or {}).get("login")) or ""
        for c in data.get("comments") or []:
            for m in MARKER.findall(c.get("body") or ""):
                if valid(m[0], m[1], m[2], head, gh_author):
                    login = (c.get("author") or {}).get("login") or gh_author
                    print("review_gate: marker from a different GitHub login than the PR author (stronger evidence)" if login != gh_author
                          else "review_gate: same-account review: run-id separation only", file=sys.stderr)
                    return True
        return False
    except (OSError, ValueError, subprocess.SubprocessError, AttributeError):
        return False


LOCKFILES = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "Cargo.lock", "Gemfile.lock", "go.sum", "uv.lock", "composer.lock"}


def lockfile_only(pr: str, head: str, repo: str = "") -> bool:
    """True only when the PR's current head matches `head` and every file (and rename source) is a LOCKFILES name.
    Fails closed: gh error, empty list, >=100 files (the gh list may be truncated) or a head mismatch is False."""
    cmd = [os.environ.get("GH", "gh"), "pr", "view", pr, "--json", "files,headRefOid"] + (["--repo", repo] if repo else [])
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
        data = json.loads(out.stdout) if out.returncode == 0 else {}
        files = data["files"]
        if not _same_head(str(data["headRefOid"]), head) or not files or len(files) >= 100:
            return False
        paths = [p for f in files for p in (f["path"], f.get("previousFilename") or f["path"])]
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError):
        return False
    return all(os.path.basename(p) in LOCKFILES for p in paths)


def _main(argv: list) -> int:
    ap = argparse.ArgumentParser(prog="review_gate.py")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("pr")
    c.add_argument("--head", required=True)
    c.add_argument("--repo", default="")
    c.add_argument("--audit-clean", action="store_true")  # caller asserts the dependency audit diff is clean
    r = sub.add_parser("receipt")
    r.add_argument("pr")
    r.add_argument("--reviewer", required=True)
    r.add_argument("--author", required=True)
    r.add_argument("--head", required=True)
    a = ap.parse_args(argv)
    if a.cmd == "receipt":
        if not valid(a.reviewer, a.author, a.head, a.head):
            print("review_gate: reviewer must be non-empty and differ from the author", file=sys.stderr)
            return 2
        d = Path(os.environ.get("REVIEW_DIR", ".perun/reviews"))
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{a.pr}.json").write_text(json.dumps(
            {"pr": a.pr, "reviewer": a.reviewer, "author": a.author, "head": a.head, "diff_pass": True, "evil_twin": True}) + "\n")
        return 0
    try:
        mode = perun_policy.load()["review_gate"]
    except ValueError:
        mode = "warn"
    if mode == "off" or has_evidence(a.pr, a.head, a.repo):
        return 0
    try:
        skip = perun_policy.load()["lockfile_skip_review"] == "on"
    except ValueError:
        skip = False
    if skip and a.audit_clean and lockfile_only(a.pr, a.head, a.repo):
        print(f"review_gate: #{a.pr} is lockfile-only with a clean audit diff; separate review lane skipped (lockfile_skip_review=on)", file=sys.stderr)
        return 0
    msg = (f"#{a.pr} has no independent deep-code-review DIFF pass + evil-twin receipt "
           f"(.perun/reviews/{a.pr}.json or a perun-review PR comment from a non-author reviewer)")
    if mode == "enforce":
        print(f"REVIEW GATE: {msg}; not merged", file=sys.stderr)
        return 1
    print(f"WARN review_gate: {msg}; warn-only this release, review_gate=enforce blocks, review_gate=off opts out", file=sys.stderr)
    return 0


def main(argv: list) -> int:
    """_main; an unexpected exception in warn mode prints a WARN and exits 0 (never blocks); in enforce it exits 1."""
    try:
        return _main(argv)
    except Exception as e:  # noqa: BLE001 - fail soft by design
        try:
            enforce = perun_policy.load()["review_gate"] == "enforce"
        except Exception:  # noqa: BLE001
            enforce = False
        print(f"{'REVIEW GATE' if enforce else 'WARN review_gate'}: internal error ({type(e).__name__}); review not verified", file=sys.stderr)
        return 1 if enforce else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
