#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=tier-1 changes need the strongest model and an independent receipted review, review=2027-01-30
"""Review-tier gate: tier-1 changes need the strongest model and an independent, receipted review.

Reads the ONE path-glob -> tier file (templates/review-tiers.tsv; format
`<glob>\\t<tier>\\t<why>`, fnmatch where `*` crosses `/`, tried against both
the repo-relative path and the path with a leading `/` so `*/auth/*` also
matches a root-level `auth/`; strictest matching tier wins; unmatched paths
are tier 2). Modes:

  tier_gate.py --classify PATH...   print each path's tier and the strictest
                                    tier overall (the dispatch step's input).
  tier_gate.py BASE..HEAD           judge every first-parent commit in the
                                    range, merge commits included (a merge is
                                    judged by its diff against its first
                                    parent, so a release squash or merge on
                                    the protected branch is judged too).
  tier_gate.py --github PR          judge a GitHub pull request: tier from its
                                    files; tier 1-2 need an APPROVED review
                                    from a login other than the PR author.
  --advisory                        print every finding, always exit 0.

Per commit, the strictest tier among its changed paths decides:
  tier 1 -> a `Model:` trailer naming a model in TIER_STRONG_MODELS
            (comma-separated, default `opus`; first word, case-insensitive)
            AND an independent, receipted `Reviewed-By:` trailer.
  tier 2 -> an independent, receipted `Reviewed-By:` trailer.
  tier 3 -> self-review allowed; no trailer required.

`Reviewed-By: <id> receipt:<ref>` — the id part (with any `<email>` removed)
must differ from BOTH the author and the committer name, and any email in the
value must differ from both of their emails. The receipt must exist: a path
committed in the judged commit or at HEAD, a commit sha reachable in this
repo, or a GitHub pull-request review/comment URL (`#pullrequestreview-N`,
`#issuecomment-N`, `#discussion_rN`) that `gh api` can fetch — when gh is not
installed a URL receipt fails closed. LIMITS: this proves a named, different
identity left a checkable artifact; it cannot prove the reviewer read the
diff, and one shared account (or one person holding two identities) cannot
prove independence at all — give the reviewer a separate account, e.g. a
reviewer bot, and prefer `--github` against its APPROVED review.

Exit codes: 0 pass, 1 at least one failure, 2 usage error, unreadable or
malformed tiers file, unresolvable range, or gh failure (fail closed);
`--advisory` turns 1 and 2 into printed findings with exit 0. Side effects:
none (reads git; `--github` and URL receipts run read-only gh calls).
`--selftest` builds throwaway git repos under a temp dir and stubs gh.
"""
import fnmatch
import json
import os
import re
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_TIERS = os.path.join(HERE, "..", "templates", "review-tiers.tsv")
DEFAULT_TIER = 2
URL_RE = re.compile(r"^https://github\.com/([^/]+)/([^/]+)/pull/(\d+)#(pullrequestreview-|issuecomment-|discussion_r)(\d+)$")
USAGE = "usage: tier_gate.py [--tiers FILE] [--advisory] (--classify PATH... | --github PR | BASE..HEAD)"


class TierError(Exception):
    """Unreadable or malformed tiers file, a git failure, or a gh failure (exit 2)."""


def load_tiers(path):
    """Parse the tiers file into [(glob, tier)]; raise TierError on any bad row."""
    try:
        with open(path, encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except OSError as exc:
        raise TierError(f"cannot read tiers file {path}: {exc}")
    rows = []
    for n, line in enumerate(lines, 1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2 or parts[1].strip().rstrip("!") not in ("1", "2", "3"):
            raise TierError(f"{path}:{n}: expected <glob>\\t<1|2|3>[!]\\t<why>, got {line!r}")
        t = int(parts[1].strip().rstrip("!"))
        rows.append((parts[0].strip(), -t if parts[1].strip().endswith("!") else t))  # negative = pinned
    if not rows:
        raise TierError(f"{path}: no tier rows (fail closed)")
    return rows


def tier_of(path, rows):
    """Strictest (lowest) tier among matching globs, a pinned row (`2!`/`1!`) winning outright, the strictest among pins; DEFAULT_TIER when none match."""
    hits = [t for g, t in rows if fnmatch.fnmatchcase(path, g) or fnmatch.fnmatchcase("/" + path, g)]
    pins = [-t for t in hits if t < 0]
    return min(pins) if pins else min(hits) if hits else DEFAULT_TIER


def _gh(args):
    """Run gh read-only; (returncode, stdout). 127 when gh is not installed."""
    if not shutil.which("gh"):
        return 127, ""
    proc = subprocess.run(["gh", *args], capture_output=True, text=True)
    return proc.returncode, proc.stdout


def _git(repo, *args, check=True):
    proc = subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise TierError(f"git {' '.join(args)}: {proc.stderr.strip()}")
    return proc.stdout if check else proc.returncode == 0


def _trailer(repo, sha, key):
    out = _git(repo, "log", "-1", f"--format=%(trailers:key={key},valueonly,unfold)", sha)
    return [v.strip() for v in out.splitlines() if v.strip()]


def receipt_ok(repo, sha, ref):
    """(ok, why) — does the review receipt exist?"""
    m = URL_RE.match(ref)
    if m:
        owner, name, pr, kind, rid = m.groups()
        endpoint = {
            "pullrequestreview-": f"repos/{owner}/{name}/pulls/{pr}/reviews/{rid}",
            "issuecomment-": f"repos/{owner}/{name}/issues/comments/{rid}",
            "discussion_r": f"repos/{owner}/{name}/pulls/comments/{rid}",
        }[kind]
        rc, _ = _gh(["api", endpoint])
        if rc == 127:
            return False, f"receipt {ref} is a URL but gh is not installed (cannot verify; fail closed)"
        return (rc == 0), f"receipt {ref} not found via gh api"
    if ref.startswith(("http://", "https://")):
        return False, f"receipt {ref} is not a GitHub PR review/comment URL"
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref) and _git(repo, "cat-file", "-e", f"{ref}^{{commit}}", check=False):
        return True, ""
    for rev in (sha, "HEAD"):
        if _git(repo, "cat-file", "-e", f"{rev}:{ref}", check=False):
            return True, ""
    return False, f"receipt {ref} is not a reachable commit or a committed path"


def reviewer_problem(repo, sha, values, people):
    """None when some Reviewed-By value is independent and receipted, else why not."""
    if not values:
        return "needs a Reviewed-By: <id> receipt:<sha|path|url> trailer"
    names = {n.lower() for n, _ in people if n}
    emails = {e.lower() for _, e in people if e}
    why = ""
    for value in values:
        m = re.search(r"\breceipt:(\S+)", value)
        ident = re.sub(r"\breceipt:\S+", "", value)
        found = {e.lower() for e in re.findall(r"<([^>]*)>", ident)}
        name = re.sub(r"<[^>]*>", "", ident).strip().lower()
        if name in names or found & emails or any(e in value.lower() for e in emails):
            why = f"Reviewed-By {value!r} names the author or committer (not independent)"
            continue
        if not m:
            why = f"Reviewed-By {value!r} has no receipt:<sha|path|url>"
            continue
        ok, rwhy = receipt_ok(repo, sha, m.group(1))
        if ok:
            return None
        why = rwhy
    return why


def judge_commit(repo, sha, rows, strong):
    """Return a list of failure strings for one commit (empty = pass)."""
    parents = _git(repo, "rev-list", "--parents", "-n1", sha).split()[1:]
    if len(parents) > 1:
        paths = _git(repo, "diff", "--name-only", parents[0], sha).splitlines()
    else:
        paths = _git(repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "--root", sha).splitlines()
    paths = [p for p in paths if p]
    if not paths:
        return []
    tier, path = min((tier_of(p, rows), p) for p in paths)
    if tier == 3:
        return []
    an, ae, cn, ce = _git(repo, "log", "-1", "--format=%an%x00%ae%x00%cn%x00%ce", sha).strip().split("\x00")
    fails = []
    problem = reviewer_problem(repo, sha, _trailer(repo, sha, "Reviewed-By"), [(an, ae), (cn, ce)])
    if problem:
        fails.append(f"tier {tier} ({path}): {problem}")
    if tier == 1:
        models = [m.split()[0].lower() for m in _trailer(repo, sha, "Model") if m.split()]
        if not any(m in strong for m in models):
            fails.append(f"tier 1 ({path}): needs a Model: trailer naming one of {sorted(strong)}")
    return fails


def gate(repo, rng, rows, strong):
    """Judge every first-parent commit (merges included) in rng; return (failure lines, count)."""
    shas = _git(repo, "rev-list", "--first-parent", "--reverse", rng).split()
    lines = []
    for sha in shas:
        for f in judge_commit(repo, sha, rows, strong):
            lines.append(f"FAIL {sha[:12]} {f}")
    return lines, len(shas)


def github_gate(pr, rows):
    """Judge a pull request by its files and reviews; return failure lines."""
    rc, out = _gh(["pr", "view", pr, "--json", "author,reviews,files"])
    if rc != 0:
        raise TierError(f"gh pr view {pr} failed (rc={rc}; gh missing or no access)")
    data = json.loads(out)
    paths = [f.get("path", "") for f in data.get("files") or [] if f.get("path")]
    if not paths:
        return []
    tier, path = min((tier_of(p, rows), p) for p in paths)
    if tier == 3:
        return []
    author = ((data.get("author") or {}).get("login") or "").lower()
    approvers = {((r.get("author") or {}).get("login") or "").lower()
                 for r in data.get("reviews") or [] if r.get("state") == "APPROVED"}
    approvers.discard("")
    approvers.discard(author)
    if approvers:
        return []
    return [f"FAIL PR {pr} tier {tier} ({path}): needs an APPROVED review from a login other than the PR author"]


def _strong():
    return {m.strip().lower() for m in os.environ.get("TIER_STRONG_MODELS", "opus").split(",") if m.strip()}


def main(argv):
    args = list(argv)
    advisory = "--advisory" in args
    args = [a for a in args if a != "--advisory"]
    tiers = DEFAULT_TIERS
    if "--tiers" in args:
        i = args.index("--tiers")
        if i + 1 >= len(args):
            print(USAGE, file=sys.stderr)
            return 2
        tiers = args[i + 1]
        del args[i:i + 2]
    try:
        rows = load_tiers(tiers)
        if args and args[0] == "--classify":
            if len(args) < 2:
                print("tier_gate: --classify needs at least one path", file=sys.stderr)
                return 2
            for p in args[1:]:
                print(f"{tier_of(p, rows)}\t{p}")
            print(f"strictest\t{min(tier_of(p, rows) for p in args[1:])}")
            return 0
        if len(args) == 2 and args[0] == "--github":
            lines, n = github_gate(args[1], rows), 1
        elif len(args) == 1 and ".." in args[0]:
            lines, n = gate(os.getcwd(), args[0], rows, _strong())
        else:
            print(USAGE, file=sys.stderr)
            return 2
    except TierError as exc:
        print(f"tier_gate: {exc} (fail closed{'; advisory, exit 0' if advisory else ''})", file=sys.stderr)
        return 0 if advisory else 2
    for line in lines:
        print(line)
    print(f"tier_gate: {n} judged, {len(lines)} failure(s){' (advisory: not failing)' if advisory else ''}")
    return 1 if lines and not advisory else 0


# ---------------------------------------------------------------------------
# --selftest — pins the shipped tiers file's classification and proves the
# gate fires on each planted violation in a throwaway git repo (gh stubbed).
# ---------------------------------------------------------------------------
def _selftest():
    import tempfile

    global _gh
    passed = failed = 0

    def case(name, ok):
        nonlocal passed, failed
        passed += bool(ok)
        failed += not ok
        print(f"{'PASS' if ok else 'FAIL'}  {name}")

    rows = load_tiers(DEFAULT_TIERS)
    for path, want in [
        (".claude/skills/agentic-delivery/SKILL.md", 2),
        (".claude/skills/agentic-delivery/INDEX.md", 2),
        (".claude/skills/deep-code-review/references/method.md", 2),
        (".claude/skills/deep-code-review/references/merge-operations.md", 2),
        (".claude/skills/deep-code-review/evals/evals.json", 2),
        (".claude/agents/reviewer.md", 1),
        (".claude/commands/ship.md", 1),
        # nested: a pinned 2! row beats an unpinned name glob, a 1! row beats a pinned 2!
        (".claude/skills/x/references/merge-ops.md", 2),
        (".claude/skills/x/references/gate-notes.md", 2),
        (".claude/skills/x/evals/scripts/gate.py", 1),
        (".claude/skills/x/references/templates/lane.md", 1),
        (".claude/skills/x/references/AGENTS.md", 1),
        (".claude/skills/x/references/install.sh", 1),
        (".claude/skills/x/references/probe.py", 2),
        (".claude/skills/x/evals/runner.sh", 2),
        (".claude/skills/x/references/sub/CLAUDE.md", 1),
        ("CODEOWNERS", 1),
        (".claude/skills/agentic-delivery/scripts/review_gate.py", 1),
        (".github/workflows/ci.yml", 1),
        (".claude/hooks/caveman.js", 1),
        ("db/migrations/0001_init.py", 1),
        ("src/auth/session.py", 1),
        ("auth/session.py", 1),
        ("src/merge_queue.py", 1),
        ("scripts/dcr-gates.sh", 1),
        ("CLAUDE.md", 1),
        ("src/app/cart.py", 2),
        ("src/delegate.py", 2),
        ("src/author.py", 2),
        ("src/emergency.py", 2),
        ("README.md", 3),
        ("docs/guide.md", 3),
        ("docs/author-guide.md", 3),
    ]:
        case(f"shipped-tiers: {path} -> {want}", tier_of(path, rows) == want)

    real_gh = _gh
    tmp = tempfile.mkdtemp(prefix="tier-gate-selftest-")
    try:
        bad = os.path.join(tmp, "bad.tsv")
        with open(bad, "w") as fh:
            fh.write("*.md\tthree\tdocs\n")
        try:
            load_tiers(bad)
            case("malformed-tiers-fails-closed", False)
        except TierError:
            case("malformed-tiers-fails-closed", True)
        case("missing-tiers-exit-2", main(["--tiers", os.path.join(tmp, "nope.tsv"), "a..b"]) == 2)

        repo = os.path.join(tmp, "repo")
        os.makedirs(repo)

        def git(*a, env=None):
            subprocess.run(["git", "-C", repo, *a], check=True, capture_output=True, env=env)

        git("init", "-q")
        git("config", "user.name", "Jane Smith")
        git("config", "user.email", "jane@example.com")
        os.makedirs(os.path.join(repo, "reviews"))
        with open(os.path.join(repo, "reviews", "r1.md"), "w") as fh:
            fh.write("approved\n")
        git("add", "-A")
        git("commit", "-q", "-m", "base")
        base = _git(repo, "rev-parse", "HEAD").strip()

        def commit(path, msg, env=None):
            full = os.path.join(repo, path)
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "a") as fh:
                fh.write("x\n")
            git("add", "-A")
            git("commit", "-q", "-m", msg, env=env)
            return _git(repo, "rev-parse", "HEAD").strip()

        strong = {"opus"}
        t1 = ".claude/hooks/demo.sh"
        ok_rev = "Reviewed-By: reviewer-bot receipt:reviews/r1.md"
        cases = [
            ("tier1-no-trailers-fails", t1, "edit", 2),
            ("tier1-self-review-fails", t1, "edit\n\nModel: opus\nReviewed-By: Jane Smith <jane@example.com> receipt:reviews/r1.md", 1),
            ("tier1-self-email-only-fails", t1, "edit\n\nModel: opus\nReviewed-By: J <jane@example.com> receipt:reviews/r1.md", 1),
            ("tier1-no-receipt-fails", t1, "edit\n\nModel: opus\nReviewed-By: reviewer-bot", 1),
            ("tier1-missing-receipt-path-fails", t1, "edit\n\nModel: opus\nReviewed-By: reviewer-bot receipt:reviews/none.md", 1),
            ("tier1-weak-model-fails", t1, f"edit\n\nModel: sonnet\n{ok_rev}", 1),
            ("tier1-strong-independent-path-receipt-passes", t1, f"edit\n\nModel: opus\n{ok_rev}", 0),
            ("tier1-sha-receipt-passes", t1, f"edit\n\nModel: opus\nReviewed-By: John Doe <john@example.com> receipt:{base[:10]}", 0),
            ("tier2-no-reviewer-fails", "src/app/cart.py", "feat", 1),
            ("tier3-docs-self-review-passes", "docs/guide.md", "docs", 0),
        ]
        for name, path, msg, want in cases:
            case(f"{name} ({want} failure(s))", len(judge_commit(repo, commit(path, msg), rows, strong)) == want)

        env = dict(os.environ, GIT_COMMITTER_NAME="reviewer-bot", GIT_COMMITTER_EMAIL="bot@example.com")
        sha = commit(t1, f"edit\n\nModel: opus\n{ok_rev}", env=env)
        case("tier1-reviewer-is-committer-fails", len(judge_commit(repo, sha, rows, strong)) == 1)

        url = "https://github.com/acme/widgets/pull/7#pullrequestreview-42"
        url_msg = f"edit\n\nModel: opus\nReviewed-By: reviewer-bot receipt:{url}"
        _gh = lambda args: (127, "")  # noqa: E731
        case("url-receipt-without-gh-fails-closed", len(judge_commit(repo, commit(t1, url_msg), rows, strong)) == 1)
        _gh = lambda args: (0, "{}") if args[:2] == ["api", "repos/acme/widgets/pulls/7/reviews/42"] else (1, "")  # noqa: E731
        case("url-receipt-fetched-via-gh-passes", judge_commit(repo, commit(t1, url_msg), rows, strong) == [])

        # A merge commit on the first-parent line is judged by its first-parent diff.
        git("checkout", "-q", "-b", "side")
        commit(t1, f"side edit\n\nModel: opus\n{ok_rev}")
        git("checkout", "-q", "-")
        git("merge", "-q", "--no-ff", "-m", "Merge side", "side")
        merge = _git(repo, "rev-parse", "HEAD").strip()
        case("merge-commit-without-trailers-is-judged", len(judge_commit(repo, merge, rows, strong)) == 2)

        cwd = os.getcwd()
        os.chdir(repo)
        try:
            case("range-with-failures-exit-1", main([f"{base}..HEAD"]) == 1)
            case("advisory-range-with-failures-exit-0", main(["--advisory", f"{base}..HEAD"]) == 0)
            case("unresolvable-range-exit-2", main(["nope..HEAD"]) == 2)
            case("advisory-unresolvable-range-exit-0", main(["--advisory", "nope..HEAD"]) == 0)
        finally:
            os.chdir(cwd)
        case("classify-exit-0", main(["--classify", "README.md", t1]) == 0)

        def pr(reviews, files=(t1,)):
            payload = {"author": {"login": "jane"}, "files": [{"path": f} for f in files], "reviews": reviews}
            return lambda args: (0, json.dumps(payload))

        _gh = pr([{"author": {"login": "reviewer-bot"}, "state": "APPROVED"}])
        case("github-approved-by-other-login-passes", github_gate("7", rows) == [])
        _gh = pr([{"author": {"login": "jane"}, "state": "APPROVED"},
                  {"author": {"login": "reviewer-bot"}, "state": "COMMENTED"}])
        case("github-approved-only-by-author-fails", len(github_gate("7", rows)) == 1)
        _gh = pr([], files=("docs/guide.md",))
        case("github-tier3-only-needs-no-review", github_gate("7", rows) == [])
        _gh = lambda args: (127, "")  # noqa: E731
        case("github-without-gh-exit-2", main(["--github", "7"]) == 2)
    finally:
        _gh = real_gh
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(_selftest())
    sys.exit(main(sys.argv[1:]))
