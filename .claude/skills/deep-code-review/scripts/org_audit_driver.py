#!/usr/bin/env python3
"""org_audit_driver.py: review_checks.sh over a repo list, one result file per repo.

Usage: org_audit_driver.py --repos FILE --out DIR [--timeout SECS] [--allow-partial]

FILE: one `owner/repo` per line ('#' and blank lines skipped). Per repo: shallow clone then `git fetch --unshallow`
into a fresh mkdtemp dir, then `review_checks.sh --full --full-history` (never --tests, which runs repo
code). Semgrep is forced to the bundled rules via REVIEW_SEMGREP_CONFIG, so a repo's own .semgrep.yml is ignored.
Output in --out: `<owner>__<repo>-<YYYYMMDD>.json` (the findings array) and `summary-<YYYYMMDD>.tsv`
(repo, status OK|PARTIAL|FAILED, findings, NOT CHECKED tools or the failure reason). A clone or scan failure is a FAILED
row (a review_checks failure appends its last stderr line, 200 chars max), never skipped. A review_checks run killed at --timeout is a PARTIAL row: its findings so far are kept and each unfinished tool
(plus "review_checks" for checks never started) is a not-checked row "timed out"; if its progress file is unreadable every tool seen counts as timed out. The clone uses --filter=blob:limit=5m;
each history blob it skipped is a git-clone not-checked row in the JSON (one aggregated entry in the summary). Exit 0 = every repo scanned; 1 = any FAILED (also a failed rev-list of skipped blobs); 3 = any PARTIAL and no FAILED, unless --allow-partial (then 0); 2 = usage or an empty list. NOT CHECKED tools do not fail the
run but are listed per repo: they are unchecked surface, not a clean result.
Private repos: if ORG_AUDIT_TOKEN is set it reaches ONLY the git clone/fetch children, as an `http.extraHeader` Basic
auth header appended to the parent's GIT_CONFIG_COUNT/KEY_n/VALUE_n env at index COUNT (parent entries kept) (never in the URL, argv or .git/config). Every other child
(review_checks and its scanners) runs with ORG_AUDIT_TOKEN, GH_TOKEN, GITHUB_TOKEN removed and no header, and the token
(raw and base64) is masked in any FAILED reason. --out is created (or chmod-ed) 0700.
Env: ORG_AUDIT_BASE_URL (default https://github.com) and ORG_AUDIT_REVIEW_CHECKS (script path) exist for tests.
Side effects: network clones; writes only under --out and its own temp dir, which is removed on exit.
Repo-local scanner config (.gitleaks.toml, .gitleaks-allow, .gitleaksignore, .trivyignore, ...) is deleted in the temp clone
before scanning, so a repo cannot allowlist its own findings; history is still scanned in full. Only root-level
files from UNTRUSTED_CFG are stripped: nested or other-named configs and linter configs (ruff, shellcheck) are NOT.
Every tracked symlink is removed too. Children run with stdin closed, no prompts, no host git config, hooks off,
and are killed (whole process group) on --timeout. Two repos mapping to one output name: the later is FAILED.
"""
import argparse, base64, datetime, glob, json, os, re, signal, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
# Repo-root config an untrusted repo could use to allowlist or silence its own findings; review_checks.sh and the
# tools read them from the tree or from HEAD. Removed in the temp clone (history is still scanned in full).
UNTRUSTED_CFG = [".gitleaks.toml", ".gitleaks-allow", ".gitleaksignore", ".semgrep.yml", ".semgrep", ".semgrepignore",
                 ".trivyignore", "trivy.yaml", "osv-scanner.toml", ".checkov.yaml", ".checkov.yml", ".hadolint.yaml",
                 ".hadolint.yml", "zizmor.yml", ".github/zizmor.yml", ".trufflehogignore"]
NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*/(?!\.{1,2}$)[A-Za-z0-9._-]+$")  # repo may lead with a dot, never be . or ..


# Neutral env for every child: no prompts, no host/system git config, only https/file transports, C locale.
SECRET_ENV = ("ORG_AUDIT_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")
ENV = dict({k: v for k, v in os.environ.items() if k not in SECRET_ENV}, GIT_TERMINAL_PROMPT="0", LC_ALL="C", GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL="/dev/null",
           GIT_ALLOW_PROTOCOL="https:file")
GIT = ["git", "-c", "core.hooksPath=/dev/null"]


def run(cmd, timeout=None, env=None, inp=None):
    """subprocess with stdin closed (or inp), own session, whole process group killed on timeout."""
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE if inp is not None else subprocess.DEVNULL, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, errors="replace", env=env or ENV, start_new_session=True)
    try:
        out, err = p.communicate(inp, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(p.pid, signal.SIGKILL)
        p.communicate()
        raise
    return subprocess.CompletedProcess(cmd, p.returncode, out, err)


def timed_out(rcd, timeout):
    """Rows for a review_checks run killed at --timeout: its raw findings so far plus a not-checked row per unfinished tool."""
    rows, nc, seen, ok = [], set(), set(), False
    for d in glob.glob(os.path.join(rcd, "review.*")):
        try:
            for l in open(os.path.join(d, "raw"), errors="replace"):
                t = l.rstrip("\n").split("\t")
                if len(t) == 5:
                    seen.add(t[0])
                    rows.append({"file": t[1], "line": int(t[2]) if t[2].isdigit() else 0, "rule": t[3], "message": t[4], "text": f"{t[3]}: {t[4]}", "tool": t[0]})
        except OSError:
            pass
        try:
            st = [l.split(None, 1) for l in open(os.path.join(d, "progress")) if l.strip()]
            nc = {x[1].strip() for x in st if x[0] == "start"} - {x[1].strip() for x in st if x[0] == "done"}
            ok = True
        except OSError:
            pass
    msg = f"timed out after {timeout}s, results are partial"
    if not ok:  # fail closed: no readable progress, so no tool counts as finished
        msg += ", progress unreadable so every check counts as timed out"
        nc = seen
    for t in sorted(nc) + ["review_checks"]:  # the last row covers checks that never started (every check when progress is unreadable)
        rows.append({"file": ".", "line": 0, "rule": "not-checked", "message": msg, "text": f"not-checked: {msg}", "tool": t})
    return rows


def audit(repo, tmp, rc_script, base_url, timeout):
    """Return (findings_json_text, rows, not_checked) or raise RuntimeError(reason)."""
    dest = os.path.join(tmp, "clone")
    url = f"{base_url}/{repo}.git"
    tok = os.environ.get("ORG_AUDIT_TOKEN")
    n = int(ENV.get("GIT_CONFIG_COUNT") or 0)  # keep parent proxy/CA entries, append the header after them
    genv = ENV if not tok else dict(ENV, GIT_CONFIG_COUNT=str(n + 1), **{f"GIT_CONFIG_KEY_{n}": "http.extraHeader",
        f"GIT_CONFIG_VALUE_{n}": "Authorization: Basic " + base64.b64encode(f"x-access-token:{tok}".encode()).decode()})
    for cmd in (GIT + ["clone", "--quiet", "--depth", "1", "--filter=blob:limit=5m", "--", url, dest], GIT + ["-C", dest, "fetch", "--quiet", "--unshallow"]):
        r = run(cmd, timeout=timeout, env=genv)
        if r.returncode and "--unshallow" in cmd and "does not make sense" in r.stderr:
            continue  # already complete (one-commit repo): nothing to unshallow
        if r.returncode:
            raise RuntimeError(f"{'fetch' if '-C' in cmd else 'clone'} failed (exit {r.returncode})")
    # Drop untrusted config and every symlink (a link could make a tool read a host file), commit it in the temp clone.
    r = run(GIT + ["-C", dest, "ls-files", "-s", "-z"], timeout=timeout)
    if r.returncode:
        raise RuntimeError(f"ls-files failed (exit {r.returncode})")
    links = [e.split("\t", 1)[1] for e in r.stdout.split("\0") if e.startswith("120000 ")]
    r = run(GIT + ["-C", dest, "rm", "-rq", "--ignore-unmatch", "--pathspec-from-file=-", "--pathspec-file-nul"],
            timeout=timeout, inp="\0".join(UNTRUSTED_CFG + links) + "\0")
    if r.returncode:
        raise RuntimeError(f"config strip failed (exit {r.returncode})")
    r = run(GIT + ["-C", dest, "diff", "--cached", "--quiet"], timeout=timeout)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"diff --cached failed (exit {r.returncode})")
    if r.returncode == 1:  # something was removed: commit it so reads from HEAD miss it too
        r = run(GIT + ["-C", dest, "-c", "user.name=audit", "-c", "user.email=audit@example.com", "commit", "-qm", "drop repo-local scan config"], timeout=timeout)
        if r.returncode:
            raise RuntimeError(f"config strip commit failed (exit {r.returncode})")
    rcd = os.path.join(tmp, "rc"); os.mkdir(rcd)  # review_checks' temp dir lands here, so a kill leaves its partial rows readable
    env = dict(ENV, TMPDIR=rcd, REVIEW_SEMGREP_CONFIG=os.path.join(HERE, "..", "templates", "semgrep-taint"))
    partial = False
    try:
        r = run(["bash", rc_script, "--repo", dest, "--full", "--full-history"], env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        partial = True
        r = subprocess.CompletedProcess([], 0, json.dumps(timed_out(rcd, timeout)), "")
    last = next((l.strip() for l in reversed(r.stderr.splitlines()) if l.strip()), "")
    why = f": {last.replace(chr(9), ' ')[:200]}" if last else ""
    try:
        rows = json.loads(r.stdout)
        assert isinstance(rows, list)
    except (ValueError, AssertionError):
        raise RuntimeError(f"review_checks gave no JSON (exit {r.returncode}){why}")
    if r.returncode:
        raise RuntimeError(f"review_checks exit {r.returncode}{why}")
    # Blobs the clone filter skipped (listed after the scan, so lazily fetched ones are not reported) are unchecked surface.
    rl = run(GIT + ["-C", dest, "rev-list", "--objects", "--all", "--missing=print"], timeout=timeout)
    if rl.returncode:  # an unreadable listing must not read as "no blob skipped"
        raise RuntimeError(f"rev-list --missing failed (exit {rl.returncode})")
    miss = rl.stdout.split()
    rows += [{"file": o[1:13], "line": 0, "rule": "not-checked", "message": "blob over 5m skipped by the clone filter",
              "text": f"not-checked: blob {o[1:13]} over 5m skipped by the clone filter", "tool": "git-clone"} for o in miss if o.startswith("?")]
    nc = {m.strip() for m in re.findall(r"NOT CHECKED: ([^\n]*)", r.stderr)}
    nc |= {f"{x.get('tool')} ({x.get('message')})" for x in rows if x.get("rule") == "not-checked" and x.get("tool") != "git-clone"}
    if n := sum(x.get("tool") == "git-clone" for x in rows):
        nc.add(f"git-clone ({n} blobs over 5m skipped)")
    return json.dumps(rows), rows, sorted(nc), partial


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--allow-partial", action="store_true", help="exit 0 even when a repo is PARTIAL (timed out)")
    a = ap.parse_args()
    try:
        names = [l.strip() for l in open(a.repos) if l.strip() and not l.lstrip().startswith("#")]
    except OSError as e:
        print(f"org_audit_driver: {e}", file=sys.stderr)
        return 2
    if not names:
        print("org_audit_driver: empty repo list", file=sys.stderr)
        return 2
    os.makedirs(a.out, mode=0o700, exist_ok=True)
    os.chmod(a.out, 0o700)
    day = datetime.date.today().strftime("%Y%m%d")
    rc_script = os.environ.get("ORG_AUDIT_REVIEW_CHECKS") or os.path.join(HERE, "review_checks.sh")
    base_url = os.environ.get("ORG_AUDIT_BASE_URL", "https://github.com").rstrip("/")
    lines, failed, partial, seen = [], 0, 0, set()
    for repo in names:
        try:
            if not NAME.match(repo):
                raise RuntimeError("bad repo name (want owner/repo)")
            fn = f"{repo.replace('/', '__')}-{day}.json"
            if fn.lower() in seen:
                raise RuntimeError("output name collision with an earlier repo")
            seen.add(fn.lower())
            with tempfile.TemporaryDirectory(prefix="org-audit-") as tmp:  # own mkdtemp dir, removed on exit
                text, rows, nc, part = audit(repo, tmp, rc_script, base_url, a.timeout)
            with open(os.path.join(a.out, fn), "w") as f:
                f.write(text)
            partial += bool(part)
            lines.append(f"{repo}\t{'PARTIAL' if part else 'OK'}\t{len(rows)}\t" + ("; ".join(nc) or "-"))
        except (RuntimeError, subprocess.TimeoutExpired, OSError) as e:
            failed += 1
            msg = str(e).replace(chr(9), ' ').replace(chr(10), ' ')
            tok = os.environ.get("ORG_AUDIT_TOKEN")
            for secret in (tok, tok and base64.b64encode(f"x-access-token:{tok}".encode()).decode()):
                msg = msg.replace(secret, "***") if secret else msg
            lines.append(f"{repo}\tFAILED\t-\t{msg}")
    out = "repo\tstatus\tfindings\tnot_checked_or_reason\n" + "\n".join(lines) + "\n"
    with open(os.path.join(a.out, f"summary-{day}.tsv"), "w") as f:
        f.write(out)
    sys.stdout.write(out)
    return 1 if failed else 3 if partial and not a.allow_partial else 0


if __name__ == "__main__":
    sys.exit(main())
