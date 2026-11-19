#!/usr/bin/env python3
"""Tests: every install hint in the hub table counts as "not installed"; unverified-flag and config-in-this-diff rows are ENVGAP rows,
not blockers; a rescan still reports a fixed-then-re-added finding; a held sha does not re-report the same added line on every run; a
delta that skips a missing tool's files keeps the tool listed; installing a tool that emits no row when missing forces one rescan;
dep-scan tracks the missing auditor binary; a summary row with a newly added member line is reported again; summary paths with spaces
stay stable; no non-printable character in a file name can split a TSV row."""
import atexit, json, os, re, shutil, subprocess, sys, tempfile, types

D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts")
sys.path.insert(0, D)
import audit_sweep as a  # noqa: E402

FAKE = r'''import json, os, re, subprocess, sys
av = sys.argv
repo = av[av.index("--repo") + 1]
t = os.path.dirname(repo)
open(t + "/calls.log", "a").write(" ".join(av[1:]) + "\n")
cfg = json.load(open(t + "/cfg.json")) if os.path.exists(t + "/cfg.json") else {}
base = av[av.index("--base") + 1] if "--base" in av else None
diff = base and "--history" not in av
git = lambda *c: subprocess.run(["git", "-C", repo, *c], capture_output=True, text=True).stdout
added, cur = {}, None
if base:
    for l in git("diff", "-U0", base + "...HEAD").splitlines():
        if l.startswith("+++ b/"):
            cur = l[6:]; added[cur] = set()
        m = re.match(r"@@ -\S+ \+(\d+)(?:,(\d+))? @@", l)
        if m and cur:
            added[cur] |= set(range(int(m[1]), int(m[1]) + (1 if m[2] is None else int(m[2]))))
files = sorted(git("diff", "--name-only", base + "...HEAD").split()) if base else sorted(f for f in os.listdir(repo) if f != ".git")
new = lambda f, ls: {"new": any(i in added.get(f, ()) for i in ls)} if diff else {}
rows = []
for f in files:
    lines = open(os.path.join(repo, f)).read().splitlines()
    for i, l in enumerate(lines, 1):
        if "BAD" in l:
            rows.append({"file": f, "line": i, "rule": "r", "text": "BAD thing", "tool": "fake", **new(f, [i])})
        if "LATE" in l and os.path.exists(t + "/bin/latetool"):
            rows.append({"file": f, "line": i, "rule": "r", "text": "LATE thing", "tool": "latetool"})
    hits = [i for i, l in enumerate(lines, 1) if "HIT" in l]
    if len(hits) > 3:  # the hub's per-file summary row: first 3 lines shown, new when any member line was added
        m = f"{len(hits)} F821 hits in this file (showing 3 of {len(hits)}; REVIEW_FIXTURE_ROWS=all for every row): {', '.join(map(str, hits[:3]))}"
        rows.append({"file": f, "line": hits[0], "rule": "F821-summary", "tool": "ruff", "text": "ruff: " + m, **new(f, hits)})
if not os.path.exists(t + "/bin/latetool") and any(f.endswith(".late") for f in files):  # like the hub: only when a routed file is in range
    rows.append({"file": "", "line": 0, "rule": "not-checked", "message": "install: brew install latetool", "text": "not-checked: install: brew install latetool", "tool": "latetool"})
for g in cfg.get("gaps", []):
    rows.append({"file": g.get("file", ""), "line": 0, "rule": "not-checked", "message": g["m"], "text": "not-checked: " + g["m"], "tool": g["tool"]})
print(json.dumps(rows + cfg.get("rows", [])))
'''


def env(cfg=None):
    t = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    atexit.register(shutil.rmtree, t, True)
    open(t + "/fake.py", "w").write(FAKE)
    open(t + "/checks.sh", "w").write(f'exec {sys.executable} {t}/fake.py "$@"\n')
    os.makedirs(t + "/bin"); os.makedirs(t + "/acme")
    e = types.SimpleNamespace(t=t, path=t + "/bin" + os.pathsep + "/usr/bin:/bin")  # never the host PATH
    e.cfg = lambda c: json.dump(c, open(t + "/cfg.json", "w"))
    if cfg:
        e.cfg(cfg)
    repo, state = t + "/acme", t + "/s.json"
    g = lambda *c: subprocess.run(["git", "-C", repo, "-c", "user.email=jane@example.com", "-c", "user.name=Jane Smith", *c], check=True, capture_output=True)
    g("init", "-q")

    def commit(files):
        for n, body in files.items():
            open(os.path.join(repo, n), "w").write(body)
        g("add", "-A"); g("commit", "-qm", "c")

    def raw():
        return subprocess.run([sys.executable, D + "/audit_sweep.py", "--local", repo, "--state", state], capture_output=True, text=True,
                              env=dict(os.environ, AUDIT_SWEEP_CHECKS=t + "/checks.sh", PATH=e.path, HOME=t))

    def inst(n="latetool"):
        open(t + "/bin/" + n, "w").write(""); os.chmod(t + "/bin/" + n, 0o755)

    e.commit, e.raw, e.inst = commit, raw, inst
    e.run = lambda: [tuple(l.split("\t")[1:5]) for l in raw().stdout.splitlines()[1:] if "\tCOVERAGE\t" not in l and "\tENVGAP\t" not in l and "\tGAP\t" not in l]
    e.st = lambda: list(json.load(open(state)).values())[0]
    e.calls = lambda: open(t + "/calls.log").read().splitlines() if os.path.exists(t + "/calls.log") else []
    return e


HINTS = {"devskim": "dotnet tool install --global Microsoft.CST.DevSkim.CLI", "skillspector": "uv tool install git+https://github.com/NVIDIA/skillspector.git",
         "psalm": "composer global require vimeo/psalm", "sobelow": "mix escript.install hex sobelow"}
HUB_SRC = open(os.path.join(D, "review_checks.sh")).read()
gap = lambda tool, text, file="": {"rule": "not-checked", "tool": tool, "file": file, "text": "not-checked: " + text, "message": text}


def test_every_hub_install_hint_is_not_installed():
    for tool, hint in HINTS.items():
        assert f"'{tool};" in HUB_SRC and f";{hint}'" in HUB_SRC, f"hint drifted from the hub table: {tool}"
        assert a.not_installed(gap(tool, "install: " + hint)), tool
        assert not a.not_installed(gap(tool, "install: " + hint, "a.py")) and not a.not_installed(gap("cosign", "install: " + hint)), tool
    for tool, hint in re.findall(r"^  '([a-z0-9_-]+);verified;[^']*;([^';]+)'", HUB_SRC, re.M):
        assert a.not_installed(gap(tool, "install: " + hint)), f"hub row {tool} hint not recognized: {hint}"
    e = env({"gaps": [{"tool": "devskim", "m": "install: " + HINTS["devskim"]}]})
    e.commit({"f.py": "ok\n"}); e.run()
    assert e.st().get("sha") and e.st()["missing"] == ["devskim"], f"a missing devskim must not hold the sha: {e.st()}"


def test_permanent_gaps_are_envgap():
    for tool, text, file in (("snyk-agent-scan", "unverified flags: skipped by default", ""),
                             ("dep-scan", "no dependency scan ran for this lockfile (no osv-scanner/trivy result and no fallback for its ecosystem)", "go.mod"),
                             ("eslint-security", "eslint config or package.json changed in this diff: not run", ""),
                             ("rubocop", ".rubocop*.yml changed in this diff: its config can require code, not run", ""),
                             ("sobelow", "mix.exs or .sobelow-conf changed in this diff: its config is code, not run", "")):
        assert a.env_gap(gap(tool, text, file)), tool
        assert not a.env_gap(gap(tool, text + " exit 1", file)) and not a.env_gap(gap("faketool", text, file)), tool
        assert not a.env_gap(gap(tool, text, "a.txt" if file == "" else "")), tool
    e = env({"gaps": [{"tool": "snyk-agent-scan", "m": "unverified flags: skipped by default"}]})
    e.commit({"SKILL.md": "x\n"})
    out = e.raw().stdout
    assert e.st().get("sha") and "\tENVGAP\t\t\tsnyk-agent-scan\t" in out, f"unverified flags are listed, not blocking: {e.st()} {out}"


def test_rescan_reports_readded_finding():
    e = env(); e.inst()
    e.commit({"f.py": "BAD\n"})
    assert [r[0] for r in e.run()] == ["first"]
    e.commit({"f.py": "ok\n"})
    assert e.run() == []
    e.commit({"f.py": "ok\nBAD\n"})
    open(e.t + "/checks.sh", "a").write("# rule upgrade\n")  # tool stamp changes: mode rescan
    got = e.run()
    assert got == [("rescan", "f.py", "r", "fake")], f"a re-added finding must be reported in a rescan too: {got}"


def test_held_sha_reports_added_line_once():
    e = env(); e.inst()
    e.commit({"f.py": "ok\n"}); e.run()
    e.cfg({"gaps": [{"tool": "guarddog", "m": "unparseable output"}]})  # blocking: holds the sha, every run rediffs the same range
    e.commit({"f.py": "ok\nBAD\n"})
    assert e.run() == [("delta", "f.py", "r", "fake")]
    r3, r4 = e.run(), e.run()
    assert r3 == [] and r4 == [], f"the same added line must not re-alert while the sha is held: {r3} {r4}"
    e.cfg({}); e.run()
    assert e.st().get("held", []) == [], f"held list cleared once the sha advances: {e.st()}"


def test_delta_without_routed_file_keeps_missing_tool():
    e = env()
    e.commit({"a.late": "LATE\n"}); e.run()
    assert e.st()["missing"] == ["latetool"]
    e.commit({"b.txt": "x\n"}); e.run()
    assert e.st()["missing"] == ["latetool"], f"a delta with no *.late file must keep the tool listed: {e.st()}"
    e.inst(); e.commit({"c.txt": "y\n"})
    got = e.run()
    assert ("rescan", "a.late", "r", "latetool") in got, f"the install must rescan the old range: {got}"


def test_install_of_rowless_tool_forces_rescan():
    tools = subprocess.run(["bash", os.path.join(D, "review_checks.sh"), "--list-tools"], capture_output=True, text=True).stdout.split()
    e = env()
    pick = [x for x in ("shellcheck", "semgrep", "trivy", "osv-scanner") + tuple(tools) if x in tools and x not in a.BIN and not shutil.which(x, path=e.path)]
    assert pick, "every listed tool is on the isolated PATH: this test would check nothing"
    e.commit({"f.py": "ok\n"}); e.run()
    n = len(e.calls()); e.run()
    assert len(e.calls()) == n, "idle repo: no scan"
    e.inst(pick[0]); e.run()
    new = e.calls()[n:]
    assert new and new[-1].endswith("--full"), f"installing {pick[0]} (no row when missing) must force one rescan: {new}"
    n = len(e.calls()); e.run()
    assert len(e.calls()) == n, "one rescan, then idle again"
    old = os.environ["PATH"], os.environ.get("BUNDLER_AUDIT_DB")
    os.environ["PATH"], os.environ["BUNDLER_AUDIT_DB"] = e.path, e.t  # bundler-audit also needs a non-empty DB dir
    try:
        e.inst("ruff"); e.inst("bundle-audit")
        assert a.installed("ruff-security") and a.installed("bundler-audit"), "hub names map to their binaries"
    finally:
        os.environ["PATH"] = old[0]
        os.environ.pop("BUNDLER_AUDIT_DB") if old[1] is None else os.environ.update(BUNDLER_AUDIT_DB=old[1])


def test_dep_scan_tracks_auditor_binary():
    e = env()
    aud = [x for x in ("pip-audit", "pnpm", "npm") if not shutil.which(x, path=e.path)]
    assert aud, "every auditor is on the isolated PATH: this test would check nothing"
    e.cfg({"gaps": [{"tool": "dep-scan", "file": "requirements.txt", "m": f"no dependency scan ran: osv-scanner/trivy gave no result and {aud[0]} is not installed"}]})
    e.inst(); e.inst(next(x for x in ("npm", "pnpm", "pip-audit") if x != aud[0]))  # another auditor on PATH
    e.commit({"f.py": "ok\n"}); e.run()
    assert e.st()["missing"] == [aud[0]], e.st()
    for i in range(3):
        e.commit({f"g{i}.txt": "z\n"}); n = len(e.calls()); e.run()
        assert not any("--full" in c for c in e.calls()[n:]), f"another auditor on PATH must not force a rescan: run {i} {e.calls()[n:]}"


def test_summary_row_with_added_member_reports_again():
    e = env(); e.inst()
    e.commit({"s.py": "HIT\nHIT\nHIT\nHIT\n"})
    assert e.run() == [("first", "s.py", "F821-summary", "ruff")]
    e.commit({"s.py": "top\nHIT\nHIT\nHIT\nHIT\n"})
    assert e.run() == [], "a line shift alone is no new hit"
    e.commit({"s.py": "top\nHIT\nHIT\nHIT\nHIT\nHIT\n"})
    got = e.run()
    assert got == [("delta", "s.py", "F821-summary", "ruff")], f"a new member line must re-alert the summary: {got}"


def test_summary_paths_with_spaces_are_stable():
    f = lambda t: a.fingerprint("r", {"tool": "gitleaks", "rule": "likely-fixture-summary", "file": "my fixtures", "text": t})
    m = "gitleaks: {n} generic-api-key hits under my fixtures/ tagged likely-fixture (showing 3 of {n}; REVIEW_FIXTURE_ROWS=all for every row): {l} [likely-fixture]"
    assert f(m.format(n=5, l="my fixtures/a b.py:3, my fixtures/a+b.py:9, my fixtures/@c.py:30")) == f(m.format(n=6, l="my fixtures/a b.py:4, my fixtures/a+b.py:10, my fixtures/@c.py:31"))
    g = lambda t: a.fingerprint("r", {"tool": "ruff", "rule": "F821-summary", "file": "x.py", "text": t})
    s = "ruff: {n} F821 hits in this file (showing 3 of {n}; REVIEW_FIXTURE_ROWS=all for every row): {l}; names: {nm}"
    assert g(s.format(n=4, l="1, 2, 3", nm="foo")) == g(s.format(n=5, l="2, 3, 4", nm="foo")) != g(s.format(n=4, l="1, 2, 3", nm="bar"))


def test_nonprintable_file_name_keeps_one_row():
    name = "a\x0bb\x0cc\x1cd\x85e f\x1bg.py"
    e = env({"rows": [{"file": name, "line": 1, "rule": "r2", "text": "x", "tool": "fake"}]})
    e.inst(); e.commit({"f.py": "ok\n"})
    lines = [l for l in e.raw().stdout.splitlines()[1:] if "\tCOVERAGE\t" not in l]
    assert len(lines) == 1 and len(lines[0].split("\t")) == 6 and "\x1b" not in lines[0], lines


T = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
bad = 0
for f in T:
    try:
        f(); print("ok", f.__name__)
    except Exception as ex:  # an AssertionError or a crash fails this test only
        bad += 1; print("FAIL", f.__name__, ex)
print(f"Tests: {len(T) - bad}/{len(T)}")
sys.exit(bad)
