#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=defer a heavy local command while the machine is busy, review=2027-01-30
"""heavy_gate.py — PreToolUse(Bash) hook: defer a heavy local command while the machine is busy.

WHY: host_probe.py and the heavy-lease primitive in perun_policy.py existed but nothing called
them, so fleets ran 10+ test runners at once (load1 > 3x cores, swap climbing, OOM kills). This
hook runs on every Bash call, so the admission check happens without anyone remembering it.

What it does: if the command starts a test runner, a build, a whole-repo security scanner (semgrep scan|ci|--config, trivy
fs|repo|image|config|rootfs, osv-scanner, grype, checkov, gitleaks detect|git|dir, trufflehog git|filesystem|github), a JS dependency
install (npm|pnpm|yarn|bun ci|i|install) or a Perun scan/CI entrypoint (review_checks.sh, run-ci-tests.sh, app_pentest.sh, run as `bash PATH`
or directly) (DEFAULT_PATTERNS, or the newline-separated regexes in $PERUN_HEAVY_PATTERNS, each matched at the start of a shell segment,
after runner wrappers are stripped), it denies the call when host_probe.decide(lane_type="heavy") says HOLD (load1 > cores or low free
RAM; swap is not read, one sample shows no trend) or when the machine-wide heavy leases already fill the
slot count (perun_policy.heavy_slots; local_cpu=maximize raises it to every core). Otherwise it
prints nothing and the call proceeds. While a train gate holds the EXCLUSIVE lease (perun_policy.py heavy-exclusive) every heavy command is denied with "gate running: wait" and that deny is never bypassed or counted. It never takes a lease and never stops or deletes anything.
Light forms are never held: --version/--help, `command -v TOOL`, --download-db-only, --package-lock-only (not on `npm ci`, which wipes node_modules), a scanner with no
argument (a bare `grype` fed by a pipe or `<` reads an SBOM from stdin and is held), `grype db|version|help` (a target such as `db:latest` or `help.json` is not one).

Bypass: the hook keeps a small ledger (`heavy-denies.json`, next to the lease dir). After MAX_DENIES (3) denies of the same command (whitespace-normalized) in the same cwd within WINDOW (30 min) the 4th attempt is allowed with a WARN `additionalContext` (it matches the lane preamble's "retry at most 3 times, then proceed"); the ledger entry resets.

Fail open: any error inside the hook (bad stdin, unreadable host data, an unparsable command line, a bad policy) allows the call.
A block is a JSON `permissionDecision: "deny"` on stdout with exit 0, never exit 2, so a crash
cannot turn into a block. Register it as `python3 ".../heavy_gate.py" || true`.

Fast path (<200ms): one os.getloadavg(), one memory_pressure or /proc/meminfo read, one swap read
(no two-sample trend, no `top`). Test injection: PERUN_GATE_LOAD1, PERUN_GATE_CORES,
PERUN_GATE_FREE_RAM_PCT override the readings; PERUN_HEAVY_DIR points the lease dir at a fixture.
"""
import json
import os
import re
import fcntl
import shlex
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

DEFAULT_PATTERNS = (
    r"(python3? -m )?pytest\b", r"(npx |pnpm |yarn )?(jest|vitest|playwright)\b",
    r"(npm|pnpm|yarn|bun) (run )?test\b", r"cargo (test|nextest)\b", r"go test\b",
    r"(npx )?next build\b", r"(npm|pnpm|yarn|bun) run build\b", r"(npx )?tsc -b\b",
    # Whole-repo scanners (a global flag may precede the subcommand: `trivy --cache-dir D image`), installs, and Perun's scan/CI entrypoints.
    # osv-scanner, grype and checkov count only with an argument; grype's db|version|help are subcommands, not targets (a word that merely
    # starts with one, `db:latest` or `help.json`, is a target; osv-scanner takes directories, so its `db` can be one). A bare grype fed by a
    # pipe or `<` reads an SBOM from stdin, so _heavy reads it as `grype -`. Light, matching nothing: zizmor, actionlint, shellcheck, hadolint, bandit and ruff.
    # ponytail: a fixed tool list with the known-launcher ceiling of VALUE_WRAP, so a scanner behind docker, `bash -x PATH` or an unquoted
    # `$DIR/x.sh` path (the tokenizer splits at `$`) still passes light; add the launcher or tool when one shows up.
    r"semgrep( .*)? (scan|ci|--config)\b", r"trivy( .*)? (fs|repo|image|config|rootfs)\b", r"(osv-scanner|checkov) \S",
    r"grype (?!(db|version|help)(\s|$))\S",
    r"gitleaks( .*)? (detect|git|dir)\b", r"trufflehog( .*)? (git|filesystem|github)\b", r"(npm|pnpm|yarn|bun) (ci|i|install)\b",
    r"((ba|z)?sh )?(\S*/)?(review_checks|run-ci-tests|app_pentest)\.sh\b",
)
PUNCT = ";()<>|&\n"
# Joins backslash-newline (group 1 = the escaped pairs kept: an odd run of backslashes before the newline, an even run is escaped backslashes) and
# matches a `#` comment line only to leave it whole (group 1 is None): bash ends a comment at its newline, a trailing backslash included.
CONT = re.compile(r"^[ \t]*#.*|(?<!\\)((?:\\\\)*)\\\n", re.M)
# A separator ending in a pipe (`|`, `|&`, `)|`), not an or-list `||`. ponytail: a grype right after `(` or `{` (`cat s | (grype)`) still reads light.
PIPE = re.compile(r"(?<!\|)\|&?\n*$")
WRAP = re.compile(r"(\w+=\S*|command|npx|uvx|bunx|uv (tool )?run|poetry run|pipx run|(pnpm|npm) exec|(pnpm|yarn) dlx|bun x|python[\d.]* -m)$")
WRAP_VALUE_OPTS = {"-p", "--package", "--with", "--python", "--from"}  # `uv run --with x`, `npx -p pkg`
# Wrappers whose listed options take a separate value (`nice -n 5`); timeout also takes a DURATION positional.
# ponytail: a known-launcher list, so an unlisted one (watch, parallel, `{ ...; }`) still passes light; the gate is
# a host-load hold, not a security boundary.
VALUE_WRAP = {"env": {"-u", "--unset", "-C", "--chdir", "-P", "-a"}, "nice": {"-n", "--adjustment"}, "nohup": set(), "setsid": set(),
              "caffeinate": {"-t", "-w"}, "arch": {"-arch", "-e"}, "time": {"-f", "-o", "--format", "--output"}, "exec": {"-a"},
              "sudo": {"-u", "-g", "-h", "-p", "-C", "-D", "-R", "-T", "-r", "-U", "-t", "--user", "--group"}, "doas": {"-u", "-C"},
              "ionice": {"-c", "-n", "-p"}, "taskpolicy": {"-c", "-t", "-l", "-p"},
              "timeout": {"-s", "--signal", "-k", "--kill-after"}, "stdbuf": {"-i", "-o", "-e", "--input", "--output", "--error"},
              "xargs": {"-n", "-I", "-J", "-R", "-S", "-P", "-L", "-d", "-E", "-s", "-a", "--max-args", "--replace", "--max-procs",
                        "--max-lines", "--delimiter", "--eof", "--max-chars", "--arg-file"}}
SHELLS = {"bash", "sh", "zsh", "dash", "ksh", "fish"}
SHELL_VALUE_OPTS = {"-o", "-O", "+o", "+O", "--rcfile", "--init-file"}
# ponytail: `npm install --package-lock-only` counts as light, yet a bare one (no package args) without `--ignore-scripts` can still run the
# project's own lifecycle scripts (preinstall, prepare, ...), so a heavy script can hide behind it; require --ignore-scripts here if that bites.
LIGHT_FLAGS = {"--version", "--help", "-h", "--collect-only", "--co", "--list-affected",  # --list-affected: run-ci-tests.sh dry form
               "--download-db-only", "--download-java-db-only", "--package-lock-only"}  # trivy DB fetch, no scan; npm lockfile, no install
TEST_FILE = re.compile(r"[A-Za-z0-9_./-]+\.py(::[A-Za-z0-9_.\[\]-]+)*")
SHORT_FLAGS = re.compile(r"-[qvxsl]+")
PYTEST_VALUE_OPTS = {"-k", "-m", "-W", "-r", "-p", "-n", "-o", "-c", "--cov", "--cov-report", "--log-file", "--tb", "--maxfail",
                     "--durations", "--rootdir", "--basetemp", "--junitxml"}
PYTEST_FLAGS = {"--lf", "--ff", "--nf", "--sw", "--no-header", "--showlocals", "--strict-markers", "--failed-first",
                "--last-failed", "--verbose", "--quiet", "--exitfirst"}


def scoped_pytest(args) -> bool:
    """True when pytest `args` name one or two test files/nodeids and nothing else positional.
    Fail-closed: only options in PYTEST_FLAGS / SHORT_FLAGS (no value) or PYTEST_VALUE_OPTS (next arg skipped; `--opt=val`
    and the attached short form `-kfoo` match by name) are understood; any other option (`--ignore`, `--cache-dir`, ...)
    makes the run heavy. Every positional must fully match TEST_FILE (plain path chars ending `.py`, optional `::nodeid`),
    so a glob, brace list, `$var`, or directory is heavy. Expects tokens from segments(cmd, ":[]") so a colon or bracket
    stays inside its word and whitespace is never lost."""
    pos, skip = [], False
    for a in args:
        if skip:
            skip = False
        elif a.startswith("-"):
            if a.split("=")[0] in PYTEST_VALUE_OPTS:
                skip = "=" not in a
            elif a[:2] not in PYTEST_VALUE_OPTS or a.startswith("--"):  # else attached short value: -kfoo, -n4, -rA
                if a not in PYTEST_FLAGS and not SHORT_FLAGS.fullmatch(a):
                    return False
        elif TEST_FILE.fullmatch(a):
            pos.append(a)
        else:
            return False
    return 1 <= len(pos) <= 2


def tokens(command: str, extra: str = ""):
    """Shell tokens, punctuation (`;`, `|`, `>`, `&&`, newline) as tokens of their own. Quotes and heredoc bodies never split; raises ValueError on a parse error.
    `extra` chars are added to the word characters, so they stay inside a word instead of splitting it.
    A backslash-newline continuation is joined first (after the heredoc bodies are dropped, so a body line ending in a backslash stays
    literal); a `#` comment line is left whole, so a trailing backslash there does not join the next line into the comment."""
    lines, delim = [], None
    for line in command.split("\n"):
        if delim is not None:
            delim = None if line.strip() == delim else delim
            continue
        m = re.search(r"<<-?\s*(['\"]?)(\w+)\1", line)
        delim = m.group(2) if m else None
        lines.append(line)
    text = CONT.sub(lambda m: m.group(0) if m.group(1) is None else m.group(1), "\n".join(lines))
    lex = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lex.whitespace = " \t\r"
    lex.wordchars += extra
    return list(lex)


def _split(command: str, extra: str = ""):
    """`(tokens, separator before, separator after)` per shell segment (split at punctuation); raises ValueError on a parse error.
    A quoted empty argument (`sed -i '' ...`) is an argument, not a separator: `set('') <= set(PUNCT)` is true, hence the `tok and`.
    Bare newlines right after a separator do not replace it as the one before: `a | <newline> b` is still a pipe."""
    seg, out, before = [], [], ""
    for tok in tokens(command, extra):
        if tok and set(tok) <= set(PUNCT):
            out.append((seg, before, tok))
            seg, before = [], (before if not seg and not tok.strip("\n") else tok)
        else:
            seg.append(tok)
    return out + [(seg, before, "")]


def segments(command: str, extra: str = ""):
    """Token lists, one per shell segment (split at punctuation); raises ValueError on a parse error."""
    return [seg for seg, _, _ in _split(command, extra)]


def heavy_patterns():
    """Heavy-command regexes: the newline-separated ones in $PERUN_HEAVY_PATTERNS, else DEFAULT_PATTERNS."""
    env_pat = os.environ.get("PERUN_HEAVY_PATTERNS")
    return [p for p in env_pat.splitlines() if p.strip()] if env_pat else DEFAULT_PATTERNS


def strip_wrappers(toks):
    """Drop leading runner wrappers (env/VAR=x/time/sudo, npx|uvx|bunx, uv|poetry|pipx run, uv tool run, pnpm exec|dlx, npm exec,
    yarn dlx, bun x, python -m, nice, nohup, timeout DURATION, stdbuf, xargs) and their flags; a VALUE_WRAP option's separate value is dropped with it.
    `command -v|-V X` is a presence check, not a launcher: it returns [] so nothing is classified."""
    while toks:
        toks = [os.path.basename(toks[0]) or toks[0]] + toks[1:]  # /usr/bin/env, /usr/bin/python3 -m
        two = " ".join(toks[:2])
        if two in ("command -v", "command -V"):
            return []
        if toks[0] in VALUE_WRAP:
            opts, toks = VALUE_WRAP[toks[0]], toks[1:]
            while toks and toks[0].startswith("-") and toks[0] != "-":
                toks = toks[2:] if toks[0] in opts else toks[1:]
            if two.startswith("timeout"):
                toks = toks[1:]  # DURATION
            toks = toks[1:] if toks[:1] == ["--"] else toks
            continue
        n = next((n for n in (3, 2, 1) if WRAP.match(" ".join(toks[:n]))), 0)  # `uv tool run` is three words, `uv run` two, `npx` one
        if not n:
            break
        toks = toks[n:]
        while toks and toks[0].startswith("-"):
            toks = toks[2:] if toks[0] in WRAP_VALUE_OPTS else toks[1:]
    return toks


def is_heavy(command: str, patterns) -> bool:
    """True when a shell segment of `command` begins, after runner wrappers, with a heavy pattern.
    Quote- and heredoc-aware: `git commit -m "fix; pytest"` is not heavy; `cd x && uv run pytest` is.
    Light invocations (--version, --help, --collect-only, --list-affected, --download-db-only, --package-lock-only except on `ci`,
    `command -v TOOL`, `playwright install`) are never heavy. A bare `grype` after a pipe or before `<` reads an SBOM from stdin: heavy.
    A pytest run scoped to one or two explicit test files (`a.py`, `a.py::test`), with any -k, is light
    (the hold message advises it); no file, a directory, or a third file stays heavy (see scoped_pytest).
    `bash|sh -c 'STRING'` (any option cluster holding `c`, e.g. `-lc`) is checked as STRING.
    A command that does not parse (unclosed quote) is NOT heavy: the gate fails open; a `-c` STRING that does not
    parse is heavy (fails closed), since a heavy run is the likely reason to wrap it."""
    return _heavy(command, patterns, False)


def _heavy(command, patterns, on_parse_error):
    try:
        segs = _split(command or "", ":[]{}+%")  # `{}`, `+x`, `%e` stay one word: `xargs -I{} pytest {}`
    except ValueError:
        return on_parse_error
    for toks, before, after in segs:
        toks = strip_wrappers(toks)
        if toks == ["grype"] and (PIPE.search(before) or after.startswith("<")):
            toks = ["grype", "-"]  # a bare grype fed by a pipe or `<` reads an SBOM from stdin: it scans
        if toks and os.path.basename(toks[0]) in SHELLS:
            i = 1
            while i < len(toks) and toks[i][:1] and toks[i][:1] in "-+":
                i += 2 if toks[i] in SHELL_VALUE_OPTS else 1
            if i < len(toks) and any("c" in t for t in toks[1:i] if t[:1] == "-" and not t.startswith("--")):
                if _heavy(toks[i], patterns, True):
                    return True
                continue
        light = LIGHT_FLAGS - {"--package-lock-only"} if toks[1:2] == ["ci"] else LIGHT_FLAGS  # npm ci wipes node_modules, lockfile-only or not
        if not toks or light & set(toks) or (toks[0] == "playwright" and (toks[1:2] or [""])[0].startswith("install")):
            continue
        seg = " ".join(toks)
        if any(re.match(p, seg) for p in patterns):
            if toks[0] == "pytest" and scoped_pytest(toks[1:]):
                continue
            return True
    return False


def _float_env(name):
    v = os.environ.get(name)
    return float(v) if v not in (None, "") else None


def verdict(policy_cpu="efficient") -> tuple:
    """`(block_reason_or_None, load1, cores, free_ram_pct)` from fast readings."""
    import host_probe
    import perun_policy
    load1 = _float_env("PERUN_GATE_LOAD1")
    if load1 is None:
        load1 = os.getloadavg()[0]
    cores = int(_float_env("PERUN_GATE_CORES") or os.cpu_count() or 1)
    ram = _float_env("PERUN_GATE_FREE_RAM_PCT")
    if ram is None:
        ram = host_probe.read_free_ram_pct()
    if perun_policy.exclusive_holder(perun_policy.lease_dir()):
        return "HOLD gate running: wait", load1, cores, ram
    swap = 0.0  # one sample cannot show a trend; (0, 0) keeps decide() reading load and RAM
    v = host_probe.decide(swap_samples=(swap, swap), free_ram_pct=ram, lane_type="heavy",
                          load1=load1, cores=cores)
    if v.startswith("HOLD"):
        return v, load1, cores, ram
    slots = perun_policy.heavy_slots(cores, load1)
    if policy_cpu == "maximize":
        slots = max(slots, cores)
    held = perun_policy.lease_load(perun_policy.lease_dir())  # weighted: a light lane counts a fraction of a heavy one
    if held >= slots:
        return f"HOLD heavy-lease-full {held:g}/{slots}", load1, cores, ram
    return None, load1, cores, ram


def holders() -> str:
    """Who holds the machine-wide heavy slots, read from the lease files (no ps/top): `pid N (kind, Xm)` per live lease plus the
    exclusive train gate's pid. Empty when none is readable. Read-only."""
    import perun_policy
    d, now = perun_policy.lease_dir(), time.time()
    out = [f"pid {pid} ({(kind or 'heavy').split('@')[0]}, {max(0, int(now - start)) // 60}m)" for pid, start, kind in perun_policy._leases(d, now)]
    ex = perun_policy.exclusive_holder(d)
    return ", ".join(([f"train gate pid {ex}"] if ex else []) + out)


def wait_clear(first, load1, cores, ram, cpu):
    """Wait inside the hook for a transient HOLD instead of failing the turn: re-read `verdict` with backoff (1s, 2s, 4s ...)
    until it clears or $PERUN_HEAVY_HOOK_WAIT_SECS (default 60, hard cap 120, 0 = never wait) passes; returns the last verdict.
    Not waited for: the exclusive train gate (minutes to hours), and a host whose readings are injected by $PERUN_GATE_*
    (static, so waiting cannot change them) unless the wait env is set explicitly. The wait is clamped to the hook's own
    timeout minus 2s ($PERUN_HEAVY_HOOK_TIMEOUT, default 5 = what an old install's settings give; the template sets 70), because
    a host-killed hook runs `|| true` and fails open."""
    w = _float_env("PERUN_HEAVY_HOOK_WAIT_SECS")
    injected = any(os.environ.get(k) for k in ("PERUN_GATE_LOAD1", "PERUN_GATE_CORES", "PERUN_GATE_FREE_RAM_PCT"))
    room = (_float_env("PERUN_HEAVY_HOOK_TIMEOUT") or 5.0) - 2.0  # the hook's own timeout (old installs: 5s) minus 2s; a killed hook fails open
    w = max(0.0, min(120.0, room, 0.0 if w is None and injected else 60.0 if w is None else w))
    t0, step, v = time.time(), 1.0, (first, load1, cores, ram)
    while v[0] and "gate running" not in v[0] and time.time() - t0 < w:
        time.sleep(min(step, w - (time.time() - t0)))
        step = min(step * 2, 16.0)
        v = verdict(cpu)
    return v


MAX_DENIES, WINDOW = 3, 30 * 60


def _bypass(cmd: str, cwd: str, deny: bool, now=None) -> bool:
    """Ledger step. deny=True records a deny; deny=False asks whether MAX_DENIES recent denies already exist
    (True = allow with WARN, and the entry resets). Any I/O error returns False (keeps the deny)."""
    import hashlib
    import perun_policy
    now = time.time() if now is None else now
    f = perun_policy.lease_dir().parent / "heavy-denies.json"
    key = hashlib.sha1(f"{cwd}\0{' '.join(cmd.split())}".encode()).hexdigest()
    try:
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f.with_suffix(".lock"), "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)  # serialize the read-modify-write across concurrent hooks
            led = json.loads(f.read_text()) if f.is_file() else {}
            led = {k: [t for t in v if now - t < WINDOW] for k, v in led.items()}
            led = {k: v for k, v in led.items() if v}
            hit = not deny and len(led.get(key, [])) >= MAX_DENIES
            if hit:
                led.pop(key)
            elif deny:
                led.setdefault(key, []).append(now)
            f.write_text(json.dumps(led))
            return hit
    except (OSError, ValueError, AttributeError, TypeError):
        return False


def main() -> int:
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command", "")
        if not is_heavy(cmd, heavy_patterns()):
            return 0
        import perun_policy
        try:
            cpu = perun_policy.load().get("local_cpu", "efficient")
        except ValueError:
            cpu = "efficient"
        reason, load1, cores, ram = verdict(cpu)
        reason, load1, cores, ram = wait_clear(reason, load1, cores, ram, cpu)
        if not reason:
            return 0
        gate = "gate running" in reason  # the exclusive train lease is never bypassed
        if not gate and _bypass(cmd, str(data.get("cwd") or ""), deny=False):
            print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "additionalContext":
                  f"WARN: machine busy ({reason}) but this command was denied {MAX_DENIES} times in 30 min; "
                  "allowing it per the retry-3-then-proceed rule. Say so in your report."}}))
            return 0
        if not gate:
            _bypass(cmd, str(data.get("cwd") or ""), deny=True)
        ram_s = f"{ram:.0f}% free" if ram is not None else "unknown"
        try:
            who = holders()
        except Exception:  # enrichment only: it must never cancel the deny
            who = ""
        msg = (f"machine busy (load {load1:.1f}/{cores} cores, RAM {ram_s}; {reason}" + (f"; held by {who}" if who else "") + "): "
               "wait and retry, or narrow the command (one test file, a -k filter, a smaller scan path)")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": msg}}))
    except Exception:  # fail open: the gate must never block work because the gate broke
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
