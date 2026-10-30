#!/usr/bin/env python3
"""heavy_gate.DEFAULT_PATTERNS also hold whole-repo security scanners, dependency installs and Perun's scan/CI entrypoints
(review_checks.sh, run-ci-tests.sh, app_pentest.sh), while --version/--help/--list-affected, the cheap linters and the single-file
bandit/ruff runs stay light, as do presence checks (`command -v grype`, `command -v pytest`), db-only and lockfile-only runs (but not
`npm ci --package-lock-only`), bare scanner names and grype's db/version/help subcommands. A bare grype fed by a pipe or `<` reads an SBOM
from stdin and is heavy; a scan target named like a subcommand (`db:latest`, `help.json`) is a target; `uv tool run`, `yarn dlx`, `bun x`
and `npm exec` unwrap like npx; a backslash-newline continuation joins before classifying, except on a `#` comment line. The is_heavy
tables only classify text; the hook tests feed heavy_gate.py a busy and an idle machine through its $PERUN_GATE_* injection and a private
lease dir. Offline; nothing named here is ever executed."""
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
SC = Path(__file__).resolve().parents[1] / ".claude/skills/agentic-delivery/scripts"
sys.path.insert(0, str(SC))
import heavy_gate as hg  # noqa: E402

FULL_MAP = SC.parent / "references/full-map.md"
FIXTURE = Path(__file__).resolve().parent / "eval-fixtures/slim-delivery-hard-rules.txt"

HEAVY = [
    # semgrep: scan, ci or --config, also behind a global flag or a runner wrapper
    "semgrep scan", "semgrep scan --config auto .", "semgrep ci", "semgrep --config p/default src/", "semgrep --config=auto .",
    "semgrep --metrics=off scan .", "uv run semgrep scan", "pipx run semgrep ci",
    # trivy: fs|repo|image|config|rootfs, a global flag with a separate value may come first
    "trivy fs .", "trivy repo https://example.com/acme/app.git", "trivy image acme/app:1.0", "trivy config .", "trivy rootfs /",
    "trivy fs --scanners vuln,secret .", "trivy --cache-dir /tmp/c image acme/app:1.0", "/usr/local/bin/trivy fs .",
    # osv-scanner, grype, checkov: any run
    "osv-scanner -r .", "osv-scanner --format json -r .", "osv-scanner scan source -r .", "grype dir:.", "grype sbom:bom.json -o json",
    "checkov -d .", "checkov -f main.tf -o json --quiet",
    # secret scanners
    "gitleaks detect --source . --no-banner", "gitleaks git .", "gitleaks dir .", "trufflehog git file://. --only-verified",
    "trufflehog --no-update filesystem .", "trufflehog github --org=acme",
    # installs
    "npm ci", "npm install", "npm i", "npm ci --ignore-scripts", "pnpm install --frozen-lockfile", "pnpm i", "yarn install", "bun install", "bun i",
    "npm install left-pad",
    # position and wrappers: after a chain, in a pipe, behind env/time/nice/timeout, inside bash -c
    "cd app && npm ci", "echo x; trivy fs .", "trivy fs . | tee out.txt", "time semgrep scan", "nice -n 5 trivy fs .", "timeout 600 gitleaks detect",
    "CI=1 npm ci", "env FOO=1 osv-scanner -r .", "bash -c 'trivy fs .'", 'sh -c "cd app && npm ci"',
    # Perun entrypoints: bash/sh PATH or direct, with flags, a $VAR path, a wrapper or a chain
    "bash scripts/run-ci-tests.sh", "bash scripts/run-ci-tests.sh --affected origin/main", "sh scripts/run-ci-tests.sh",
    "./scripts/run-ci-tests.sh --affected", "scripts/run-ci-tests.sh",
    "bash .claude/skills/deep-code-review/scripts/review_checks.sh --base origin/main --history",
    ".claude/skills/deep-code-review/scripts/review_checks.sh --full", 'bash "$DIR/review_checks.sh" --tests',  # unquoted $DIR splits at the `$`: not matched
    "bash .claude/skills/deep-code-review/scripts/app_pentest.sh http://localhost:3000",
    "PERUN_X=1 bash scripts/run-ci-tests.sh", "time bash scripts/run-ci-tests.sh --affected", "cd /w && bash scripts/run-ci-tests.sh 2>&1 | tail -5",
]
LIGHT = [
    # --version/--help/-h never start a scan or an install
    "semgrep --version", "semgrep scan --help", "trivy --version", "trivy image --help", "osv-scanner --version", "osv-scanner -h",
    "grype --help", "checkov --version", "gitleaks detect --help", "trufflehog --help", "npm ci --help", "yarn --version",
    "bash scripts/run-ci-tests.sh --help", "bash .claude/skills/deep-code-review/scripts/review_checks.sh --help",
    # the dry form of run-ci-tests.sh only lists the suites it would run
    "bash scripts/run-ci-tests.sh --list-affected", "bash scripts/run-ci-tests.sh --list-affected origin/main",
    # cheap linters and single-file runs
    "zizmor .github/workflows", "actionlint", "actionlint .github/workflows/ci.yml", "shellcheck scripts/run-ci-tests.sh",
    "hadolint Dockerfile", "bandit app.py", "bandit -q src/one.py", "ruff check app.py", "ruff format --check app.py",
    # subcommands that do not scan or install
    "semgrep login", "trivy version", "trivy plugin list", "gitleaks version", "npm run lint", "npm ls", "npm init", "npm info left-pad",
    "npm view left-pad version",
    # a mention, a read or a syntax check is not a run
    "echo trivy fs .", 'git commit -m "npm ci && semgrep scan"', "grep -rn 'trivy fs' docs", "cat scripts/run-ci-tests.sh",
    "bash -n scripts/run-ci-tests.sh", "git add scripts/run-ci-tests.sh", "bash scripts/not-run-ci-tests.sh", "git diff review_checks.sh",
    "git commit -F - <<'EOF'\nfix\n\nnpm ci\ntrivy fs .\nEOF",
]
# `command -v TOOL` is a presence check: nothing runs, however it is chained or wrapped
PRESENCE = ["command -v grype", "command -V checkov", "command -v osv-scanner >/dev/null && echo ok", "x=$(command -v grype)", "nice command -v grype",
            # runners need no argument to count, so only strip_wrappers' `command -v` early return keeps these light (a scanner above is light anyway)
            "command -v pytest", "command -V pytest", "command -v jest", "command -v vitest", "command -v playwright", "command -v pytest >/dev/null && echo ok"]
# db-only fetches and lockfile-only installs run no scan and unpack nothing
DB_ONLY = ["trivy image --download-db-only", "trivy --cache-dir /tmp/c image --download-db-only", "trivy image --download-java-db-only",
           "npm install left-pad --package-lock-only", "npm i --package-lock-only"]
# a scanner counts only with a scan target; grype's db/version/help are subcommands (osv-scanner takes directories, so `db` can be one)
NO_TARGET = ["grype", "checkov", "osv-scanner", "grype db update", "grype db status", "grype version", "grype help"]
TARGET = ["grype dbx", "grype -o json dir:.", "osv-scanner db", "command grype dir:.", "checkov -d ."]
# launchers unwrapped like npx and uv run
LAUNCHED = ["uvx semgrep scan", "uvx --from semgrep semgrep scan", "bunx vitest", "pnpm dlx vitest run", "uvx pytest -q", "bunx trivy fs ."]
UNWRAPPED = ["uv tool run semgrep scan", "uv tool run --from semgrep semgrep scan", "uv tool run pytest -q", "yarn dlx vitest run", "yarn dlx -p vitest vitest run",
             "bun x vitest", "bun x trivy fs .", "npm exec vitest", "npm exec -- vitest run", "npm exec -p pkg -- jest", "npm exec --yes -- playwright test",
             "FOO=1 uv tool run semgrep ci"]
# a backslash-newline joins the lines before the command is read, so a continued scan or install is still one command
CONTINUED = ["semgrep \\\n  scan", "semgrep scan \\\n  --config auto .", "semgrep\\\n scan", "npm \\\n ci", "trivy \\\n  fs .", "cd app && \\\n  npm ci",
             "uv run \\\n  pytest", "echo hi; \\\n npm ci",
             "echo a\\\\\nnpm ci",  # an even run of backslashes ends the line, npm ci is its own command
             # a `#` comment ends at its newline, a trailing backslash included, so the next line is its own command
             "# note \\\npytest -q", "  # note \\\npytest -q", "echo a\n# note \\\npytest -q",
             "cat <<EOF\nx \\\nEOF\nnpm ci"]  # a heredoc body line ending in a backslash is dropped with the body, so npm ci is its own command
CONTINUED_LIGHT = ["echo semgrep \\\n  scan", "echo hi \\\n && npm ls", "ls \\\n -la", "git commit -m x \\\n  -m 'npm ci'"]
# a scan target that merely starts with a subcommand name (`db:latest`, `help.json`) is a target, not the subcommand
GRYPE_NAMED_TARGETS = ["grype db:latest", "grype db.tar", "grype help.json", "grype version:latest"]
# a bare grype reads an SBOM from stdin when a pipe or `<` feeds it, so it scans; with no stdin source, or with a subcommand, it stays light
GRYPE_STDIN = ["syft acme/app:1.0 -o json | grype", "cat sbom.json | grype", "syft . -o json | tee sbom.json | grype", "grype < sbom.json", "grype <sbom.json",
               'grype <<< "$SBOM"', "grype <<EOF\n{}\nEOF", "syft . -o json | nice grype", "syft . -o json |& grype", "syft . -o json |\n  grype",
               "cd app && syft . -o json | /usr/local/bin/grype | jq .", "bash -c 'syft . -o json | grype'",
               "(cat sbom.json)|grype", "syft . -o json | \n  grype", "syft . -o json |& \n  grype"]  # a subshell before the pipe; a space before the newline after it
GRYPE_NO_STDIN = ["grype", "grype | tee out.txt", "grype > out.txt", "echo ok; grype", "true && grype", "false || grype", "grype db update < /dev/null",
                  "cat sbom.json | grype db update", "(true)||grype", "cat sbom.json\ngrype", "cat sbom.json || \n grype"]
HOOK_HEAVY = ["semgrep scan --config auto .", "trivy fs .", "npm ci", "gitleaks detect --source .", "bash scripts/run-ci-tests.sh --affected",
              "npm ci --package-lock-only", "syft . -o json | grype"]
HOOK_LIGHT = ["zizmor .github/workflows", "semgrep --version", "bash scripts/run-ci-tests.sh --list-affected", "ruff check app.py",
              "command -v grype", "command -v pytest", "trivy image --download-db-only", "npm install left-pad --package-lock-only", "grype db update", "grype"]


def hook(cmd, load1, d):
    """Run heavy_gate.py as the PreToolUse hook on `cmd` with an injected load; returns its stdout (empty = allowed)."""
    env = {k: v for k, v in os.environ.items() if k != "PERUN_HEAVY_PATTERNS"}
    env.update(PERUN_HEAVY_DIR=str(Path(d) / "heavy"), PERUN_POLICY=str(Path(d) / "none.json"), PERUN_GATE_LOAD1=str(load1),
               PERUN_GATE_CORES="8", PERUN_GATE_FREE_RAM_PCT="60", PERUN_HEAVY_HOOK_WAIT_SECS="0")
    return subprocess.run([sys.executable, str(SC / "heavy_gate.py")], input=json.dumps({"tool_input": {"command": cmd}, "cwd": "/w"}),
                          env=env, capture_output=True, text=True, timeout=30).stdout


class ScannerPatterns(unittest.TestCase):
    def test_scanners_installs_and_entrypoints_are_heavy(self):
        for c in HEAVY:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_light_forms_stay_light(self):
        for c in LIGHT:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_presence_checks_are_light(self):
        for c in PRESENCE:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_db_only_and_lockfile_only_runs_are_light(self):
        for c in DB_ONLY:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_scanner_needs_a_scan_target(self):
        for c in NO_TARGET:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in TARGET:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_uvx_bunx_and_pnpm_dlx_are_unwrapped(self):
        for c in LAUNCHED:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in ("uvx ruff check app.py", "uvx pytest a.py", "pnpm dlx create-app"):
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_grype_target_named_like_a_subcommand_is_a_target(self):
        for c in GRYPE_NAMED_TARGETS:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_bare_grype_is_heavy_only_when_stdin_feeds_it(self):
        for c in GRYPE_STDIN:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in GRYPE_NO_STDIN:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        # the patterns still decide: a custom set that does not name grype holds nothing here
        self.assertFalse(hg.is_heavy("cat sbom.json | grype", [r"pytest\b"]))
        self.assertTrue(hg.is_heavy("cat sbom.json | grype", [r"grype \S"]))

    def test_npm_ci_stays_heavy_with_package_lock_only(self):
        # npm ci wipes node_modules and reinstalls, so the lockfile-only flag does not make it light; npm install with it does
        for c in ("npm ci --package-lock-only", "cd app && npm ci --package-lock-only", "CI=1 npm ci --ignore-scripts --package-lock-only"):
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in ("npm install --package-lock-only", "npm install --package-lock-only --ignore-scripts", "npm ci --package-lock-only --help"):
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)

    def test_uv_tool_run_yarn_dlx_bun_x_and_npm_exec_are_unwrapped(self):
        for c in UNWRAPPED:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in ("uv tool run ruff check app.py", "yarn dlx create-app", "bun x create-app", "npm exec -- create-app", "uv tool install semgrep",
                  "uv tool list", "npm exec", "bun x"):
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        self.assertEqual(hg.strip_wrappers(["uv", "tool", "run", "--from", "semgrep", "semgrep", "scan"]), ["semgrep", "scan"])
        self.assertEqual(hg.strip_wrappers(["npm", "exec", "--", "vitest"]), ["vitest"])
        self.assertEqual(hg.strip_wrappers(["uv", "tool", "install", "semgrep"]), ["uv", "tool", "install", "semgrep"])

    def test_backslash_newline_continuation_is_joined_before_classifying(self):
        for c in CONTINUED:
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        for c in CONTINUED_LIGHT:
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)
        # ceo_altitude_guard reads the same tokens and segments, so it sees the joined line too
        self.assertEqual(hg.segments("sed -i \\\n  a.py"), [["sed", "-i", "a.py"]])
        self.assertEqual(hg.tokens("echo x >\\\n out.py"), ["echo", "x", ">", "out.py"])
        # a comment line ending in a backslash joins nothing: the guard sees the next line as its own command
        self.assertEqual(hg.tokens("# note \\\npytest -q"), ["pytest", "-q"])
        self.assertEqual(hg.segments("echo a\n# note \\\npytest -q"), [["echo", "a"], ["pytest", "-q"]])

    def test_existing_runners_still_heavy(self):
        for c in ("pytest -q", "npm test", "npm run build", "cargo test", "go test ./...", "next build", "tsc -b"):
            self.assertTrue(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)


class ScannerHook(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        (Path(self.tmp.name) / "heavy").mkdir()
        (Path(self.tmp.name) / "none.json").write_text("{}")

    def test_busy_machine_denies_scanner_runs(self):
        for c in HOOK_HEAVY:
            out = json.loads(hook(c, 99, self.tmp.name))["hookSpecificOutput"]
            self.assertEqual(out["permissionDecision"], "deny", c)
            self.assertIn("machine busy", out["permissionDecisionReason"], c)

    def test_idle_machine_allows_them(self):
        for c in HOOK_HEAVY:
            self.assertEqual(hook(c, 0, self.tmp.name), "", c)

    def test_light_forms_pass_even_when_busy(self):
        for c in HOOK_LIGHT:
            self.assertEqual(hook(c, 99, self.tmp.name), "", c)

    def test_deny_text_fits_scans_and_installs(self):
        for c in ("npm ci", "trivy fs ."):
            reason = json.loads(hook(c, 99, self.tmp.name))["hookSpecificOutput"]["permissionDecisionReason"]
            self.assertNotIn("narrower test", reason, c)
            self.assertIn("narrow the command (one test file, a -k filter, a smaller scan path)", reason, c)


class InstallClaim(unittest.TestCase):
    def test_docs_and_fixture_say_js_installs(self):
        for f in (FULL_MAP, FIXTURE):
            line = next(ln for ln in f.read_text().splitlines() if "denies tests" in ln)
            self.assertIn("denies tests/builds/scans/JS installs while", line, f.name)

    def test_non_js_installs_are_not_held(self):
        for c in ("pip install requests", "cargo install ripgrep", "go install example.com/x@latest"):
            self.assertFalse(hg.is_heavy(c, hg.DEFAULT_PATTERNS), c)


if __name__ == "__main__":
    unittest.main()
