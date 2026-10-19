#!/usr/bin/env python3
"""sandbox_probe.py: first-run check that an agent can work autonomously inside the sandbox.

Usage: python3 sandbox_probe.py [REPO] [--verdict-only]

Runs nine harmless checks (git status in REPO, `import ssl`, an HTTPS HEAD to github.com,
binding 127.0.0.1:0, writing a temp file under ~/.cache, plus runtime probes for gh, a headless
Chromium launch, a Postgres client connect and tsx) and prints one line per check;
each failure gets a plain-English cause and the exact fix (a settings key or a
`/sandbox exclude` entry; the tool probes name the matching sandbox_preflight.py RISKS rule).
A tool probe prints SKIP, not FAIL, when the tool is absent or the result is not a sandbox block
(nothing is installed; tsx comes only from PATH or REPO/node_modules/.bin).
The last line is the verdict. Nothing is deleted or killed: the ~/.cache file is a
self-removing tempfile, the socket is closed at once.
Run it from a Claude Code Bash call to test the sandbox itself; from a plain terminal it
only tests that shell. Exit 0 = no failure (SKIPs allowed), 1 = at least one failure.
"""
import os, re, shutil, socket, subprocess, sys, tempfile
from pathlib import Path


class Skip(Exception):
    """Raised by a probe that cannot judge the sandbox (tool absent, or a failure that is not a block)."""


def _run(cmd, cwd=None):
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=15, check=False)
    if r.returncode:
        raise RuntimeError(f"exit {r.returncode}")


def _tool(cmd, block=None, env=None):
    """Run a tool probe. Absent tool -> Skip. Exit 0 -> pass. Non-zero: with `block` (regex on stderr) only a
    match fails and anything else is Skip (not logged in, no server: not a sandbox block); without it, any
    non-zero exit or timeout fails. Timeouts raise TimeoutExpired, which probe() reports as FAIL."""
    if not cmd[0] or not (shutil.which(cmd[0]) or os.path.isfile(cmd[0])):
        raise Skip("not installed")
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=20, check=False, env={**os.environ, **(env or {})})
    if not r.returncode:
        return
    if block and not re.search(block, r.stderr, re.I):
        raise Skip("failed for a reason that is not a sandbox block")
    raise RuntimeError(f"exit {r.returncode}")


def _chromium():
    names = ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable", "chrome")
    mac = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    exe = next((n for n in names if shutil.which(n)), mac if os.path.isfile(mac) else None)
    _tool([exe, "--headless", "--disable-gpu", "--dump-dom", "about:blank"])


def _tsx(repo):
    local = Path(repo) / "node_modules" / ".bin" / "tsx"
    exe = shutil.which("tsx") or (str(local) if local.is_file() else None)
    _tool([exe, "-e", "process.exit(0)"])


def _bind():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))


def _cache_write():
    d = Path.home() / ".cache"
    d.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=d, prefix="perun-probe-"):
        pass


def checks(repo):
    """(name, callable that raises on failure, plain-English cause, exact fix) for each probe."""
    return [
        ("git", lambda: _run(["git", "--no-optional-locks", "status", "--porcelain"], cwd=repo), "git cannot run in this repo",
         "run the failing git command yourself with the ! prefix (protected paths such as .claude/skills stay write-denied)"),
        ("python-ssl", lambda: _run([sys.executable, "-c", "import ssl"]), "python3 has no working ssl module",
         "reinstall python3 with OpenSSL support (not a sandbox setting)"),
        ("network", lambda: _run(["curl", "-sI", "-m", "10", "-o", os.devnull, "https://github.com"]),
         "HTTPS to github.com is blocked", 'add "github.com" to sandbox.network.allowedDomains'),
        ("local-bind", _bind, "dev servers cannot listen on localhost", "set sandbox.network.allowLocalBinding: true"),
        ("cache-write", _cache_write, "package managers cannot write their cache in ~/.cache",
         'add "~/.cache" to sandbox.filesystem.allowWrite'),
        ("gh", lambda: _tool(["gh", "api", "rate_limit"], block=r"x509|certificate|tls"),
         "gh (a Go CLI) fails TLS verification under macOS Seatbelt",
         'add "gh *" to sandbox.excludedCommands (sandbox_preflight.py rule: gh)'),
        ("chromium", _chromium, "headless Chromium cannot launch (it needs macOS XPC/Mach services)",
         'add the browser command you run (for example "playwright *") to sandbox.excludedCommands (sandbox_preflight.py rule: browser)'),
        ("postgres", lambda: _tool(["psql", "-h", "127.0.0.1", "-w", "-c", "select 1"], block=r"not permitted|permission denied",
                                    env={"PGCONNECT_TIMEOUT": "5"}),
         "the Postgres client cannot open its own TCP connection",
         'add the database command you run (for example "psql *") to sandbox.excludedCommands (sandbox_preflight.py rule: db)'),
        ("tsx", lambda: _tsx(repo), "tsx cannot open its Unix-socket IPC pipe",
         'add the tsx command you run (for example "tsx *") to sandbox.excludedCommands (sandbox_preflight.py rule: tsx)'),
    ]


def probe(items):
    """Run each check; return (lines, failures). A check fails on any exception (timeouts included) except Skip,
    which prints a SKIP line and counts as neither pass nor failure."""
    lines, bad, skipped = [], 0, 0
    for name, fn, cause, fix in items:
        try:
            fn()
            lines.append(f"OK    {name}")
        except Skip as e:
            skipped += 1
            lines.append(f"SKIP  {name}: {e}")
        except Exception:  # noqa: BLE001 - any failure is reported, never raised
            bad += 1
            lines.append(f"FAIL  {name}: {cause}. Fix: {fix}")
    n = len(items)
    note = f", {skipped} skipped" if skipped else ""
    lines.append(f"sandbox probe: {n - skipped}/{n - skipped} checks passed{note} in this shell (run it from an agent session to test the agent sandbox)" if not bad
                 else f"sandbox probe: {bad} of {n} checks failed; run python3 {Path(__file__).resolve()} for the fixes")
    return lines, bad


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    repo = next((a for a in argv if not a.startswith("-")), ".")
    lines, bad = probe(checks(repo))
    print("\n".join(lines[-1:] if "--verdict-only" in argv else lines))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
