#!/usr/bin/env python3
"""audit_sweep.py: recurring audit sweep that reports only NEW findings and alerts when a run itself fails.

Usage: audit_sweep.py --state FILE --org ORG [--token-env VAR]
       audit_sweep.py --state FILE --local REPO      (no network; used by the test)

Per repo the `--state` JSON keeps the last scanned HEAD sha and the fingerprints already reported
(see `fingerprint()`). Each run, per repo:
  HEAD == last sha, same tool stamp     -> skipped, no scan.
  last sha is an ancestor of HEAD       -> two scans, rows merged: plain diff mode `--repo R --base LAST` (rows with `new: false`, not on a line
                                           added since LAST, are dropped) and `--base LAST --history` (the real scanner emits `new` only in plain
                                           diff mode, so history rows are all kept). mode `delta`.
  no last sha (first run)               -> `--full` scan (with `--timeout FULL_TIMEOUT`, as every --full scan). mode `first`.
  last sha missing or not an ancestor   -> history was rewritten: `--full` rescan. mode `rewrite`.
  tool stamp changed (HEAD same or a descendant) -> `--full` rescan, mode `rescan`, even on an idle repo, plus a plain diff scan `--base LAST`
                                           when HEAD moved (only to mark re-added lines, see below). The stamp hashes review_checks.sh, the
                                           scripts/*.py, templates/semgrep-taint, templates/gitleaks.toml and which `review_checks.sh --list-tools`
                                           tools are on PATH, so a rule upgrade or a tool install re-reads old code (most tools emit no row when missing).
  last --full scan 7+ days old (`FULL_EVERY`) -> the same `rescan`: tool versions, advisory DBs and rule snapshots change outside the stamp.
Only fingerprints not yet in the state are reported, as TSV on stdout: `repo mode file rule tool fingerprint`; rows the hub hinted
`test-path` (a code-pattern scanner row in a test-only file) come last, as one `repo TESTPATH "<n> rows" rule tool` count line per tool and rule
(repo = org/name with --org, the absolute path with --local: the state key and the fingerprint use it, so two orgs or two
same-named repos never share state; a state entry keyed by a bare name, from before, is left unused and that repo gets a first run)
(fingerprint = first 12 hex chars). No finding text, message or secret value is ever printed or stored; the state
holds hashes only (repo names are hashed too; the stored sha is a public git object id; `full` is the epoch second of the last --full scan), so it is safe to keep next to
the cron job. Exit 0 = swept (findings or not, they are the TSV);
exit 1 = at least one repo failed to clone or scan (an `ERROR` row, the alert) or ended with a blocking gap (a `GAP` row, see below)
-- a failed repo keeps its old state and a blocked one its old sha, so the next run rescans the same range; exit 2 = usage; exit 3 = the sweep could not start (unreadable or corrupt
--state, or the org listing failed) or the new state could not be written (OSError, fsync'd temp file then atomic
rename): one `ERROR` row, state untouched. Repos are listed with `org_leak_sweep.list_repos`.
Edge cases: empty org = header-only TSV; an empty repo (no commit, no ref) is skipped (no row, not an error); a fingerprint reported once is not reported again unless its row sits on a line added since the
last scan (`new: true` in the plain diff scan of a delta or rescan; a `-summary` row when one of its member lines was added): a fixed
finding that is re-added is reported again, and so is a moved or reformatted line, once. While a blocking gap holds the sha every run
rediffs the same range, so those fingerprints are kept in `held` and not reported again until the sha advances. A repo that vanishes
from the org keeps its (hashed) state entry; a rewrite rescan reports only findings whose fingerprint is new. Fingerprint = sha256 of
`repo|tool|rule|file|text` with the volatile parts of the text normalized (see `norm`); rows with the same tool, rule, file and text in
one scan get an occurrence index, so the same text on two lines stays two alerts. `not-checked` rows (a missing tool or an unread file)
are coverage gaps, never findings: counted on stderr, never fingerprinted, reported as one `COVERAGE` row (`repo COVERAGE  N
not-checked`). The `CORE` scanners the hub skips without any row when missing are named in a second `COVERAGE` row (`repo COVERAGE
not installed  <tools>`) on every scan of a host that lacks them. While a repo has a gap other than a not-installed tool (see
`not_installed`), a design, config or provisioning gap a rescan cannot close (see `ENV`; one `ENVGAP` row per tool) or a noise path a
--full scan never reads (see `NOISE`) -- a blocking gap: a timeout, crash or unread file, one `GAP` row per tool -- its sha and tool stamp
are not advanced, so the next run rescans the same range (new findings are still recorded as seen); a "config changed in this diff" ENV row
advances the sha but not the tool stamp, so the next run rescans --full. The missing-tool list (binary from `BIN`, else the tool name; dep-scan records the missing
auditor) is replaced by a full scan and merged by a delta, since the hub names a missing tool only when a file it routes to is in
range; a listed tool that appears on PATH is rescanned once, then dropped even if the hub still reports it. A scanner that exits 0 with
empty or whitespace-only stdout is a tool error (ERROR row, exit 1, state not advanced), never "0 findings" (a clean scan prints `[]`).
Every non-printable character (tab, newline, any other line or control break) in a TSV cell becomes a space. Override the scanner with
env AUDIT_SWEEP_CHECKS=path (tests only).
Side effects: --org clones into a temporary directory that is deleted after each repo; rewrites --state atomically after each repo,
after that repo's rows are flushed to stdout. The scanned repo's files are only read, but the hub writes review-checks-last.json into
its git dir (`git rev-parse --git-common-dir`). The scanner runs without `SCRUB` (GH_TOKEN, GITHUB_TOKEN, the --token-env variable,
REVIEW_TEST_CMD, REVIEW_FUZZ, REVIEW_SCORECARD), so it gets no token and never runs repo code (tests, fuzz targets, a repo-local tsc, eslint, psalm, a
configured ansible-lint, checkov or tflint configs: each is then a not-checked `ENV` row).
"""
import argparse, glob, hashlib, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from org_leak_sweep import list_repos, run  # noqa: E402


def norm(t):
    """Row text without the parts that change between scans of the same finding: "<N> commits since", the count and first-3 line numbers
    of per-file and fixture summary rows (any path characters, up to "; names: ", " [likely-fixture]" or the end), a "; added: ..."
    extension, the "[corroborated by: ...]" suffix and the " [test-path]" hint. Other digits stay, so rows differing only by digits stay distinct."""
    t = re.sub(r" \[corroborated by: [^\]]*\]| \[test-path\]", "", t)
    t = re.sub(r"; added: \d+(?:, \d+)*", "", t)
    t = re.sub(r"\d+ commits since", "# commits since", t)
    t = re.sub(r"^((?:\S+: )?)\d+ (?=\S+ hits )", r"\1# ", t)
    return re.sub(r"\(showing 3 of \d+; REVIEW_FIXTURE_ROWS=all for every row\)(?:: .*?(?=; names: | \[likely-fixture\]|\Z))?", "(showing 3 of #; ...)", t)


def fingerprint(repo, row, occ=0):
    """Stable id of repo, tool, rule, file and the row text (see `norm`). `occ` = the row's index (see `tag`) among rows of one scan with
    the same tool, rule, file and text (the same text on two lines of one file is two findings); index 0 hashes without a suffix."""
    ident = norm(row.get("text", "")) + (f"#{occ}" if occ else "")
    return hashlib.sha256("|".join([repo, row.get("tool", ""), row.get("rule", ""), row.get("file", ""), ident]).encode()).hexdigest()


# seconds between forced --full rescans: a new advisory against an unchanged lockfile or a new built-in detector reaches idle code
FULL_EVERY = 7 * 86400
FULL_TIMEOUT = "600"  # per-tool seconds for a --full scan: the hub's 60 s default fits a diff, and a whole big repo's semgrep runs longer
# review_checks.sh `have` skips these without a row when missing (stderr only): see `stamp` and the CORE COVERAGE row in `sweep_repo`
CORE = ("shellcheck", "semgrep", "trivy", "osv-scanner", "ruff/pyflakes")
HUB_SH = os.path.join(HERE, "review_checks.sh")  # the shipped hub: its hint table and tool list, even when AUDIT_SWEEP_CHECKS fakes the scan
CHECKS = os.environ.get("AUDIT_SWEEP_CHECKS") or HUB_SH


def stamp():
    """Hash of the scanner code (CHECKS, scripts/*.py, templates/semgrep-taint, templates/gitleaks.toml: the hub's allowlist template) and
    of which `review_checks.sh --list-tools` tools are on PATH: the `CORE` tools emit no row when missing, so only this catches their
    install."""
    h = hashlib.sha256()
    tpl = os.path.join(HERE, "..", "templates")
    py = sorted(glob.glob(os.path.join(HERE, "*.py")))
    taint = sorted(os.path.join(d, n) for d, _, ns in os.walk(os.path.join(tpl, "semgrep-taint")) for n in ns)
    for f in [CHECKS] + py + taint + [os.path.join(tpl, "gitleaks.toml")]:
        try:
            with open(f, "rb") as fh:
                h.update(fh.read())
        except OSError:
            h.update(b"?")
    h.update(" ".join(t for t in run(["bash", HUB_SH, "--list-tools"]).stdout.split() if installed(t)).encode())
    return h.hexdigest()


def git(repo, *a):
    return run(["git", "-C", repo, *a])


# env never passed to the scanner: tokens (main() adds the --token-env variable), the opt-ins that make the hub run repo code, and
# REVIEW_SCORECARD (it needs GITHUB_TOKEN, which is scrubbed, so it could only ever add a blocking "needs GITHUB_TOKEN" gap)
SCRUB = {"GH_TOKEN", "GITHUB_TOKEN", "REVIEW_TEST_CMD", "REVIEW_FUZZ", "REVIEW_SCORECARD"}


def scan1(repo, *flags):
    """One review_checks.sh run on repo with the `SCRUB` variables removed from its env. Returns its JSON rows; raises RuntimeError on a
    non-zero exit, empty stdout or a non-array document."""
    r = run(["bash", CHECKS, "--repo", repo, *flags], env={k: v for k, v in os.environ.items() if k not in SCRUB})
    if r.returncode:
        raise RuntimeError(f"scanner exit {r.returncode}")
    if not r.stdout.strip():  # a clean scan prints `[]`; silence is a broken tool, never "0 findings"
        raise RuntimeError("scanner produced no output")
    rows = json.loads(r.stdout)
    if not isinstance(rows, list):
        raise RuntimeError("scanner output not a JSON array")
    return rows


# hub row names that are not one binary on PATH (review_checks.sh): the binaries whose install fixes the gap. dep-scan rows record the
# missing auditor itself (see `scan`); its entry only maps states written before that. eslint-security runs a project-local eslint: no PATH binary.
BIN = {"ruff/pyflakes": ("ruff", "pyflakes"), "zap": ("zap-baseline.py", "docker"), "dast": ("zap-baseline.py", "docker", "nuclei"),
       "dep-scan": ("osv-scanner", "trivy", "npm", "pnpm", "pip-audit"), "ruff-security": ("ruff",), "bundler-audit": ("bundle-audit",),
       "node-check": ("node",), "go-vet": ("go",)}


def installed(tool):
    """True when a binary that fixes the tool's gap is on PATH (see `BIN`). bundler-audit also needs the local ruby-advisory-db the hub
    checks (non-empty $BUNDLER_AUDIT_DB, else ~/.local/share/ruby-advisory-db; never downloaded): the binary alone still gives a gap row."""
    if tool == "bundler-audit":
        db = os.environ.get("BUNDLER_AUDIT_DB") or os.path.join(os.environ.get("HOME") or "/nonexistent", ".local", "share", "ruby-advisory-db")
        try:
            if not os.listdir(db):
                return False
        except OSError:
            return False
    return any(shutil.which(b) for b in BIN.get(tool, (tool,)))


def hub_table():
    """{tool: (flag status, install hint)} from the `hub=(` registry of the shipped review_checks.sh (the rows `--list-tools` reads);
    {} when it cannot be read, so its hint rows stay blocking (fail closed)."""
    try:
        with open(HUB_SH) as fh:
            body = fh.read().split("\nhub=(\n", 1)[1].split("\n)\n", 1)[0]
    except (OSError, IndexError):
        return {}
    return {m[1]: (m[2], m[3]) for m in re.finditer(r"^  '([a-z0-9_-]+);(\w+);[^']*;([^';]+)'", body, re.M)}


HUB = hub_table()
INSTALL = re.compile(r"install: (?:(?:pipx|brew|gem|go) install [\w@./-]+|npm install -g [\w@./-]+|cargo install [\w-]+ --locked"
                     r"|npm i -D eslint eslint-plugin-security \(project-local, never npx\)|pipx install zaproxy, or docker \+ ghcr\.io/zaproxy/zaproxy:stable)")
AUDITOR = "(npm|pnpm|pip-audit)"  # review_checks.sh dependency-scan fallback: `at[0]`
DEP_MISSING = re.compile(r"no dependency scan ran: osv-scanner/trivy gave no result and " + AUDITOR + " is not installed")
DEP_ENV = re.compile(r"no dependency scan ran; set REVIEW_OSV=1 to scan \(osv-scanner, else " + AUDITOR + r"\)")


def msg(x):
    """The hub's raw not-checked message: real rows carry it in `message` and a "not-checked: "-prefixed copy in `text`."""
    return x.get("message", x.get("text", ""))


def not_installed(x):
    """A hub `not-checked` row for a tool that is not installed, matched by full-string match on the hub's own emitters (review_checks.sh
    `skip`, `have`, `pneed`, the gitleaks/trufflehog fallback, the dep-scan fallback): empty file and text "not installed", "not installed;
    secrets were not scanned" (gitleaks, trufflehog), "install: <hint>" with the hint the hub table gives this tool (`HUB`) or one of the
    `INSTALL` forms (pneed, codeql), or bundler-audit's "no local ruby-advisory-db" (a provisioning gap, see `installed`); or tool dep-scan
    with its "... <auditor> is not installed" text. "heavy lease full" is transient and blocking. Rows whose text starts with a repo file name (cosign,
    tfsec) carry a file or another tool, so a file named like a marker cannot forge one. Any other text is a real gap (a `NA` row, a checker
    that does not apply, is no gap at all: see `scan`)."""
    t = msg(x)
    if x.get("rule") != "not-checked":
        return False
    if x.get("tool") == "dep-scan":
        return bool(DEP_MISSING.fullmatch(t))
    return x.get("file", "") == "" and (t == "not installed" or bool(INSTALL.fullmatch(t)) or (x.get("tool") in HUB and t == "install: " + HUB[x["tool"]][1])
                                        or (x.get("tool") in ("gitleaks", "trufflehog") and t == "not installed; secrets were not scanned")
                                        or (x.get("tool") == "bundler-audit" and t == "no local ruby-advisory-db: bundler-audit would download one"))


# review_checks.sh rows that mean "this checker does not apply here" (exact tool and text, hub-set: a repo file name cannot forge both).
# guarddog judges only packages added since a base, so every --full scan of a package-lock.json repo emits its row. Other SKIPPED rows
# (guarddog unparseable, wrong version) are real misses and stay blocking.
NA = {"tenant-scope": "SKIPPED: no *.prisma", "route-auth": "SKIPPED: no HTTP handlers", "header-config": "SKIPPED: no supported web app",
      "attempt-limit": "SKIPPED: no credential check or sign-in route", "cost-limit": "SKIPPED: no HTTP handler",
      "insecure-defaults": "SKIPPED: no source files", "csrf-cookie": "SKIPPED: no HTTP handler or cookie", "pii-data": "SKIPPED: no source file",
      "guarddog": "SKIPPED: --full has no base to find newly added packages against"}
# review_checks.sh `nskip`, any tool, one row per file: a --full scan never reads mocks/, fixtures/, e2e/, __mocks__/ or testdata/
# (REVIEW_NOISE_RE) while a diff scan does. A gap by design that no rescan closes: counted in COVERAGE, never blocking.
NOISE = "noise path excluded by REVIEW_NOISE_RE, not scanned"


# review_checks.sh not-checked rows that rescanning cannot close (design or config, not a transient failure): tool -> (full-match text,
# file must be empty). Non-blocking like a missing tool, but listed by name as an ENVGAP row. dep-scan rows carry the lockfile as file,
# node-check's JSX row the first such file. A config file changed in a delta stays in the diff while a blocking gap holds the sha, so
# "changed in this diff" would block forever; that tool never read the range, so the row clears the tool stamp (see `sweep_repo`) and
# the next run is a --full rescan, which never skips a changed config. The "set REVIEW_TEST_CMD" rows are fixed by design: `SCRUB` drops it.
lit = lambda *s: re.compile("|".join(map(re.escape, s)))
CONFIG_CHANGED = " changed in this diff: "
PCODE = "it executes project code (its config and plugins); set REVIEW_TEST_CMD to run it"  # eslint-security, psalm, a configured ansible-lint
ENV = {"osv-scanner": (lit("REVIEW_OSV not set; osv-scanner queries the OSV API"), True),
       "dep-scan": (re.compile(DEP_ENV.pattern + "|" + re.escape("no dependency scan ran for this lockfile (no osv-scanner/trivy result and no fallback for its ecosystem)")), False),
       "node-check": (re.compile(r"\d+ \.js files hold JSX or markup that node --check cannot parse \(first 3: .+\); a JSX-aware linter or the project build judges them"), False),
       "eslint-security": (lit("eslint config or package.json changed in this diff: not run", PCODE, "the eslint config names no security plugin"), True),
       "rubocop": (lit(".rubocop*.yml changed in this diff: its config can require code, not run"), True),
       "sobelow": (lit("mix.exs or .sobelow-conf changed in this diff: its config is code, not run"), True),
       "ansible-lint": (lit(".ansible-lint or ansible.cfg changed in this diff: its config is code, not run", PCODE), True),
       "psalm": (lit("psalm.xml or composer.json changed in this diff: its config is code, not run", PCODE, "no psalm.xml at repo root"), True),
       "tsc": (lit("repo-local tsc not run (set REVIEW_TEST_CMD to run it: it executes project code)"), True),
       "checkov": (lit("a .checkov.yaml or .checkov.yml in the repo root can load Python checks (external-checks-dir); set REVIEW_TEST_CMD to run it"), True),
       "tflint": (re.compile(r".+: " + re.escape("a .tflint.hcl, .tflint.json or .tflint.d beside it can load plugin binaries; set REVIEW_TEST_CMD to run it")), True),
       # repo layout or host provisioning the hub never fetches: a rescan cannot close them, the FULL_EVERY rescan picks up a later fix
       "kubescape": (re.compile(re.escape("Helm chart templates are not rendered by the hub") + "|"
                                + re.escape("no local nsa.json and cis-v1.23-t1.0.1.json in ") + ".+" + re.escape(" (kubescape download artifacts; never fetched)")), True),
       "gosec": (lit("no go.mod at repo root"), True), "govulncheck": (lit("no go.mod at repo root", "go toolchain missing"), True),
       "staticcheck": (lit("no go.mod at repo root", "go toolchain missing"), True),
       "retire": (lit("REVIEW_RETIRE_JSREPO names no local jsrepository.json (never fetched)"), True),
       "cargo-deny": (lit("cargo toolchain missing"), True),
       "cargo-audit": (re.compile(re.escape("no local advisory DB at ") + ".+" + re.escape("/advisory-db (never fetched)")), True)}
ENV.update({n: (lit(f"{st} flags: skipped by default"), True) for n, (st, _) in HUB.items() if st != "verified" and n not in ENV})  # hub `nc "$hs flags: ..."`


def env_gap(x):
    e = ENV.get(x.get("tool"))
    return bool(e) and x.get("rule") == "not-checked" and bool(e[0].fullmatch(msg(x))) and (x.get("file", "") == "") == e[1]


def tag(rows):
    """Sets `_occ` on each row: its index among the rows of this one scan (before any filtering) with the same tool, rule, file and
    text. Per scan, so the same finding seen by both the diff and the history scan gets the same index in each."""
    n = {}
    for x in rows:
        k = (x.get("tool", ""), x.get("rule", ""), x.get("file", ""), norm(x.get("text", "")))
        x["_occ"], n[k] = n.get(k, 0), n.get(k, 0) + 1
    return rows


def scan(repo, base, full):
    """Returns (finding rows, fresh rows: plain diff rows with `new: true`, not-checked count, blocking tools: those with a gap other than
    a tool that is not installed, an `ENV` gap or a `NOISE` row, names of missing tools: see `not_installed`, dep-scan gives the auditor, tools with
    an `ENV` gap, True when one of those is a config-changed row: that tool did not read this range).
    full: rows and gaps come from one `--full` scan, and a base adds a plain diff scan used only for its fresh rows; else a diff plus a
    history scan against base. `new` exists only in plain diff mode, so the filter applies only there."""
    diff = tag(scan1(repo, "--base", base)) if base else []
    if full:
        raw = rows = tag(scan1(repo, "--timeout", FULL_TIMEOUT, "--full"))
    else:  # diff rows keep new is not False; history rows carry no `new` key
        hist = tag(scan1(repo, "--base", base, "--history"))
        raw = hist + diff
        rows = [x for x in diff if x.get("new") is not False] + hist
    raw = [x for x in raw if not (x.get("rule") == "not-checked" and NA.get(x.get("tool")) == msg(x))]  # checker does not apply: no gap
    gaps = sum(1 for x in raw if x.get("rule") == "not-checked")
    miss = {DEP_MISSING.fullmatch(msg(x))[1] if x.get("tool") == "dep-scan" else x.get("tool", "") for x in raw if not_installed(x)}
    block = sorted({x.get("tool", "") for x in raw if x.get("rule") == "not-checked" and not not_installed(x) and not env_gap(x) and not (x.get("file") and msg(x) == NOISE)})
    if gaps:  # a missing tool or unread file is a coverage gap, not a finding; its hint text varies by mode and install state
        print(f"audit_sweep: {gaps} not-checked row(s) skipped (tool missing or file unread)", file=sys.stderr)
    fresh = [x for x in diff if x.get("new") is True and x.get("rule") != "not-checked"]
    env = [x for x in raw if env_gap(x)]
    return ([x for x in rows if x.get("rule") != "not-checked"], fresh, gaps, block, sorted(miss), sorted({x["tool"] for x in env}),
            any(CONFIG_CHANGED in msg(x) for x in env))


def sweep_repo(name, path, st):
    r = git(path, "rev-parse", "--verify", "-q", "HEAD")
    if r.returncode:  # 1 = a git repo without a HEAD commit; with no ref at all it is empty: nothing to scan, not an error
        if r.returncode == 1 and not git(path, "for-each-ref", "--count=1").stdout.strip():
            return []
        raise RuntimeError("no HEAD")
    head = r.stdout.strip()
    last = st.get("sha")
    tool = stamp()
    back = [m for m in st.get("missing", []) if installed(m)]  # tools skipped as not installed that are on PATH now: their old range was never scanned
    now = int(time.time())
    due = now - st.get("full", 0) >= FULL_EVERY  # a state from before `full` existed is due once
    if last == head and st.get("tool") == tool and not back and not due:
        return []
    if not last:
        mode = "first"
    elif (st.get("tool") != tool or back or due) and (last == head or git(path, "merge-base", "--is-ancestor", last, "HEAD").returncode == 0):
        mode = "rescan"  # rule or tool upgrade: re-read everything, even an idle repo
    elif git(path, "merge-base", "--is-ancestor", last, "HEAD").returncode == 0:
        mode = "delta"
    else:
        mode = "rewrite"
    rows, fresh, gaps, block, miss, env, unread = scan(path, last if mode == "delta" or (mode == "rescan" and last != head) else None, mode != "delta")
    seen, held = set(st.get("seen", [])), set(st.get("held", []))
    # a row on a line added since the last scan is a new occurrence even when its fingerprint was seen (fixed, then re-added); `held`:
    # already reported for this same range (a blocking gap keeps the sha, so the next run rediffs it)
    fresh_fp = {fingerprint(name, x, x.get("_occ", 0)) for x in fresh} - held
    out, out_fp, tp = [], set(), {}
    for x in rows + fresh:  # a rescan's fresh rows come from its diff scan; out_fp drops the copies
        fp = fingerprint(name, x, x.get("_occ", 0))
        if (fp not in seen or fp in fresh_fp) and fp not in out_fp:
            out_fp.add(fp)
            seen.add(fp)
            if (x.get("hint") or "").startswith("test-path"):  # the hub's test-path hint: counted per (tool, rule) below, fingerprint still stored
                k = (x.get("tool", ""), x.get("rule", "")); tp[k] = tp.get(k, 0) + 1
            else:
                out.append((name, mode, x.get("file", ""), x.get("rule", ""), x.get("tool", ""), fp[:12]))
    st["seen"] = sorted(seen)
    if gaps:  # coverage rows list every gap, a missing tool included
        out.append((name, "COVERAGE", "", f"{gaps} not-checked", "", ""))
    gone = [t for t in CORE if not installed(t)]
    if gone:  # the hub names these only on stderr: without this row a host lacking semgrep sweeps "clean"
        out.append((name, "COVERAGE", "", "not installed", " ".join(gone), ""))
    out += [(name, "ENVGAP", "", "", t, "") for t in env]  # design/config gaps a rescan cannot close, listed by tool
    out += [(name, "GAP", "", "", t, "") for t in block]  # a timeout, crash or unread file: holds the sha, and main() exits 1
    out += [(name, "TESTPATH", f"{n} rows", r, t, "") for (t, r), n in sorted(tp.items())]  # after every other row: code-pattern rows in test-only files
    # one rescan per install: a tool on PATH that the hub still calls not installed is dropped, so the next run does not rescan forever.
    # A delta reads only the changed files and the hub names a missing tool only for a file it routes to: keep the old names (back is empty).
    st["missing"] = sorted(set(miss) | set(st.get("missing", []))) if mode == "delta" else [m for m in miss if m not in back]
    if not block:  # a tool that is not installed cannot be fixed by rescanning; an unread file or a tool that errored keeps the old range
        st["sha"], st["tool"] = head, None if unread else tool  # a config-changed tool skipped this range: next run rescans --full
        if mode != "delta":
            st["full"] = now
        st.pop("held", None)
    else:
        st["held"] = sorted(held | fresh_fp)
    return out


def save(state, path):
    """Atomic write (fsync'd temp file, rename). Returns 3 and prints an ERROR row on OSError, else 0."""
    d, tmpname = os.path.dirname(os.path.abspath(path)), None
    try:
        os.makedirs(d, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", dir=d, delete=False) as fh:
            tmpname = fh.name
            json.dump(state, fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmpname, path)
    except BaseException as e:  # also KeyboardInterrupt or a non-OSError from json.dump: never leave the temp file behind
        if tmpname and os.path.exists(tmpname):
            os.unlink(tmpname)
        if not isinstance(e, OSError):
            raise
        print(f"-\tERROR\t\tstate not saved: {type(e).__name__}\t\t")
        return 3
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--org")
    g.add_argument("--local", help="sweep this one local repo, no network")
    ap.add_argument("--state", required=True)
    ap.add_argument("--token-env", help="env var holding a token; default `gh auth token`")
    a = ap.parse_args()
    if a.token_env:
        SCRUB.add(a.token_env)
    print("repo\tmode\tfile\trule\ttool\tfingerprint")
    try:
        state = {}
        if os.path.exists(a.state):
            with open(a.state) as fh:
                state = json.load(fh)
            if not isinstance(state, dict):
                raise ValueError("state is not a JSON object")
        if a.org:
            token = os.environ.get(a.token_env, "") if a.token_env else run(["gh", "auth", "token"]).stdout.strip()
            repos = [(f"{a.org}/{n}", u) for n, u in list_repos(a.org, token)]  # org/name: two orgs in one state never share an entry
        else:
            repos = [(os.path.abspath(a.local), os.path.abspath(a.local))]  # the path: two local repos with one basename stay apart
    except (Exception, SystemExit) as e:  # list_repos exits with a message on a failed listing
        print(f"-\tERROR\t\tsweep not started: {type(e).__name__}\t\t")
        return 3
    bad = False
    for name, url in repos:
        tmp = tempfile.mkdtemp(prefix="audit-sweep-") if a.org else None
        try:
            path = url
            if tmp:
                path = os.path.join(tmp, "r")
                if run(["git", "clone", "-q", "--", url, path]).returncode:
                    raise RuntimeError("clone failed")
            key = hashlib.sha256(name.encode()).hexdigest()[:16]
            st = dict(state.get(key, {}))
            rows = sweep_repo(name, path, st)
            for r in rows:
                print("\t".join("".join(ch if ch.isprintable() else " " for ch in c) for c in r))  # a file name may hold a tab, newline or other break
            state[key] = st  # only once its rows are printed: a failed print keeps the old state
            bad = bad or any(r[1] == "GAP" for r in rows)  # a blocked repo is an alert, not a clean sweep
        except Exception as e:
            print(f"{name}\tERROR\t\t{type(e).__name__}: {e}\t\t")
            bad = True
        finally:
            if tmp:
                shutil.rmtree(tmp, ignore_errors=True)
        sys.stdout.flush()  # rows reach stdout before save() records them as seen: a kill in between re-reports a row, never loses one
        if save(state, a.state):  # per repo: a later crash or kill keeps finished repos' state
            return 3
    return save(state, a.state) or (1 if bad else 0)


if __name__ == "__main__":
    sys.exit(main())
