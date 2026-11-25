#!/usr/bin/env python3
"""Tests: rows that every --full scan emits by design (guarddog has no base, a noise path is never read, JSX that node cannot parse)
never hold the sha, so the next run is an incremental delta, end to end on the real review_checks.sh too; ansible-lint and psalm
"changed in this diff" rows are ENVGAP rows, and every such row forces one --full rescan because that tool never read the range; a
missing ruby-advisory-db is a missing tool, and provisioning the DB rescans once; a rescan reports a noise-path finding that only its
diff scan sees; the CodeQL license-gate row is an ENVGAP row and REVIEW_CODEQL is scrubbed from the scanner env. Every sweep runs with an isolated environment (PATH t/bin:/usr/bin:/bin, HOME in the temp dir)."""
import re
import atexit, json, os, shutil, subprocess, sys, tempfile, types

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
import audit_sweep as a  # noqa: E402

HUB_SRC = open(os.path.join(D, "review_checks.sh")).read()
NOISE = "noise path excluded by REVIEW_NOISE_RE, not scanned"
GUARDDOG = "SKIPPED: --full has no base to find newly added packages against"
JSX = "2 .js files hold JSX or markup that node --check cannot parse (first 3: a.js, b (1).js); a JSX-aware linter or the project build judges them"
RUBY_DB = "no local ruby-advisory-db: bundler-audit would download one"
CODEQL = "off by default (license: OSI-licensed code only); set REVIEW_CODEQL=1"
CONFIG = {"ansible-lint": ".ansible-lint or ansible.cfg changed in this diff: its config is code, not run",
          "psalm": "psalm.xml or composer.json changed in this diff: its config is code, not run",
          "eslint-security": "eslint config or package.json changed in this diff: not run",
          "rubocop": ".rubocop*.yml changed in this diff: its config can require code, not run",
          "sobelow": "mix.exs or .sobelow-conf changed in this diff: its config is code, not run"}
gap = lambda tool, text, file="": {"rule": "not-checked", "tool": tool, "file": file, "text": "not-checked: " + text, "message": text}

# fake review_checks.sh: like the hub's nskip, --full never reads fixtures/ and emits a noise row instead; a BAD line is a finding
# (`new: true` in plain diff mode); cfg.json adds not-checked rows per scan kind ("full", "diff" or "hist").
FAKE = r'''import json, os, subprocess, sys
av = sys.argv
repo = av[av.index("--repo") + 1]
t = os.path.dirname(repo)
open(t + "/calls.log", "a").write(" ".join(av[3:]) + "\n")
cfg = json.load(open(t + "/cfg.json"))
full, diff = "--full" in av, "--base" in av and "--history" not in av
ls = ["diff", "--name-only", av[av.index("--base") + 1] + "...HEAD"] if "--base" in av else ["ls-files"]
rows = []
for f in subprocess.run(["git", "-C", repo, *ls], capture_output=True, text=True).stdout.split():
    if full and f.startswith("fixtures/"):
        m = "noise path excluded by REVIEW_NOISE_RE, not scanned"
        rows.append({"file": f, "line": 0, "rule": "not-checked", "message": m, "text": "not-checked: " + m, "tool": "semgrep"})
    elif "BAD" in open(os.path.join(repo, f)).read():
        rows.append({"file": f, "line": 1, "rule": "r", "text": "BAD thing", "tool": "fake", **({"new": True} if diff else {})})
for g in cfg.get("full" if full else "diff" if diff else "hist", []):
    rows.append({"file": g.get("file", ""), "line": 0, "rule": "not-checked", "message": g["m"], "text": "not-checked: " + g["m"], "tool": g["tool"]})
print(json.dumps(rows))
'''


def env(cfg=None):
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    atexit.register(shutil.rmtree, t, True)
    os.makedirs(t + "/bin"); os.makedirs(t + "/acme")
    open(t + "/fake.py", "w").write(FAKE)
    open(t + "/checks.sh", "w").write(f'exec {sys.executable} {t}/fake.py "$@"\n')
    repo, state = t + "/acme", t + "/s.json"
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c],
                                  check=True, capture_output=True, text=True).stdout.strip()
    g("init", "-q")

    def commit(files):
        for n, body in files.items():
            os.makedirs(os.path.dirname(os.path.join(repo, n)), exist_ok=True)
            open(os.path.join(repo, n), "w").write(body)
        g("add", "-A"); g("commit", "-qm", "c")
        return g("rev-parse", "HEAD")

    e = types.SimpleNamespace(t=t, commit=commit, env={"PATH": t + "/bin:/usr/bin:/bin", "HOME": t, "TMPDIR": t, "AUDIT_SWEEP_CHECKS": t + "/checks.sh"})
    e.cfg = lambda c: json.dump(c, open(t + "/cfg.json", "w"))
    e.cfg(cfg or {})
    e.sweep = lambda: subprocess.run([sys.executable, D + "/audit_sweep.py", "--local", repo, "--state", state], capture_output=True, text=True, env=e.env).stdout
    e.st = lambda: list(json.load(open(state)).values())[0]
    e.calls = lambda: open(t + "/calls.log").read().splitlines() if os.path.exists(t + "/calls.log") else []
    e.bin = lambda n, body="": (open(t + "/bin/" + n, "w").write(body), os.chmod(t + "/bin/" + n, 0o755))
    return e


def rows(out):
    return [tuple(l.split("\t")[1:5]) for l in out.splitlines()[1:] if "\tCOVERAGE\t" not in l and "\tENVGAP\t" not in l]


def test_full_scan_design_rows_do_not_block():
    assert f'not-checked "{NOISE}"' in HUB_SRC and f'skip guarddog "{GUARDDOG}"' in HUB_SRC, "row text drifted from the hub"
    assert "files hold JSX or markup that node --check cannot parse (first 3: $first); a JSX-aware linter or the project build judges them" in HUB_SRC
    assert a.env_gap(gap("node-check", JSX, "a.js")) and not a.env_gap(gap("node-check", JSX)) and not a.env_gap(gap("cosign", JSX, "a.js"))
    assert not a.env_gap(gap("node-check", JSX + " exit 1", "a.js"))
    for g, envgap in (({"tool": "guarddog", "m": GUARDDOG}, ""), ({"tool": "node-check", "file": "a.js", "m": JSX}, "node-check"), (None, "")):
        e = env({"full": [g] if g else []})
        h = e.commit({"f.py": "ok\n", "fixtures/a.py": "x\n"})  # every run: one noise row (the fake's nskip)
        out = e.sweep()
        assert e.st().get("sha") == h and "\tCOVERAGE\t\t" in out, f"{g}: a by-design --full row must not hold the sha: {e.st()} {out}"
        assert not envgap or re.search(rf"\tENVGAP\t[^\t]*\t[^\t]*\t{envgap}\t", out), out
        h = e.commit({"g.py": "BAD\n"})
        got, calls = rows(e.sweep()), e.calls()
        assert got == [("delta", "g.py", "r", "fake")] and e.st()["sha"] == h and "--full" not in calls[-1], f"{g}: next run is a delta: {got} {calls}"


def test_rescan_reports_noise_path_finding_from_its_diff_scan():
    e = env()
    e.commit({"f.py": "ok\n"}); e.sweep()
    h = e.commit({"fixtures/x.py": "BAD\n"})
    open(e.t + "/checks.sh", "a").write("# rule upgrade\n")  # stamp change: --full (never reads fixtures/) plus a diff scan (reads it)
    got = rows(e.sweep())
    assert got == [("rescan", "fixtures/x.py", "r", "fake")] and e.st()["sha"] == h, f"only the diff scan sees the noise path: {got} {e.st()}"


def test_config_changed_rows_are_envgap_then_one_full_rescan():
    for tool, m in CONFIG.items():
        assert m in HUB_SRC, f"text drifted from the hub: {tool}"
        assert a.env_gap(gap(tool, m)) and not a.env_gap(gap(tool, m, "a.yml")) and not a.env_gap(gap("cosign", m)), tool
        e = env({"diff": [{"tool": tool, "m": m}]})
        e.commit({"f.py": "ok\n"}); e.sweep()
        h = e.commit({"g.py": "ok\n"})
        out = e.sweep()
        assert e.st()["sha"] == h and re.search(rf"\tENVGAP\t[^\t]*\t[^\t]*\t{tool}\t", out), f"{tool}: listed, not blocking: {e.st()} {out}"
        n = len(e.calls()); e.sweep()
        assert e.calls()[n:] == [f"--timeout {a.FULL_TIMEOUT} --full"], f"{tool} never read that range: the next run must rescan --full: {e.calls()[n:]}"
        n = len(e.calls()); e.sweep()
        assert len(e.calls()) == n, f"{tool}: one rescan, then idle"


def test_codeql_license_gate_is_scrubbed_and_envgap():
    assert "REVIEW_CODEQL" in a.SCRUB, "an operator REVIEW_CODEQL=1 must never reach a sweep of private repos"
    assert f'not-checked "{CODEQL}"' in HUB_SRC, "text drifted from the hub"
    assert a.env_gap(gap("codeql", CODEQL)) and not a.env_gap(gap("codeql", CODEQL, "a.py")) and not a.env_gap(gap("cosign", CODEQL))
    assert not a.env_gap(gap("codeql", "install: brew install codeql")), "a missing codeql is a missing tool, not a license gap"


def test_missing_ruby_advisory_db_is_a_missing_tool():
    assert f'not-checked "{RUBY_DB}"' in HUB_SRC, "text drifted from the hub"
    assert a.not_installed(gap("bundler-audit", RUBY_DB)) and not a.not_installed(gap("bundler-audit", RUBY_DB, "Gemfile.lock"))
    assert not a.not_installed(gap("brakeman", RUBY_DB)) and not a.not_installed(gap("bundler-audit", RUBY_DB + " exit 1"))
    e = env({"full": [{"tool": "bundler-audit", "m": RUBY_DB}]})
    e.bin("bundle-audit")  # the binary alone does not close the gap
    h = e.commit({"Gemfile.lock": "x\n"}); e.sweep()
    assert e.st().get("sha") == h and e.st()["missing"] == ["bundler-audit"], f"no DB is a provisioning gap, not a blocker: {e.st()}"
    n = len(e.calls()); e.sweep()
    assert len(e.calls()) == n, "still no DB: no rescan"
    os.makedirs(e.t + "/db"); open(e.t + "/db/gems", "w").close()
    e.env["BUNDLER_AUDIT_DB"] = e.t + "/db"; e.cfg({})
    n = len(e.calls()); e.sweep()
    assert e.calls()[n:] == [f"--timeout {a.FULL_TIMEOUT} --full"] and e.st()["missing"] == [], f"a provisioned DB rescans the old range once: {e.calls()[n:]} {e.st()}"


def test_real_hub_full_scan_then_incremental():
    e = env()
    hub = os.path.join(D, "review_checks.sh")
    open(e.t + "/checks.sh", "w").write(f'shift 2; echo "$*" >>{e.t}/calls.log; exec bash {hub} --repo {e.t}/acme "$@"\n')
    e.bin("node", "#!/bin/sh\necho \"SyntaxError: Unexpected token '<'\" >&2\nexit 1\n")  # node --check fails on JSX: the hub's JSX row
    h = e.commit({"fixtures/a.py": "x = 1\n", "package-lock.json": '{"lockfileVersion": 3, "packages": {}}\n', "app.js": "const a = <div/>;\n"})
    out = e.sweep()
    assert e.calls() == [f"--timeout {a.FULL_TIMEOUT} --full"] and e.st().get("sha") == h, f"run 1 (--full: guarddog, noise and JSX rows) must store the sha: {e.st()} {out}"
    assert re.search(r"\tENVGAP\t[^\t]*\t[^\t]*\tnode-check\t", out), f"the JSX row is an ENVGAP row: {out}"
    h = e.commit({"b.txt": "b\n"})
    e.sweep()
    assert e.calls()[1:] and not any("--full" in c for c in e.calls()[1:]) and e.st()["sha"] == h, f"run 2 is a delta: {e.calls()} {e.st()}"


T = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
bad = 0
for f in T:
    try:
        f(); print("ok", f.__name__)
    except Exception as ex:  # an AssertionError or a crash fails this test only
        bad += 1; print("FAIL", f.__name__, ex)
print(f"Tests: {len(T) - bad}/{len(T)}")
sys.exit(bad)
