#!/usr/bin/env python3
"""heavy_gate.py — PreToolUse(Bash) hook: defer a heavy local command while the machine is busy.

WHY: host_probe.py and the heavy-lease primitive in perun_policy.py existed but nothing called
them, so fleets ran 10+ test runners at once (load1 > 3x cores, swap climbing, OOM kills). This
hook runs on every Bash call, so the admission check happens without anyone remembering it.

What it does: if the command starts a test runner or a build (DEFAULT_PATTERNS, or the
newline-separated regexes in $PERUN_HEAVY_PATTERNS, each matched at the start of a shell segment, after runner wrappers are stripped),
it denies the call when host_probe.decide(lane_type="heavy") says HOLD (load1 > cores or low free
RAM; swap is not read, one sample shows no trend) or when the machine-wide heavy leases already fill the
slot count (perun_policy.heavy_slots; local_cpu=maximize raises it to every core). Otherwise it
prints nothing and the call proceeds. While a train gate holds the EXCLUSIVE lease (perun_policy.py heavy-exclusive) every heavy command is denied with "gate running: wait" and that deny is never bypassed or counted. It never takes a lease and never stops or deletes anything.

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
)
PUNCT = ";()<>|&\n"
WRAP = re.compile(r"(\w+=\S*|env|time|nice|command|exec|sudo|npx|uv run|poetry run|pipx run|pnpm exec|python[\d.]* -m)$")
LIGHT_FLAGS = {"--version", "--help", "-h", "--collect-only", "--co"}
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
    `extra` chars are added to the word characters, so they stay inside a word instead of splitting it."""
    lines, delim = [], None
    for line in command.split("\n"):
        if delim is not None:
            delim = None if line.strip() == delim else delim
            continue
        m = re.search(r"<<-?\s*(['\"]?)(\w+)\1", line)
        delim = m.group(2) if m else None
        lines.append(line)
    lex = shlex.shlex("\n".join(lines), posix=True, punctuation_chars=PUNCT)
    lex.whitespace = " \t\r"
    lex.wordchars += extra
    return list(lex)


def segments(command: str, extra: str = ""):
    """Token lists, one per shell segment (split at punctuation); raises ValueError on a parse error.
    A quoted empty argument (`sed -i '' ...`) is an argument, not a separator: `set('') <= set(PUNCT)` is true, hence the `tok and`."""
    seg, out = [], []
    for tok in tokens(command, extra):
        if tok and set(tok) <= set(PUNCT):
            out.append(seg)
            seg = []
        else:
            seg.append(tok)
    return out + [seg]


def heavy_patterns():
    """Heavy-command regexes: the newline-separated ones in $PERUN_HEAVY_PATTERNS, else DEFAULT_PATTERNS."""
    env_pat = os.environ.get("PERUN_HEAVY_PATTERNS")
    return [p for p in env_pat.splitlines() if p.strip()] if env_pat else DEFAULT_PATTERNS


def strip_wrappers(toks):
    """Drop leading runner wrappers (env/VAR=x/time/sudo, npx, uv|poetry|pipx run, pnpm exec, python -m) and their flags."""
    while toks:
        two = " ".join(toks[:2])
        if WRAP.match(two) and len(toks) > 1:
            toks = toks[2:]
        elif WRAP.match(toks[0]):
            toks = toks[1:]
        else:
            break
        while toks and toks[0].startswith("-"):
            toks = toks[1:]
    return toks


def is_heavy(command: str, patterns) -> bool:
    """True when a shell segment of `command` begins, after runner wrappers, with a heavy pattern.
    Quote- and heredoc-aware: `git commit -m "fix; pytest"` is not heavy; `cd x && uv run pytest` is.
    Light invocations (--version, --help, --collect-only, `playwright install`) are never heavy.
    A pytest run scoped to one or two explicit test files (`a.py`, `a.py::test`), with any -k, is light
    (the hold message advises it); no file, a directory, or a third file stays heavy (see scoped_pytest).
    A command that does not parse (unclosed quote) is NOT heavy: the gate fails open."""
    try:
        segs = segments(command or "", ":[]")
    except ValueError:
        return False
    for toks in segs:
        toks = strip_wrappers(toks)
        if not toks or LIGHT_FLAGS & set(toks) or (toks[0] == "playwright" and (toks[1:2] or [""])[0].startswith("install")):
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
        msg = (f"machine busy (load {load1:.1f}/{cores} cores, RAM {ram_s}; {reason}): "
               "wait and retry, or run a narrower test (one file or -k filter)")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse",
                                                 "permissionDecision": "deny",
                                                 "permissionDecisionReason": msg}}))
    except Exception:  # fail open: the gate must never block work because the gate broke
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
