#!/usr/bin/env python3
"""perun doctor: report whether an installed Perun actually runs in a repo.

Usage: python3 scripts/perun_doctor.py [REPO] [--fix [--yes]] [--home DIR]

Checks, in plain language: installed version vs this checkout (and the global copy),
hook entries whose files exist, shipped hook scripts that nothing calls, forked copies
that drifted from the checkout (sha256), janitor/scheduler presence, policy file, and the
sandbox probe (git, ssl, network, local bind, ~/.cache write; DCR_NO_PROBE=1 skips it), and an advisory
"To run autonomously, add:" section from sandbox_preflight.py (read-only advice: the permissions, sandbox excludes and
domains this repo's own flows need; it never changes the exit code).
Exit 0 = nothing to fix, 1 = at least one WARN/FAIL (INFO rows are optional add-ons and never fail the exit code). `--fix` prints a plan (and what default-on would add), needs a typed yes on a TTY or --yes, then
re-runs the recorded install flags via scripts/update-installed.sh (skills are backed up
by install.sh first), and re-checks. Stdlib only; read-only without --fix.
"""
import argparse, hashlib, json, os, re, subprocess, sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
SKIP = {".git", "node_modules", ".venv", "__pycache__", "worktrees", "skill-backups"}
SKILL_HOSTS = (".claude", ".cursor", ".agents", ".codex", ".gemini", ".opencode", ".github", ".windsurf", ".hermes", ".kiro", ".cline", ".roo", ".factory", ".qwen", ".grok")  # every root install.sh can write
HOOK_SCRIPTS = ("pipe_mask_guard.py", "bypass_guard.py", "destructive_guard.py", "subagent_start_inject.py", "handback_cap.py", "context_nudge.py", "lane_resume_nudge.py", "ceo_altitude_guard.py", "comms_guard.py", "outcome_claim_guard.py", "landing_watchdog.py")  # operating-layer template


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def ver(d):
    f = Path(d) / ".claude/skills/deep-code-review/VERSION"
    return f.read_text().strip() if f.is_file() else None


def _git_files(root):
    """Tracked + untracked-not-ignored files when root is a git work-tree root, else None."""
    g = ["git", "-C", str(root)]
    r = subprocess.run(g + ["rev-parse", "--show-prefix"], capture_output=True, text=True)
    if r.returncode or r.stdout.strip():
        return None
    out = subprocess.run(g + ["ls-files", "-z", "-co", "--exclude-standard"], capture_output=True, text=True).stdout
    return [f for f in out.split("\0") if f]


def walk(root, depth=6):
    files = _git_files(root)
    if files is not None:  # never descend into nested worktrees or ignored build dirs
        for f in files:
            parts = Path(f).parts
            if len(parts) - 1 <= depth and not SKIP.intersection(parts) and (Path(root) / f).is_file():
                yield Path(root) / f
        return
    for dp, dn, fn in os.walk(root):
        dn[:] = [d for d in dn if d not in SKIP]
        if len(Path(dp).relative_to(root).parts) > depth:
            dn[:] = []
        for f in fn:
            yield Path(dp) / f


def hook_commands(repo):
    cmds = []
    for n in ("settings.json", "settings.local.json"):
        f = repo / ".claude" / n
        try:
            hooks = json.loads(f.read_text()).get("hooks", {})
        except (OSError, ValueError):
            continue
        for entries in hooks.values():
            for e in entries:
                cmds += [h.get("command", "") for h in e.get("hooks", [])]
    return cmds


def settings_env(repo):
    env = {}
    for n in ("settings.json", "settings.local.json"):
        try:
            env.update(json.loads((repo / ".claude" / n).read_text()).get("env", {}))
        except (OSError, ValueError, AttributeError):
            pass
    return env


def flag_words(repo):
    """Flags from the tracked record plus the untracked machine-local one."""
    out = []
    for n in (".dcr-install-flags", ".dcr-install-flags.local"):
        f = repo / ".claude" / n
        # update-installed.sh honors these three only from the local file
        out += [w for w in (f.read_text().split() if f.is_file() else [])
                if n.endswith(".local") or w not in ("--apply-operating-layer", "--with-operating-layer", "--no-sandbox")]
    return out


def check(repo, home):
    rows = []  # (status, check, detail)
    add = lambda s, c, d: rows.append((s, c, d))
    flags = repo / ".claude/.dcr-install-flags"
    flagtxt = flag_words(repo)
    latest, mine = ver(SRC), ver(repo)
    if not mine:
        add("FAIL", "installed version", "deep-code-review not installed in this repo")
    elif latest and mine != latest:
        add("WARN", "installed version", f"repo has {mine}, checkout has {latest}")
    else:
        add("OK", "installed version", f"{mine} (matches checkout)")
    g = ver(home)
    if g and latest and g != latest:
        add("WARN", "global copy", f"~/.claude has {g}, checkout has {latest} (stale; global is not touched by --fix)")
    else:
        add("OK", "global copy", g or "none")
    if not flags.is_file():
        add("WARN", "install record", ".claude/.dcr-install-flags missing: --fix cannot replay your flags")
    # hooks reference existing files
    cmds = [re.sub(r'"?\$\{?CLAUDE_PROJECT_DIR\}?/?"?', "", c) for c in hook_commands(repo)]  # project-dir anchored paths resolve against repo
    missing = sorted({m for c in cmds for m in re.findall(r"[\w./-]+\.(?:py|sh)\b", c) if not (repo / m).is_file()})
    add("FAIL" if missing else "OK", "hook files exist", ("missing: " + ", ".join(missing)) if missing else f"{len(cmds)} hook command(s) resolve")
    rel = sorted({c for c in hook_commands(repo) if re.search(r"(?:^|[\s=])\.{0,2}/?\.claude/", c)})
    if rel:  # cwd-relative: breaks (silently) when the cwd is not the repo root, e.g. inside a worktree
        add("WARN", "hook paths", f"{len(rel)} hook command(s) use relative .claude/ paths and fail outside the repo root; re-run install.sh --apply-operating-layer (restart sessions after): " + "; ".join(rel[:2]))
    env = settings_env(repo)
    if str(env.get("CLAUDE_CODE_SUBAGENT_MODEL_FORCE")) in ("1", "true") and "haiku" in str(env.get("CLAUDE_CODE_SUBAGENT_MODEL", "")).lower():
        add("WARN", "subagent model", "FORCE=1 pins every subagent to haiku (overrides lane agents; junk commits, lost hand-backs): pin to sonnet or unset FORCE")
    # mechanisms with no caller
    opted_out = "--no-operating-layer" in flagtxt
    sd = repo / ".claude/skills/agentic-delivery/scripts"
    if sd.is_dir():
        unwired = [s for s in HOOK_SCRIPTS if (sd / s).is_file() and not any(s in c for c in cmds)]
        if unwired and opted_out:
            add("OK", "hooks wired", "operating layer opted out (--no-operating-layer)")
        elif unwired:
            add("FAIL", "hooks wired", "installed but never runs: " + ", ".join(unwired) + " (no hook calls them)")
        else:
            add("OK", "hooks wired", "operating-layer hooks all call their scripts")
        callers = "".join(cmds)
        for w in (repo / ".github/workflows").glob("*") if (repo / ".github/workflows").is_dir() else []:
            callers += w.read_text(errors="ignore")
        for f in (repo / ".claude/loops").glob("*") if (repo / ".claude/loops").is_dir() else []:
            callers += f.read_text(errors="ignore")
        scripts = sorted(p for p in (repo / ".claude/skills").glob("*/scripts/*") if p.is_file())
        texts = {p: p.read_text(errors="ignore") for p in scripts}
        idle = [p.name for p in scripts if p.name not in callers and not any(p.name in t for q, t in texts.items() if q != p)]
        if idle:
            add("INFO", "manual-only scripts", f"{len(idle)} script(s) no hook/workflow/loop/script calls: " + ", ".join(idle[:8]) + (" ..." if len(idle) > 8 else ""))
    # drift: skill copies and loose forks vs checkout
    drift = []
    srcfiles = {}
    for p in walk(SRC / ".claude/skills"):
        srcfiles.setdefault(p.name, []).append(sha(p))
    for host in SKILL_HOSTS:
        base = repo / host / "skills"
        for p in walk(base) if base.is_dir() else ():
            rel = p.relative_to(base)
            s = SRC / ".claude/skills" / rel
            if rel.parts[:2] == ("deep-code-review", "references") and (SRC / "docs" / rel.name).is_file():
                s = SRC / "docs" / rel.name  # install.sh overwrites these two from docs/
            if s.is_file() and sha(s) != sha(p) and rel.name != "INDEX.md":
                drift.append(str(p.relative_to(repo)))
    for p in walk(repo):
        rel = p.relative_to(repo).parts
        if rel[0] in SKILL_HOSTS and len(rel) > 1 and rel[1] == "skills":
            continue
        if p.suffix in (".py", ".sh") and p.name in srcfiles and sha(p) not in srcfiles[p.name]:
            drift.append(str(p.relative_to(repo)) + " (forked copy)")
    add("WARN" if drift else "OK", "drifted copies", (f"{len(drift)} differ from checkout: " + ", ".join(sorted(drift)[:6]) + (" ..." if len(drift) > 6 else "")) if drift else "none")
    # janitor/scheduler
    names = [p for p in walk(repo, 4) if re.search(r"janitor|scheduler", p.name, re.I)]
    add("OK" if names else "INFO", "janitor/scheduler", f"found {names[0].relative_to(repo)}" if names else "none (optional add-on install does not ship: nothing runs Perun on a schedule)")
    # policy
    pol = [p for p in walk(repo, 3) if re.search(r"perun[-_]?policy.*\.(json|ya?ml|toml)$", p.name, re.I)]
    add("OK" if pol else "INFO", "policy file", f"found {pol[0].relative_to(repo)}" if pol else "none (optional; defaults apply, write one with install.sh --policy)")
    # sandbox probe: harmless checks; each failure names its exact fix. DCR_NO_PROBE=1 skips (tests, offline).
    if not os.environ.get("DCR_NO_PROBE"):
        sys.path.insert(0, str(SRC / ".claude/skills/agentic-delivery/scripts"))
        import sandbox_probe
        for line in sandbox_probe.probe(sandbox_probe.checks(repo))[0][:-1]:
            st, _, rest = line.partition(" ")
            name, _, detail = rest.strip().partition(": ")
            add({"OK": "OK", "SKIP": "INFO"}.get(st, "WARN"), f"sandbox {name}", detail or "works")
    return rows


def advice(repo, home):
    """The advisory 'To run autonomously, add:' text; never raises (an advisor bug must not break the doctor)."""
    sys.path.insert(0, str(SRC / ".claude/skills/agentic-delivery/scripts"))
    try:
        import sandbox_preflight
        return sandbox_preflight.advise(repo, home)
    except Exception as e:  # noqa: BLE001
        return f"To run autonomously: advice unavailable ({type(e).__name__})"


def show(rows):
    w = max(len(r[1]) for r in rows)
    for s, c, d in rows:
        print(f"{s:<5} {c:<{w}}  {d}")


FIXABLE = {"installed version", "install record", "hook files exist", "hooks wired", "drifted copies"}


def verdict(rows, repo):
    """One plain-English line: 'Healthy' or 'N things need attention: run X' (X is the fix command when one exists)."""
    bad = [r for r in rows if r[0] in ("WARN", "FAIL")]
    if not bad:
        return "Healthy: nothing needs attention."
    n = len(bad)
    todo = (f"run python3 {SRC}/scripts/perun_doctor.py {repo} --fix" if any(r[1] in FIXABLE for r in bad)
            else "see the WARN/FAIL rows below and add what is missing")
    return f"{n} thing{'s' if n != 1 else ''} need{'' if n != 1 else 's'} attention: {todo}"


def default_on_preview(repo):
    """Lines describing what the default-on operating layer would add when old flags are replayed."""
    flags = flag_words(repo)
    if not ({"--with-delivery", "--full"} & set(flags)) or {"--no-operating-layer", "--with-operating-layer", "--apply-operating-layer"} & set(flags):
        return []
    t = json.loads((SRC / ".claude/skills/agentic-delivery/templates/operating-layer.settings.json").read_text())
    cfg = repo / ".claude/settings.local.json"
    try:
        has_model = "model" in json.loads(cfg.read_text())
    except (OSError, ValueError):
        has_model = False
    return ["Default-on operating layer: replaying your old flags will ALSO write to .claude/settings.local.json (backup saved as .bak.<timestamp>):",
            "  hooks: " + ", ".join(sorted(t["hooks"])) + " (placeholder-matcher entries skipped)",
            "  env: " + ", ".join(t["env"]),
            "  model: " + ("your existing model kept" if has_model else "sonnet (you have none)"),
            "  opt out instead: add --no-operating-layer to .claude/.dcr-install-flags"]


def confirmed(yes):
    if yes:
        print("warning: --yes given, applying without an interactive confirmation", file=sys.stderr)
        return True
    if not sys.stdin.isatty():
        print("error: --fix needs a TTY to confirm (type yes) or --yes; nothing changed", file=sys.stderr)
        return False
    return input("Apply this plan? Type yes: ").strip() == "yes"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--fix", action="store_true")
    ap.add_argument("--yes", action="store_true", help="with --fix: skip the typed confirmation (prints a warning)")
    ap.add_argument("--home", default=str(Path.home()))
    a = ap.parse_args(argv)
    repo, home = Path(a.repo).resolve(), Path(a.home)
    rows = check(repo, home)
    print(verdict(rows, repo), "\n", sep="")
    show(rows)
    print("\n" + advice(repo, home))
    bad = [r for r in rows if r[0] in ("WARN", "FAIL")]
    if a.fix and bad:
        if not any(r[1] in FIXABLE for r in bad):
            print("\nNothing here a reinstall fixes (see each WARN row).")
            return 1
        print(f"\nPlan: bash {SRC}/scripts/update-installed.sh {repo}  (replays .claude/.dcr-install-flags; "
              "existing skills move to <host>/skill-backups/; loose forks and the global copy are left alone)")
        print("\n".join(default_on_preview(repo)))
        if not confirmed(a.yes):
            return 2
        r = subprocess.run(["bash", str(SRC / "scripts/update-installed.sh"), str(repo)], env={**os.environ, "DCR_NO_PULL": "1"})
        if r.returncode != 0:
            print(f"error: update-installed.sh failed (exit {r.returncode}); repo may be partly updated, see skill-backups", file=sys.stderr)
            return 2
        print("\nAfter fix:")
        rows = check(repo, home)
        print(verdict(rows, repo), "\n", sep="")
        show(rows)
        bad = [r for r in rows if r[0] in ("WARN", "FAIL")]
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
