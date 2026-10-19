#!/usr/bin/env python3
"""operating_selfcheck.py — per-item PRESENT / MISSING / COULD_NOT_CHECK report
for the always-on operating layer `references/operating-discipline.md` names.

WHY THIS EXISTS
---------------
Installing the skills reproduces the review method, not the operating
discipline: the host settings (`SubagentStart` house-default injector,
two-tier `SubagentStop` hand-back cap, subagent model pin) live OUTSIDE
anything the skill tree ships, so a second machine runs uncapped, unpinned,
and un-paced until someone notices. This script is the self-check step:
after `install.sh --with-operating-layer` writes the settings snippet and an
owner merges it, run this to confirm each item actually landed, item by item,
never a single "all green" that could hide one missed merge.

WHAT IT CHECKS, AND HOW
------------------------
Three items are **host-settable**, read from a `.claude/settings.json`-shaped
file (`--settings`, default `.claude/settings.json`):
- `subagent-start-injector` — a `SubagentStart` hook command containing
  `subagent_start_inject.py`.
- `handback-cap-two-tier` (name kept for compatibility) — a `SubagentStop` hook
  entry with no matcher (or `*` / `.*`) whose command contains `handback_cap.py`
  (the default cap). The second, `matcher`-scoped tier for a
  read-only review type is opt-in (`host-enforcement.md`): it needs the
  project's real agent type, so the template ships none and one entry is PRESENT.
- `subagent-model-pin` — `CLAUDE_CODE_SUBAGENT_MODEL` in the settings file's
  `env` block (`WARN:` when `_FORCE=1` pins a haiku-class model).
A settings file that does not exist at all reports all three `MISSING` (a
fresh install has none yet); an existing but unreadable/malformed one reports
all three `COULD_NOT_CHECK` instead — genuinely ambiguous, never guessed.

A fourth settings item, `ceo-altitude-guard`, is PRESENT only when `ceo_altitude_guard.py` is wired on both PreToolUse and
UserPromptSubmit. The report also prints the guard's drift counter (`ceo-altitude:` and `ceo-altitude-session <id>:` lines):
the role in effect, and how many direct source edits the main session made in each recent session of `--project`.

Two items are **script-file presence**, resolved relative to this script's
own installed skill directory (`--skill-root`, default: two directories up
from this file):
- `fan-out-probe` — `scripts/host_probe.py`.
- `usage-window-pacer` — the sibling `agentic-ceo` skill's
  `scripts/token_report.py`; `N/A: ... install.sh --with-ceo` (not `MISSING`) when that
  sibling skill isn't installed at all, since its absence is a project
  choice, not a broken install of this one.

The remaining layer items (model-and-effort-routing doctrine, conductor
rules, cross-session coordination, safety rules) are **protocol-only** — no
host artifact represents them, so they always report `COULD_NOT_CHECK:
protocol only, no host artifact` and point back at
`references/operating-discipline.md`.

USAGE
-----
  operating_selfcheck.py [--settings FILE] [--skill-root DIR]
  operating_selfcheck.py --selftest
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

PROTOCOL_ONLY = (
    "model-and-effort-routing-doctrine",
    "conductor-rules",
    "cross-session-coordination",
    "safety-rules",
)


SANDBOX_RED = ("MISSING RED: sandbox off -- an agent's `rm -rf` can delete your files; set sandbox.enabled=true and "
               "sandbox.allowUnsandboxedCommands=false (install.sh --apply-operating-layer)")


PIN_WARN = ("WARN: CLAUDE_CODE_SUBAGENT_MODEL_FORCE=1 pins every subagent to a haiku-class model "
            "(overrides lane agents: junk commits, lost hand-backs); pin to sonnet or unset FORCE")


def _flatten_commands(hook_entries: list) -> list:
    """Every `command` string nested under one hook-event's entry list."""
    out = []
    for entry in hook_entries or []:
        for h in (entry or {}).get("hooks", []) or []:
            cmd = h.get("command")
            if cmd:
                out.append(cmd)
    return out


HOUSE_RED = ("MISSING RED: injector hook wired but house-defaults file {f} is absent or empty -- the hook fails "
             "open and lanes run with no token cap/voice; re-run install.sh (writes a default if absent)")


def _house_status(start_cmds: list, settings_path: str) -> str:
    """PRESENT when a `subagent_start_inject.py` hook names a non-empty HOUSE_DEFAULTS_FILE, else MISSING/RED.

    `$CLAUDE_PROJECT_DIR` and relative paths resolve against `$CLAUDE_PROJECT_DIR`, else the cwd. A hook with no HOUSE_DEFAULTS_FILE assignment at all also fails open: RED.
    """
    cmds = [c for c in start_cmds if "subagent_start_inject.py" in c]
    if not cmds:
        return "MISSING"
    root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()  # not the settings path: user-level settings live in ~/.claude
    m = re.search(r'HOUSE_DEFAULTS_FILE=(?:"([^"]*)"|(\S+))', cmds[0])
    f = ((m.group(1) or m.group(2)) if m else "").replace("${CLAUDE_PROJECT_DIR}", root).replace("$CLAUDE_PROJECT_DIR", root)
    f = f and os.path.join(root, f)
    try:
        ok = bool(f) and os.path.getsize(f) > 0
    except OSError:
        ok = False
    return "PRESENT" if ok else HOUSE_RED.format(f=f or "(unset)")


def heavy_slot_lines(slots: int, lanes_n: int, env: dict, train: bool = False) -> list:
    """Lines reporting the effective heavy-slot count. WARN when `PERUN_POLICY` (env, a shell-rc leftover) overrides
    the repo policy, and when slots >1 because of that override or while a train holds its exclusive lease
    (its first-in-line slot should be serial). The default floor of 2 alone is not a warning."""
    src = f"env PERUN_POLICY={env['PERUN_POLICY']}" if env.get("PERUN_POLICY") else "repo policy"
    out = [f"heavy-slots: {slots} (lanes {lanes_n}; source: {src})"]
    if slots > 1 and (train or env.get("PERUN_POLICY")):
        out.append(f"heavy-slots: WARN: {slots} > 1: a train's first-in-line slot can run {slots} heavy commands at once; "
                   "set local_cpu=off (serial) or tokens=off to force 1")
    if env.get("PERUN_POLICY"):
        out.append("heavy-slots: WARN: PERUN_POLICY set in the environment overrides the repo policy (leftover in a shell rc?); unset it unless intended")
    return out


def check_settings(settings_path: str) -> dict:
    """`{item: status}` for the three host-settable items in one settings file.

    A settings file that does not exist at all unambiguously means the
    operating-layer snippet was never merged: all three report `MISSING`,
    not `COULD_NOT_CHECK` (a fresh install has no `.claude/settings.json`
    until an owner writes one). An existing-but-unreadable/malformed file is
    genuinely ambiguous (owner content, corrupted, wrong shape) and reports
    `COULD_NOT_CHECK` instead — never guessed either way.
    """
    if not os.path.exists(settings_path):
        return {"subagent-start-injector": "MISSING", "handback-cap-two-tier": "MISSING",
                "subagent-model-pin": "MISSING", "sandbox-on": SANDBOX_RED, "ceo-altitude-guard": "MISSING"}
    try:
        with open(settings_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        reason = "COULD_NOT_CHECK: unreadable or malformed settings file"
        return {"subagent-start-injector": reason, "handback-cap-two-tier": reason,
                "subagent-model-pin": reason, "sandbox-on": reason, "ceo-altitude-guard": reason}
    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    # the guard needs both events: PreToolUse counts and flags, UserPromptSubmit resets the turn and reads the owner override
    guard = [any("ceo_altitude_guard.py" in c for c in _flatten_commands(hooks.get(ev, [])))
             for ev in ("PreToolUse", "UserPromptSubmit")]
    start_cmds = _flatten_commands(hooks.get("SubagentStart", []))
    stop_cmds = _flatten_commands(hooks.get("SubagentStop", []))
    default_tier = any(isinstance(e, dict) and str(e.get("matcher", "")) in ("", "*", ".*")
                       and any("handback_cap.py" in c for c in _flatten_commands([e]))
                       for e in hooks.get("SubagentStop", []))
    handback_status = "PRESENT" if default_tier else (
        "MISSING (handback_cap.py only under a scoped matcher -- no default entry)"
        if any("handback_cap.py" in c for c in stop_cmds) else "MISSING")
    env = data.get("env", {}) if isinstance(data, dict) else {}
    sb = data.get("sandbox", {}) if isinstance(data, dict) else {}
    sb = sb if isinstance(sb, dict) else {}
    return {
        "subagent-start-injector": _house_status(start_cmds, settings_path),
        "handback-cap-two-tier": handback_status,
        "subagent-model-pin": PIN_WARN if (str(env.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE")) in ("1", "true")
                                           and "haiku" in str(env.get("CLAUDE_CODE_SUBAGENT_MODEL", "")).lower())
                              else "PRESENT" if "CLAUDE_CODE_SUBAGENT_MODEL" in env else "MISSING",
        "sandbox-on": "PRESENT" if sb.get("enabled") is True and sb.get("allowUnsandboxedCommands") is False
                      else SANDBOX_RED,
        "ceo-altitude-guard": "PRESENT" if all(guard) else "MISSING" + (
            " (needs both PreToolUse and UserPromptSubmit: per-turn reset and the owner override)" if any(guard) else ""),
    }


def check_scripts(skill_root: str) -> dict:
    """`{item: status}` for the script-file-presence items, relative to `skill_root`."""
    probe = os.path.join(skill_root, "scripts", "host_probe.py")
    pacer = os.path.normpath(os.path.join(skill_root, "..", "agentic-ceo", "scripts", "token_report.py"))
    pacer_sibling_dir = os.path.dirname(os.path.dirname(pacer))
    ratchet = os.path.join(pacer_sibling_dir, "scripts", "token_ratchet.py")
    if os.path.isfile(pacer):
        pacer_status = "PRESENT"
    elif os.path.isdir(pacer_sibling_dir):
        pacer_status = "MISSING"
    else:
        pacer_status = "N/A: agentic-ceo not installed; add it with install.sh --with-ceo"
    return {
        "fan-out-probe": "PRESENT" if os.path.isfile(probe) else "MISSING",
        "usage-window-pacer": pacer_status,
        # token_ratchet.py = tokens per delivered PR vs a baseline; same N/A rule as the pacer
        "token-ratchet": ("PRESENT" if os.path.isfile(ratchet) else "MISSING")
        if os.path.isdir(pacer_sibling_dir) else pacer_status,
        # weekly_receipt.py = one-screen value card; presence only, WARN-level (never blocks)
        "weekly-receipt": ("PRESENT" if os.path.isfile(os.path.join(pacer_sibling_dir, "scripts", "weekly_receipt.py"))
                           else "MISSING") if os.path.isdir(pacer_sibling_dir) else pacer_status,
    }


def report(settings_path: str, skill_root: str) -> dict:
    """The full `{item: status}` report: settings-backed + script-file + protocol-only items."""
    out = {}
    out.update(check_settings(settings_path))
    out.update(check_scripts(skill_root))
    for item in PROTOCOL_ONLY:
        out[item] = "COULD_NOT_CHECK: protocol only, no host artifact -- see references/operating-discipline.md"
    return out


GH_WARN = ("WARN: sandbox on and gh not excluded -- gh may fail with `x509 ... OSStatus -26276`; run "
           "`/sandbox exclude \"gh *\"` (gh then runs unsandboxed; see docs/host-safety.md#common-sandbox-errors)")


def sandbox_gh_warn(settings_path: str) -> str | None:
    """`GH_WARN` when settings turn the sandbox on and no `sandbox.excludedCommands` entry covers `gh`.

    Reads settings only; None when the file is missing/unreadable, the sandbox is off, or gh is excluded.
    """
    try:
        with open(settings_path, encoding="utf-8") as fh:
            sb = json.load(fh).get("sandbox")
    except (OSError, ValueError, AttributeError):
        return None
    if not isinstance(sb, dict) or sb.get("enabled") is not True:
        return None
    ex = sb.get("excludedCommands")
    ex = ex if isinstance(ex, list) else []
    if any(isinstance(e, str) and (e.strip() == "gh" or e.strip().startswith(("gh ", "gh:"))) for e in ex):
        return None
    return GH_WARN


TRAIN_CTX = "perun/train-gate"


def _gh_json(path: str):
    """(rc, parsed-json-or-None, stderr) for a read-only `gh api` GET; routed through gh_rest for the sandbox TLS fallback."""
    import subprocess
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gh_rest
    args = ["gh", "api", "--paginate", path]
    try:
        p = subprocess.run(args, capture_output=True, text=True, timeout=30)
        rc, out, err = gh_rest.fallback(args, p.returncode, p.stdout, p.stderr)
    except (OSError, subprocess.SubprocessError) as e:
        return 1, None, str(e)
    if rc != 0:
        return rc, None, err
    try:  # --paginate prints back-to-back JSON values: merge arrays, keep a lone object
        dec, i, vals = json.JSONDecoder(), 0, []
        while i < len(out):
            if out[i].isspace():
                i += 1
                continue
            v, i = dec.raw_decode(out, i)
            vals.append(v)
        return 0, ([x for v in vals for x in v] if vals and all(isinstance(v, list) for v in vals) else vals[0] if vals else []), ""
    except ValueError:
        return 1, None, "unparseable gh output"


def train_gate_line(base: str, gh=_gh_json) -> str:
    """One doctor line: does `base` require the `perun/train-gate` status? Read-only (branch protection + rulesets).

    PRESENT only when a classic protection or a ruleset names the context. A definite "not protected"
    (404 on protection, no ruleset naming it) -> WARN. Any other failure (auth, network, no gh) -> COULD_NOT_CHECK, never green.
    """
    slug = "{owner}/{repo}"
    rc, data, err = gh(f"repos/{slug}/branches/{base}/protection/required_status_checks?per_page=100")
    named = rc == 0 and TRAIN_CTX in ((data or {}).get("contexts") or []) + [c.get("context") for c in (data or {}).get("checks") or []]
    rc2, rules, err2 = gh(f"repos/{slug}/rules/branches/{base}?per_page=100")
    if rc2 == 0 and not named:
        named = any(TRAIN_CTX == c.get("context") for r in rules or [] if r.get("type") == "required_status_checks"
                    for c in (r.get("parameters") or {}).get("required_status_checks") or [])
    if named:
        return f"train-gate: PRESENT ({base} requires a status named {TRAIN_CTX}; matched by name only, the app/source is not verified)"
    if rc != 0 or rc2 != 0:  # 404/403/network on either read: absence cannot be proven
        why = (err if rc != 0 else err2).strip()[:80]
        return f"train-gate: COULD_NOT_CHECK (cannot read protection/rulesets for {base}: {why})"
    return (f"WARN: train-gate: {base} does not require a status named {TRAIN_CTX} (name-only match) -- an agent can self-merge "
            "past the train; add it as a required check (references/merge-queue-worktrees.md)")


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(description="Per-item present/missing/could-not-check report "
                                                  "for the always-on operating layer.")
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    parser.add_argument("--settings", default=".claude/settings.json")
    parser.add_argument("--skill-root", default=default_root)
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--base", default="main", help="integration branch checked for the train-gate required status")
    parser.add_argument("--project", default=".", help="project root scanned for per-host sandbox status")
    args = parser.parse_args(argv)
    if args.selftest:
        return _selftest()
    rep = report(args.settings, args.skill_root)
    tsv = os.path.join(args.skill_root, "templates", "host-safety.tsv")
    if os.path.exists(tsv):  # per-host sandbox status (host_safety.py); absent in a trimmed install
        sys.path.insert(0, os.path.join(args.skill_root, "scripts"))
        import host_safety
        rep.update(host_safety.report(args.project, tsv))
    for item, status in sorted(rep.items()):
        print(f"{item}: {status}")
    try:
        sys.path.insert(0, os.path.join(args.skill_root, "scripts"))
        import host_probe
        import perun_policy
        pol = perun_policy.load()
        load1, cores = host_probe.read_load1_and_cores()
        cores, idle = cores or os.cpu_count() or 1, host_probe.read_cpu_idle_pct()
        for line in heavy_slot_lines(perun_policy.heavy_slots(cores, load1, pol["tokens"], idle),
                                     perun_policy.lanes(pol["local_cpu"], cores, load1, pol["tokens"], idle), os.environ,
                                     perun_policy.exclusive_holder(perun_policy.lease_dir()) is not None):
            print(line)
    except (ImportError, ValueError, OSError) as e:
        print(f"heavy-slots: COULD_NOT_CHECK ({e})")
    try:  # drift counter: direct source edits by the main session, per session (always counted; the role only warns or blocks)
        sys.path.insert(0, os.path.join(args.skill_root, "scripts"))
        import ceo_altitude_guard
        for line in ceo_altitude_guard.report_lines(args.project):
            print(line)
    except Exception as e:  # advisory: never fail the self-check over a counter
        print(f"ceo-altitude: COULD_NOT_CHECK ({e})")
    print(train_gate_line(args.base))
    warn = sandbox_gh_warn(args.settings)
    if warn:
        print(warn)
    try:
        import perun_auto_update
        warn = perun_auto_update.behind_warn(Path(args.project).resolve())
    except Exception:
        warn = None
    if warn:
        print(warn)
    return 0


# ---------------------------------------------------------------------------
# --selftest — exercises check_settings()/check_scripts() directly.
# ---------------------------------------------------------------------------
def _selftest() -> int:
    import tempfile

    passed = 0
    failed = 0

    def case(name, got, want):
        nonlocal passed, failed
        if got == want:
            passed += 1
            print(f"PASS  {name}")
        else:
            failed += 1
            print(f"FAIL  {name} (got {got!r}, want {want!r})")

    tmp = tempfile.mkdtemp(prefix="operating-selfcheck-selftest-")
    try:
        before_path = os.path.join(tmp, "before.json")
        with open(before_path, "w", encoding="utf-8") as fh:
            json.dump({}, fh)
        before = check_settings(before_path)
        case("before-merge-start-missing", before["subagent-start-injector"], "MISSING")
        case("before-merge-handback-missing", before["handback-cap-two-tier"], "MISSING")
        case("before-merge-pin-missing", before["subagent-model-pin"], "MISSING")

        one_tier_path = os.path.join(tmp, "one_tier.json")
        with open(one_tier_path, "w", encoding="utf-8") as fh:
            json.dump({"hooks": {"SubagentStop": [
                {"hooks": [{"type": "command", "command": "python3 .../handback_cap.py"}]}]}}, fh)
        one_tier = check_settings(one_tier_path)
        case("one-entry-handback-present", one_tier["handback-cap-two-tier"], "PRESENT")
        scoped_path = os.path.join(tmp, "scoped.json")
        with open(scoped_path, "w") as fh:
            json.dump({"hooks": {"SubagentStop": [{"matcher": "reviewer",
                "hooks": [{"type": "command", "command": "python3 .../handback_cap.py"}]}]}}, fh)
        case("scoped-only-handback-missing", check_settings(scoped_path)["handback-cap-two-tier"].startswith("MISSING"), True)

        case("before-merge-sandbox-red", before["sandbox-on"].startswith("MISSING RED"), True)
        half_path = os.path.join(tmp, "half.json")
        with open(half_path, "w", encoding="utf-8") as fh:
            json.dump({"sandbox": {"enabled": True}}, fh)
        case("sandbox-enabled-but-unsandboxed-allowed-red",
             check_settings(half_path)["sandbox-on"].startswith("MISSING RED"), True)

        after_path = os.path.join(tmp, "after.json")
        with open(after_path, "w", encoding="utf-8") as fh:
            json.dump({
                "hooks": {
                    "SubagentStart": [{"hooks": [{"type": "command",
                        "command": "HOUSE_DEFAULTS_FILE=\"$CLAUDE_PROJECT_DIR/.claude/house-defaults.md\" python3 .../subagent_start_inject.py"}]}],
                    "SubagentStop": [
                        {"hooks": [{"type": "command", "command": "python3 .../handback_cap.py"}]},
                        {"matcher": "reviewer", "hooks": [{"type": "command",
                            "command": "HANDBACK_MAX_LINES=25 python3 .../handback_cap.py"}]},
                    ],
                },
                "env": {"CLAUDE_CODE_SUBAGENT_MODEL": "haiku"},
                "sandbox": {"enabled": True, "allowUnsandboxedCommands": False},
            }, fh)
        os.environ["CLAUDE_PROJECT_DIR"] = tmp
        os.makedirs(os.path.join(tmp, ".claude"))
        hf = os.path.join(tmp, ".claude", "house-defaults.md")
        after_path = os.path.join(tmp, ".claude", "after.json")
        with open(after_path, "w", encoding="utf-8") as fh:
            json.dump(json.load(open(os.path.join(tmp, "after.json"))), fh)
        case("house-file-absent-red", check_settings(after_path)["subagent-start-injector"].startswith("MISSING RED"), True)
        open(hf, "w").close()
        case("house-file-empty-red", check_settings(after_path)["subagent-start-injector"].startswith("MISSING RED"), True)
        with open(hf, "w", encoding="utf-8") as fh:
            fh.write("one rule\n")
        after = check_settings(after_path)
        case("after-merge-start-present", after["subagent-start-injector"], "PRESENT")
        case("after-merge-handback-two-tier-present", after["handback-cap-two-tier"], "PRESENT")
        case("after-merge-pin-present", after["subagent-model-pin"], "PRESENT")
        case("after-merge-sandbox-present", after["sandbox-on"], "PRESENT")

        guard_cmd = [{"hooks": [{"type": "command", "command": "python3 .../ceo_altitude_guard.py || true"}]}]
        guard_path = os.path.join(tmp, "guard.json")
        for name, hooks, want in (("both", {"PreToolUse": guard_cmd, "UserPromptSubmit": guard_cmd}, "PRESENT"),
                                  ("pre-only", {"PreToolUse": guard_cmd}, "MISSING (needs both")):
            with open(guard_path, "w", encoding="utf-8") as fh:
                json.dump({"hooks": hooks}, fh)
            case(f"ceo-guard-{name}", check_settings(guard_path)["ceo-altitude-guard"].startswith(want), True)
        case("ceo-guard-before-merge-missing", before["ceo-altitude-guard"], "MISSING")

        case("no-settings-file-missing-not-could-not-check",
             check_settings(os.path.join(tmp, "does-not-exist.json"))["subagent-start-injector"], "MISSING")
        malformed_path = os.path.join(tmp, "malformed.json")
        with open(malformed_path, "w", encoding="utf-8") as fh:
            fh.write("{not json")
        case("malformed-settings-could-not-check",
             check_settings(malformed_path)["handback-cap-two-tier"].startswith("COULD_NOT_CHECK"), True)

        gh_path = os.path.join(tmp, "gh.json")
        for name, sb, want in (("off", {"enabled": False}, False), ("on-no-exclude", {"enabled": True}, True),
                               ("on-excluded", {"enabled": True, "excludedCommands": ["gh *"]}, False),
                               ("on-other-exclude", {"enabled": True, "excludedCommands": ["ghost"]}, True)):
            with open(gh_path, "w", encoding="utf-8") as fh:
                json.dump({"sandbox": sb}, fh)
            case(f"gh-warn-{name}", sandbox_gh_warn(gh_path) is not None, want)
        case("gh-warn-no-file", sandbox_gh_warn(os.path.join(tmp, "nope.json")), None)

        def stub(rc, data, err=""):
            return lambda path: (rc, data, err)
        case("train-gate-classic-ok", train_gate_line("main", stub(0, {"contexts": [TRAIN_CTX]})).startswith("train-gate: PRESENT"), True)
        rs = [{"type": "required_status_checks", "parameters": {"required_status_checks": [{"context": TRAIN_CTX}]}}]
        def two(a, b):
            seq = iter([a, b])
            return lambda p: next(seq)
        case("train-gate-ruleset-ok", train_gate_line("main", two((1, None, "HTTP 404"), (0, rs, ""))).startswith("train-gate: PRESENT"), True)
        case("train-gate-both-read-not-named-warns", train_gate_line("main", two((0, {"contexts": []}, ""), (0, [], ""))).startswith("WARN: train-gate"), True)
        case("train-gate-404-protection-is-could-not-check", train_gate_line("main", two((1, None, "HTTP 404"), (0, [], ""))).startswith("train-gate: COULD_NOT_CHECK"), True)
        case("train-gate-rules-403-is-could-not-check", train_gate_line("main", two((0, {"contexts": []}, ""), (1, None, "HTTP 403"))).startswith("train-gate: COULD_NOT_CHECK"), True)
        case("train-gate-other-check-warns", train_gate_line("main", lambda p: (0, {"contexts": ["ci"]} if "protection" in p else [], "")).startswith("WARN"), True)
        case("train-gate-unknown-not-green", train_gate_line("main", stub(1, None, "HTTP 403")).startswith("train-gate: COULD_NOT_CHECK"), True)

        # script-file presence against this repo's own real, installed skill root
        real_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        real = check_scripts(real_root)
        case("real-skill-root-fan-out-probe-present", real["fan-out-probe"], "PRESENT")

        fake_root = os.path.join(tmp, "no-such-skill")
        os.makedirs(fake_root)
        fake = check_scripts(fake_root)
        case("fake-skill-root-fan-out-probe-missing", fake["fan-out-probe"], "MISSING")
        case("fake-skill-root-pacer-could-not-check",
             fake["usage-window-pacer"].startswith("N/A") and "--with-ceo" in fake["usage-window-pacer"], True)

        case("fake-skill-root-ratchet-na", fake["token-ratchet"].startswith("N/A"), True)
        case("fake-skill-root-receipt-na", fake["weekly-receipt"].startswith("N/A"), True)
        case("real-skill-root-receipt-present", real["weekly-receipt"], "PRESENT")
        full = report(after_path, real_root)
        for item in PROTOCOL_ONLY:
            case(f"protocol-only-{item}-could-not-check", full[item].startswith("COULD_NOT_CHECK"), True)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)

    print(f"\nselftest: {passed}/{passed + failed} passed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
