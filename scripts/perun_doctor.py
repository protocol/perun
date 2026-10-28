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
import argparse, hashlib, json, os, re, shlex, subprocess, sys
from pathlib import Path

SRC = Path(__file__).resolve().parent.parent
SKIP = {".git", "node_modules", ".venv", "__pycache__", "worktrees", "skill-backups"}
SKILL_HOSTS = (".claude", ".cursor", ".agents", ".codex", ".gemini", ".opencode", ".github", ".windsurf", ".hermes", ".kiro", ".cline", ".roo", ".factory", ".qwen", ".grok")  # every root install.sh can write
HOOK_SCRIPTS = ("pipe_mask_guard.py", "bypass_guard.py", "destructive_guard.py", "subagent_start_inject.py", "handback_cap.py", "context_nudge.py", "lane_resume_nudge.py", "ceo_altitude_guard.py", "comms_guard.py", "outcome_claim_guard.py", "landing_watchdog.py", "stall_guard.py", "reply_cap.py", "decision_gate.py", "repeat_poll_guard.py", "subagent_brief_lint.py")  # operating-layer template


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


DB_BINS = ("postgres", "postmaster", "mysqld", "mongod", "redis-server")
DB_DIR = re.compile(r"(?:\s-D\s*|--datadir[= ]|--dbpath[= ]|--dir[= ])(/[^\s]+)")


def orphan_dbs(ps_text):
    """[(pid, data_dir)] for dev-DB servers (postgres, mysqld, mongod, redis-server) whose absolute data dir no longer exists on
    disk, e.g. its worktree was removed while the server kept running. `ps_text` is `ps -A -o pid=,command=` output. Read-only:
    nothing is killed or deleted; the caller prints the owner's cleanup command."""
    out = []
    for ln in ps_text.splitlines():
        pid, _, cmd = ln.strip().partition(" ")
        m = DB_DIR.search(" " + cmd)
        if pid.isdigit() and m and os.path.basename(cmd.split()[0]) in DB_BINS:
            rest = (" " + cmd)[m.start(1):]  # the path may hold spaces: gone only if no whitespace-joined prefix exists
            words = rest.split(" ")
            if not any(os.path.exists(" ".join(words[:i])) for i in range(1, len(words) + 1)):
                out.append((int(pid), m.group(1)))
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
        cmd = f"DCR_NO_PULL=1 bash {shlex.quote(str(SRC / 'scripts/update-installed.sh'))} {shlex.quote(str(home))}"
        add("WARN", "global copy", f"~/.claude has {g}, checkout has {latest} (stale; auto-update and --fix skip it). Run this yourself (type it with the ! prefix if the permission classifier blocks agents): {cmd}")
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
    for host in SKILL_HOSTS[1:]:  # non-symlink host copies must equal the canonical .claude copy (install.sh links them when it can)
        for d in sorted((repo / host / "skills").glob("*")) if (repo / host / "skills").is_dir() else ():
            c = repo / ".claude/skills" / d.name
            if d.is_symlink() and not d.exists():
                drift.append(f"{d.relative_to(repo)} (dangling symlink)")
            if d.is_symlink() or not d.is_dir() or not c.is_dir():
                continue
            h = lambda r: {str(p.relative_to(r)): sha(p) for p in walk(r)}
            if h(d) != h(c):
                drift.append(f"{d.relative_to(repo)} (differs from .claude copy)")
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
        top = subprocess.run(["git", "-C", str(repo), "rev-parse", "--show-toplevel"], capture_output=True, text=True).stdout.strip()
        isgit = bool(top) and os.path.realpath(top) == os.path.realpath(repo)  # a dir nested in a parent repo is not itself a repo
        items = [c for c in sandbox_probe.checks(repo) if c[0] != "git" or (isgit and repo.resolve() != home.resolve())]  # a global (~) or non-git target has no repo to probe
        for line in sandbox_probe.probe(items)[0][:-1]:
            st, _, rest = line.partition(" ")
            name, _, detail = rest.strip().partition(": ")
            add({"OK": "OK", "SKIP": "INFO"}.get(st, "WARN"), f"sandbox {name}", detail or "works")
    if not os.environ.get("DCR_NO_PROBE"):
        try:
            orph = orphan_dbs(subprocess.run(["ps", "-A", "-o", "pid=,command="], capture_output=True, text=True, timeout=10, check=True).stdout)
        except (OSError, subprocess.SubprocessError):
            add("INFO", "orphan dev DBs", "ps unreadable: not checked")
        else:
            add("WARN" if orph else "OK", "orphan dev DBs", (f"{len(orph)} DB server(s) run on a data dir that is gone ({', '.join(f'pid {p} {d}' for p, d in orph[:4])}). Stop them yourself, nothing was killed: kill -TERM {' '.join(str(p) for p, _ in orph)}") if orph else "none")
    try:
        mx, mgb = int(os.environ.get("PERUN_WT_MAX", 20)), int(os.environ.get("PERUN_WT_MAX_GB", 20))
    except ValueError:
        mx, mgb = 20, 20
    try:
        inside, outside = lane_worktrees(repo)
        for label, paths in (("lane worktrees in repo", inside), ("lane worktrees out of tree", outside)):
            if not paths:
                continue
            kb, full = _du(paths, 0 if os.environ.get("DCR_NO_PROBE") else 30)
            big = len(paths) > mx or (kb or 0) > mgb * 1048576
            size = "" if kb is None else f", {'at least ' if not full else ''}{kb / 1048576:.1f} GB"
            hint = (" (file watchers such as fseventsd scan all of it). Create lanes outside it with .claude/skills/agentic-delivery/scripts/lane_worktree.sh and remove finished ones: git worktree remove <path>" if "in repo" in label else ". Remove finished ones: git worktree remove <path>") if big else ""
            add("WARN" if big else "OK", label, f"{len(paths)} worktree(s){size}{hint}")
    except (OSError, subprocess.SubprocessError, TypeError, AttributeError):
        add("INFO", "lane worktrees", "git worktree list failed: not checked")
    return rows


def lane_worktrees(repo):
    """([in-repo paths], [out-of-tree paths]) of this repo's linked worktrees. In-repo = inside `repo` (what file watchers
    scan); out-of-tree = under the lane root (PERUN_WT_ROOT, default ${XDG_CACHE_HOME:-~/.cache}/perun-wt). The main
    checkout and a bare repo's own entry are skipped by path, not by position."""
    g = lambda *a: subprocess.run(["git", "-C", str(repo), *a], capture_output=True, text=True, timeout=30).stdout.strip()
    common = os.path.realpath(os.path.join(str(repo), g("rev-parse", "--git-common-dir")))
    main = os.path.dirname(common) if os.path.basename(common) == ".git" else common
    root = os.path.realpath(os.environ.get("PERUN_WT_ROOT") or os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "perun-wt"))
    wts = [os.path.realpath(b.splitlines()[0][9:]) for b in g("worktree", "list", "--porcelain").split("\n\n") if b.startswith("worktree ") and "\nbare" not in b]
    wts = [w for w in wts if w != main]
    here = os.path.realpath(repo)
    return [w for w in wts if w.startswith(here + os.sep)], [w for w in wts if w.startswith(root + os.sep)]


def _du(paths, budget):
    """(kilobytes, complete) summed over `du -sk` per path within `budget` seconds in all; (None, False) when budget is 0."""
    import time
    end, kb = time.time() + budget, 0
    for w in paths:
        left = end - time.time()
        if left <= 0:
            return (kb if kb else None), False
        try:
            kb += int(subprocess.run(["du", "-sk", w], capture_output=True, text=True, timeout=left).stdout.split()[0])
        except (OSError, subprocess.SubprocessError, IndexError, ValueError):
            return (kb if kb else None), False
    return kb, True


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
