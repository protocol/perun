#!/usr/bin/env python3
"""sandbox_preflight.py: autonomy advisor. Prints what to grant so agents can work in a repo without prompts, with least privilege.

Usage: python3 sandbox_preflight.py [REPO] [--home DIR]

READ-ONLY and advice only (exit 0 always): it never writes a settings file or anything else, and it runs no repo
code (git is asked only for the remotes and core.hooksPath). The owner decides and applies what they choose.

It reads REPO's package.json scripts, Makefile, git hooks (.githooks, .husky, core.hooksPath, .git/hooks), top-level
scripts/ script/ bin/ files, and the settings that already apply (REPO/.claude/settings.json,
REPO/.claude/settings.local.json, HOME/.claude/settings.json; --home defaults to ~). Then it prints a section that starts
with "To run autonomously, add:" holding ONLY what those settings do not already cover. The safety boundary is the OS
sandbox (writes confined to the repo, network limited to the allowlist), so the main output is sandbox config:
  (a) sandbox.enabled, no unsandboxed retry, sandbox.excludedCommands for commands the sandbox breaks (tsx Unix-socket
      IPC, headless browsers, database clients, gh TLS on macOS, docker, git over SSH on macOS), written as the command
      the agent types (a script or make target that calls the tool internally needs ITS entry excluded, so risk is
      followed through package scripts, make targets, git hooks and scripts), plus sandbox.network.allowedDomains for the
      push remote, GitHub's API host and the package registries the flows use, allowLocalBinding (macOS) for dev
      servers and allowWrite for literal writes outside the repo (credential and shell-config paths are never advised).
  (b) permissions.allow for the repo's gate and build commands (matched by NAME: test, lint, check, build...) and
      `git push <remote> HEAD`, printed with a disclosure: they run repo-controlled code (a test runner executes
      conftest, config files and build scripts, and no static check can make that safe), so they are safe only with the
      sandbox enabled. If the sandbox is not enabled in the settings that apply, NO allow rule is printed: enable it
      first. A unit with a publish/deploy/release/push word in its name or body is never allowed (an ask rule instead).
  (c) permissions.deny for destructive git, rm -rf and sudo, permissions.ask for publish, deploy and release commands;
      what stays blocked or asks you on purpose; and per host the mechanism the vendor docs confirm (Claude Code
      settings and /permissions, Codex approval modes). Allow rules are checked against destructive_guard.py (a sample
      call, `*` replaced by an argument): one the guard blocks is dropped and reported.
Excluded commands get no allow rule: they prompt on each run. `analyze()` returns the data and `advise()` the text;
perun_doctor.py and install.sh print it.

Precision over recall: a tool counts only at a command position (line start, after `&&` `;` `|` `$(` `then`, after
sudo/env/npx/yarn, or as the first element of a subprocess/exec call in a .py/.js/.ts script), never inside a path,
filename or prose, so a script that merely mentions docker or playwright is not excluded. The scan is still a text
scan, a lead and not a verdict: it cannot see what a command does at run time (a test that binds a port, a tool that
writes to a cache), and multi-line calls are missed. Setting names and syntax were checked against the Claude Code and
Codex docs listed in docs/standards-index.md (fetched 2026-10-16). `/sandbox exclude <pattern>` is named by Claude
Code's own sandbox error text but is not on the docs pages checked, so the advice leads with the documented key.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import destructive_guard  # noqa: E402  (sibling module: every advised allow rule is checked against it)

GATE = re.compile(r"^(test|tests|e2e|integration|coverage|lint|check|checks|typecheck|type-check|types|format|fmt|"
                  r"verify|validate|ci|precommit|pre-commit|presubmit|prepush|pre-push|gate)(?![a-z0-9])", re.I)
BUILD = re.compile(r"^(build|compile|bundle)(?![a-z0-9])", re.I)
# a release/publish/deploy/push word in a unit's NAME or in any line of its BODY (including the units it runs)
# makes it needs-approval, never allow-listed: `ci:publish`, `check-deploy`, a gate script that runs `npm publish`
SHIP = re.compile(r"(?<![a-z0-9])(?:publish|deploy|release|push|ship|upload)(?![a-z0-9])|^(?:version|tag)(?![a-z0-9])", re.I)
HOOKS = {"pre-commit": "git commit *", "commit-msg": "git commit *", "prepare-commit-msg": "git commit *",
         "pre-push": "git push *"}
INTERP = {".sh": "bash", ".bash": "bash", ".py": "python3", ".js": "node", ".mjs": "node", ".cjs": "node", ".ts": None}
CODE = (".py", ".js", ".mjs", ".cjs", ".ts")
# permissions.deny / ask entries that make "stays blocked" a settings rule (text rules only: the sandbox and
# destructive_guard.py are the layers that do not depend on how a command is spelled)
DENY = ("git push --force *", "git push -f *", "git push --delete *", "git push -d *", "git push --mirror *",
        "git push * +*", "git push * :*", "git reset --hard *", "git clean *", "git branch -D *",
        "rm -rf *", "rm -fr *", "rm -r *", "rm -R *", "sudo *")
ASK = ("npm publish *", "pnpm publish *", "cargo publish *", "twine upload *", "gh release create *", "gh release upload *")
SENSITIVE = (".ssh", ".aws", ".gnupg", ".claude", ".config/gh", ".netrc", ".npmrc", ".docker", ".gitconfig",
             ".zshrc", ".zprofile", ".bashrc", ".bash_profile", ".profile")

CMD = (r"(?:^|[;&|`!]|\$\(|\b(?:if|elif|while|until|then|do|else|sudo|exec|nohup|time|xargs|npx|pnpx|bunx|env|"
       r"cross-env|concurrently|yarn)\b|\b\w+=\S*)\s*")  # a command position in shell text
END = r"(?![\w./=:@-])"                                  # the word ends: not part of a path, filename or option
SPAWN = re.compile(r"subprocess|\bos\.(?:system|popen)|\bPopen|check_(?:output|call)|\bexec\w*\(|\bspawn\w*\(|\bexeca\w*\(")
# key: (tool regex, why it fails in the sandbox, "exclude" | "port" | "note")
RISKS = {
    "tsx": (r"tsx", "tsx opens a Unix-socket pipe for IPC and the macOS sandbox blocks every Unix socket "
            "(a pid-named pipe cannot be listed in sandbox.network.allowUnixSockets)", "exclude"),
    "browser": (r"playwright|puppeteer|chromium|google-chrome|chrome|cypress|geckodriver|chromedriver|wdio",
                "headless browsers need macOS XPC/Mach services the sandbox blocks (the docs name "
                "sandbox.network.allowMachLookup for Playwright but not the service names, so the command is excluded)",
                "exclude"),
    "db": (r"psql|pg_dump|pg_restore|pg_isready|createdb|dropdb|mysql|mysqldump|redis-cli|mongosh?|"
           r"prisma\s+(?:migrate|db)|drizzle-kit|knex|alembic|dbmate|sqlx",
           "database clients open their own TCP connection and ignore the sandbox proxy, so they fail even to an "
           "allowed host", "exclude"),
    "gh": (r"gh(?=\s+[a-z])", "gh (a Go CLI) can fail TLS verification under macOS Seatbelt (x509 OSStatus -26276)",
           "exclude"),
    "docker": (r"docker(?:-compose|\s+compose)?", "docker is incompatible with the sandbox", "exclude"),
    "port": (r"vite(?!\s+build)|next\s+(?:dev|start)|nuxt\s+dev|astro\s+dev|webpack-dev-server|webpack\s+serve|nodemon|"
             r"http-server|live-server|serve|uvicorn|gunicorn|flask\s+run|(?:python3?\s+)?manage\.py\s+runserver|"
             r"python3?\s+-m\s+http\.server|php\s+-S|rails\s+s(?:erver)?|ng\s+serve|storybook",
             "it listens on a local port, which the macOS sandbox blocks unless sandbox.network.allowLocalBinding is "
             "true (no effect on Linux/WSL2, where a command's localhost is private to it)", "port"),
    "jest": (r"jest(?!.*--no-watchman)", "jest uses watchman, which is incompatible with the sandbox: add "
             "--no-watchman to the jest command (no setting fixes it)", "note"),
}
RX = {mode: {k: re.compile(pre + r"(?:" + tool + r")" + END) for k, (tool, _, _) in RISKS.items()}
      for mode, pre in (("shell", CMD), ("code", r"""["']\s*"""))}
DBURL = re.compile(r"\bpostgres(?:ql)?://")
PATH = r"""["']?(~/[\w.@+/-]+|\$\{?HOME\}?/[\w.@+/-]+|/tmp/[\w.@+/-]+|\.\./[\w.@+/-]+)"""
WRITE = re.compile(r"(?:>>?|\btee(?:\s+-a)?|\bmkdir(?:\s+-p)?|\btouch|\s-o|--(?:output|outdir|cache-dir|cache|prefix)[=\s]|"
                   r"\b(?:cp|mv)\s+(?:-\S+\s+)*\S+)\s*" + PATH)  # the path is the operand of a write, not any mention
STAY = (
    "Force-push, ref deletion and mirror pushes: denied above and blocked by destructive_guard.py. Only a plain `git push` "
    "of HEAD to this repo's own remote is advised; a Bash rule cannot tell branches apart, so protect main on the host.",
    "rm -rf and other recursive deletes, git reset --hard, git clean, whole-tree checkout or restore, git branch -D, "
    "git stash drop|clear: denied above or blocked by destructive_guard.py. To run one anyway, type it yourself with "
    "the ! prefix.",
    "Writes outside the repo: the sandbox allows only the working directory and $TMPDIR; allowWrite above names only "
    "literal paths the scripts write. Nothing else is widened, and other repos are never granted.",
    "Publish, deploy and release commands (npm publish, gh release, a script or target with such a word) ask you: see the "
    "ask rules above.",
    "Commands in excludedCommands run outside the sandbox with your full access and prompt on each run (no allow rule "
    "is advised); Claude can edit an excluded script in the repo and run it, so read it before you approve.",
    "gh pr create, gh pr merge, gh api, gh release: not allow-listed (gh runs unsandboxed with your credentials); they prompt.",
)
HOSTS = (
    "Claude Code: apply the JSON above to .claude/settings.local.json (untracked, yours) or ~/.claude/settings.json "
    "(every project), or add the rules in /permissions. https://code.claude.com/docs/en/permissions",
    'Codex: ~/.codex/config.toml: sandbox_mode = "workspace-write" and approval_policy = "on-request" (commands the '
    "sandbox allows then run without approval); the network is off by default: add network_access = true under "
    "[sandbox_workspace_write] if a flow needs it; per-command allow rules are on Codex's separate Rules page (not "
    "verified here). https://learn.chatgpt.com/docs/agent-approvals-security",
)


SAFE = re.compile(r"(?!.*\.\.)[\w.:@+/-]+")  # a repo-chosen name that may become part of a rule: no space, quote, `*`, `..` or shell syntax


def _clean(s):
    """Printable ASCII only, so a hostile repo line cannot smuggle terminal escapes into the advice."""
    return re.sub(r"[^\x20-\x7e]", "?", s)


def _text(p):
    """First 200 KB of a file; "" when unreadable, absent or a symlink (never followed out of the repo)."""
    try:
        if Path(p).is_symlink():
            return ""
        with open(p, errors="replace") as f:
            return f.read(200_000)
    except OSError:
        return ""


def _lines(text):
    return [s for s in (ln.strip() for ln in text.splitlines()) if s and not s.startswith(("#", "//"))]


def _git(repo, *args):
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_COMMON_DIR", "GIT_INDEX_FILE")}
    try:
        p = subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=10, env=env)
    except (OSError, subprocess.SubprocessError):
        return ""
    return p.stdout if p.returncode == 0 else ""


def _remote(repo):
    """(name, host, is_ssh) of the push remote (origin, else the first), or None."""
    urls = dict(ln.split(None, 1) for ln in _git(repo, "config", "--get-regexp", r"^remote\..+\.url$").splitlines()
                if " " in ln)
    if not urls:
        return None
    key = "remote.origin.url" if "remote.origin.url" in urls else sorted(urls)[0]
    url = urls[key].strip()
    m = re.match(r"^[a-z+]+://(?:[^@/]+@)?([^/:]+)", url) or re.match(r"^(?:[^@/]+@)?([^:/]+):", url)
    name = key[len("remote."):-len(".url")]
    if not (m and SAFE.fullmatch(name) and re.fullmatch(r"[a-z0-9.-]+", m.group(1).lower())):
        return None
    return name, m.group(1).lower(), not url.startswith(("http://", "https://"))


def _unit(label, kind, name, entries, lines, run=None, run_code=None, deps=(), code=False, key=""):
    """One thing the agent can run (or git runs for it); `entries` are the commands the agent types for it, `run`
    and `run_code` match another unit's text (shell, or a script's code) that runs this one (`key` is a substring
    every such text contains: a cheap prefilter)."""
    hits, writes = {}, set()
    for ln in lines:
        if not code or SPAWN.search(ln):
            for risk, rx in RX["code" if code else "shell"].items():
                if risk not in hits and rx.search(ln):
                    hits[risk] = (label, _clean(ln[:90]))
        if not code:
            if "db" not in hits and DBURL.search(ln):
                hits["db"] = (label, _clean(ln[:90]))
            writes |= {(m.replace("${HOME}", "~").replace("$HOME", "~"), label) for m in WRITE.findall(ln)}
    return NS(label=label, kind=kind, name=name, entries=entries, lines=lines, run=run, run_code=run_code,
              deps=set(deps), hits=hits, writes=writes, code=code, key=key)


def _makefile(repo):
    """{target: (deps, recipe lines)} from the Makefile (no includes, no conditionals)."""
    targets, cur = {}, None
    for ln in (_text(repo / "Makefile") or _text(repo / "GNUmakefile") or _text(repo / "makefile")).splitlines():
        m = re.match(r"^([A-Za-z0-9_][\w.-]*)\s*:(?![=:])\s*(.*)$", ln)
        if m and not ln.startswith("\t"):
            cur = m.group(1)
            targets[cur] = (m.group(2).split(), [])
        elif ln.startswith("\t") and cur:
            targets[cur][1].extend(_lines(ln.strip().lstrip("@-+ ")))
    return targets


def _units(repo):
    us = []
    pm = ("pnpm" if (repo / "pnpm-lock.yaml").exists() else "yarn" if (repo / "yarn.lock").exists()
          else "bun" if (repo / "bun.lockb").exists() or (repo / "bun.lock").exists() else "npm")
    try:
        scripts = json.loads(_text(repo / "package.json") or "{}").get("scripts") or {}
    except (ValueError, AttributeError):
        scripts = {}
    for name, cmd in (scripts.items() if isinstance(scripts, dict) else ()):
        if isinstance(cmd, str) and SAFE.fullmatch(name):
            ents = [f"{pm} run {name} *"] + ([f"{pm} {name} *"] if name in ("test", "start") and pm != "bun" else [])
            us.append(_unit(f"package.json scripts.{name}", "npm", name, ents, [cmd],
                            re.compile(CMD + rf"(?:npm|pnpm|yarn|bun)\s+(?:run\s+)?{re.escape(name)}(?![\w:.-])"), key=name))
    for t, (deps, recipe) in _makefile(repo).items():
        us.append(_unit(f"Makefile:{t}", "make", t, [f"make {t} *"], recipe,
                        re.compile(CMD + rf"(?:make|\$[({{]MAKE[)}}])\s+(?:-\S+\s+)*{re.escape(t)}(?![\w.-])"), deps=deps, key=t))
    hooks_path = _git(repo, "config", "core.hooksPath").strip()
    hook_dirs = {".githooks", ".husky", ".git/hooks"} | ({hooks_path} if SAFE.fullmatch(hooks_path)
                                                         and not hooks_path.startswith("/") and ".." not in hooks_path else set())
    for d in sorted(hook_dirs):
        for f in sorted((repo / d).glob("*")) if (repo / d).is_dir() else ():
            if f.name in HOOKS and f.is_file():
                us.append(_unit(f"{d}/{f.name}", "hook", f.name, [HOOKS[f.name]], _lines(_text(f))))
    for d in ("scripts", "script", "bin"):
        for f in sorted((repo / d).glob("*"))[:400] if (repo / d).is_dir() else ():
            if f.is_file() and f.suffix in INTERP and SAFE.fullmatch(f.name):
                rel = f"{d}/{f.name}"
                ents = [f"{INTERP[f.suffix]} {rel} *"] if INTERP[f.suffix] else []
                us.append(_unit(rel, "script", f.stem, ents, _lines(_text(f)),
                                re.compile(CMD + r"(?:(?:ba)?sh\s+|python3?\s+|node\s+|source\s+|\.\s+)?(?:\./)?"
                                           + re.escape(rel) + r"(?![\w.-])"),
                                re.compile(re.escape(rel) + r"(?![\w.-])"), code=f.suffix in CODE, key=rel))
    return us


def _edges(us):
    """{id(u): [units u runs]}: a make dependency, an npm pre/post script, or text that runs the other unit."""
    text = {id(u): "\n".join(u.lines) for u in us}
    out = {id(u): [] for u in us}
    for u in us:
        for v in us:
            rx = v.run_code if u.code else v.run
            if v is not u and ((u.kind == v.kind == "make" and v.name in u.deps)
                               or (rx and v.key in text[id(u)] and rx.search(text[id(u)]))
                               or (u.kind == v.kind == "npm" and v.name in (f"pre{u.name}", f"post{u.name}"))):
                out[id(u)].append(v)
    return out


def _spread(us, edges):
    """A unit that runs a risky unit is risky too: its typed command is what an exclusion has to match."""
    changed = True
    while changed:
        changed = False
        for u in us:
            for v in edges[id(u)]:
                new = {k: o for k, o in v.hits.items() if k not in u.hits}
                if new or v.writes - u.writes:
                    u.hits.update(new)
                    u.writes |= v.writes
                    changed = True


def _body(u, edges):
    """Every line `u` runs: its own and those of all units it runs, transitively."""
    seen, todo, out = set(), [u], []
    while todo:
        w = todo.pop()
        if id(w) not in seen:
            seen.add(id(w))
            out += w.lines
            todo += edges[id(w)]
    return out


def _list(x):
    return [s for s in x if isinstance(s, str)] if isinstance(x, list) else []


def _dict(x):
    return x if isinstance(x, dict) else {}


def _effective(repo, home):
    """What the settings that already apply grant (lists unioned, as Claude Code merges them)."""
    eff = {"allow": [], "ask": [], "deny": [], "exclude": [], "domains": [], "write": [], "enabled": False,
           "retry": None, "binding": False}
    for p in (home / ".claude/settings.json", repo / ".claude/settings.json", repo / ".claude/settings.local.json"):
        try:
            d = _dict(json.loads(_text(p) or "{}"))
        except ValueError:
            continue
        perm, sb = _dict(d.get("permissions")), _dict(d.get("sandbox"))
        net, fs = _dict(sb.get("network")), _dict(sb.get("filesystem"))
        for key, val in (("allow", perm.get("allow")), ("ask", perm.get("ask")), ("deny", perm.get("deny")),
                         ("exclude", sb.get("excludedCommands")), ("domains", net.get("allowedDomains")),
                         ("write", fs.get("allowWrite"))):
            eff[key] += _list(val)
        if "enabled" in sb:  # scalars resolve last-wins in precedence order (user, project, local), not OR-merged
            eff["enabled"] = sb["enabled"] is True
        if "allowLocalBinding" in net:
            eff["binding"] = net["allowLocalBinding"] is True
        if "allowUnsandboxedCommands" in sb:
            eff["retry"] = sb["allowUnsandboxedCommands"]
    return eff


def _specs(rules):
    """Bash(...) rules, or bare excludedCommands entries, as match specs; `x:*` means `x *`, a bare `Bash` means all."""
    out = []
    for r in rules:
        m = re.fullmatch(r"Bash\((.*)\)", r, re.S)
        s = m.group(1) if m else "*" if r == "Bash" else None if re.match(r"[A-Z]\w*\(", r) else r
        if s is not None:
            out.append(re.sub(r"(?<=\S):\*$", " *", s))  # the legacy `x:*` suffix, not a ` :*` argument pattern
    return out


def _sample(cmd):
    return cmd[:-2] + " x" if cmd.endswith(" *") else cmd


def _covers(rules, cmd):
    """Does any rule match a call of `cmd` (a pattern whose trailing ` *` stands for some argument)?"""
    for s in _specs(rules):
        rx = (re.escape(s[:-2]).replace(r"\*", ".*") + "( .*)?" if s.endswith(" *")
              else re.escape(s).replace(r"\*", ".*"))
        if re.fullmatch(rx, _sample(cmd)):
            return True
    return False


def _guard(cmd):
    """destructive_guard's reason when it blocks a call of `cmd`; a guard error counts as blocked (skip, don't guess)."""
    try:
        return destructive_guard.check(_sample(cmd)) or ""
    except Exception as e:  # noqa: BLE001
        return f"guard error: {e}"


def _domain_covered(have, d):
    return any(h.split(":")[0] in ("*", d) or (h.startswith("*.") and d.endswith(h.split(":")[0][1:])) for h in have)


def _path_covered(have, p):
    norm = lambda s: s.replace("$HOME", "~").rstrip("/")  # noqa: E731
    return any(p == norm(h) or p.startswith(norm(h) + "/") for h in have)


def analyze(repo, home=None, platform=None):
    """Return {"snippet": settings as a dict (only what is missing), "why": [str], "stay": [str], "notes": [str]}.

    `platform` (default sys.platform) decides the macOS-only advice (allowLocalBinding, git over SSH). A repo with
    no scripts still gets the baseline (sandbox on, no unsandboxed retry, the deny rules) when settings lack it.
    Side effects: reads files and runs `git config` only.
    """
    repo, home, mac = Path(repo), Path(home) if home else Path.home(), (platform or sys.platform) == "darwin"
    us = _units(repo)
    edges = _edges(us)
    _spread(us, edges)
    eff, remote = _effective(repo, home), _remote(repo)
    allow, exclude, writes, domains = set(), set(), set(), set()
    why, stay, ship, binding = [], [], set(), False  # why: (entries it explains or (), text)

    for u in us:
        bad = sorted(k for k in u.hits if RISKS[k][2] == "exclude")
        if "port" in u.hits and not binding:  # one line is enough: the setting is global
            why.append((("allowLocalBinding",), f"allowLocalBinding: {u.hits['port'][0]}: {RISKS['port'][1]} ({u.hits['port'][1]})"))
        binding |= "port" in u.hits
        why += [((), f"{u.label}: {RISKS[k][1]} ({u.hits[k][1]})") for k in sorted(u.hits) if RISKS[k][2] == "note"]
        if bad and u.entries:
            exclude |= set(u.entries)
            for k in bad:
                origin, line = u.hits[k]
                tail = " (git runs this hook, so the whole git call leaves the sandbox: broad)" if u.kind == "hook" else ""
                why.append((tuple(u.entries), f"exclude {' and '.join(repr(e) for e in u.entries)}: {RISKS[k][1]} "
                                              f"[{origin}: {line}]{tail}"))
        base = "" if u.kind == "hook" else u.name
        body = _body(u, edges) if u.entries else []
        if u.entries and u.kind != "hook" and (SHIP.search(base) or any(SHIP.search(ln) for ln in body)):
            ship |= set(u.entries)
        elif u.entries and not bad and (GATE.match(base) or BUILD.match(base)):
            allow |= set(u.entries)
        for path, origin in sorted(u.writes):
            if path.startswith("../"):
                stay.append(f"{origin} writes {path}: another directory or repo; never granted")
            elif any(s in path for s in SENSITIVE):
                stay.append(f"{origin} writes {path}: credential or shell-config path; never advised")
            else:
                writes.add(path)
                why.append(((path,), f"allowWrite {path!r}: {origin} writes outside the repo, which the sandbox blocks"))

    fam = {}  # many gate scripts: one prefix rule per (interpreter, dir, leading word) instead of a long list
    for u in us:
        if u.kind == "script" and u.entries and u.entries[0] in allow and GATE.match(u.name):
            fam.setdefault((u.entries[0].split()[0], u.label.rsplit("/", 1)[0], GATE.match(u.name).group(1).lower()), []).append(u)
    for (interp, d, word), group in fam.items():
        # a prefix rule also matches every sibling it names, so it needs each file under the prefix to be vetted
        siblings = [u for u in us if u.kind == "script" and u.label.startswith(f"{d}/{word}")]
        if len(group) >= 4 and ".." not in d + word and len(siblings) == len(group):
            allow = (allow - {e for u in group for e in u.entries}) | {f"{interp} {d}/{word}*"}
            why.append(((f"{interp} {d}/{word}*",), f"allow '{interp} {d}/{word}*': {len(group)} gate scripts share the "
                                                    "prefix, so the rule is broader than each file"))

    py = any((repo / f).exists() for f in ("pyproject.toml", "setup.py", "setup.cfg", "tox.ini", "Pipfile", "noxfile.py",
                                          "pytest.ini")) or any(repo.glob("requirements*.txt"))
    if remote:
        name, host, ssh = remote
        allow |= {f"git push {name} HEAD", f"git push -u {name} HEAD"}
        domains.add(host)
        if host == "github.com":
            domains.add("api.github.com")
            exclude.add("gh *")
            why.append((("gh *",), f"exclude 'gh *': {RISKS['gh'][1]}; this repo's remote is on github.com, so the PR flow uses gh"))
        if ssh and mac:
            exclude |= {"git push *", "git fetch *", "git pull *"}
            why.append((("git push *", "git fetch *", "git pull *"),
                        "exclude git push/fetch/pull: on macOS git over SSH fails inside the sandbox even to an allowed host; "
                        f"the other fix is an HTTPS remote: git remote set-url {name} https://{host}/<owner>/<repo>.git"))
    flows = "\n".join("\n".join(u.lines) for u in us)
    if (repo / "package.json").exists() and (re.search(r"\b(?:npm|pnpm|yarn|bun)\s+(?:ci|install|i|add)\b", flows)
                                              or not (repo / "node_modules").is_dir()):
        domains.add("registry.npmjs.org")
    if py and (re.search(r"\b(?:pip3?|uv|poetry|pipenv|tox|nox)\b", flows)
               or not any((repo / v).is_dir() for v in (".venv", "venv"))):
        domains |= {"pypi.org", "files.pythonhosted.org"}
    if binding and not mac:
        why.append(((), "local port: Linux/WSL2 needs no setting for a server and client inside one command; a command "
                        "that must reach a server started outside the sandbox has to be excluded"))
    if ship:
        stay.append("release or deploy commands found here need your approval and are not allow-listed: " + ", ".join(sorted(ship)))

    keep, notes = [], []
    for a in sorted(allow):
        r = _guard(a)
        if r:
            stay.append(f"{a}: not allow-listed, destructive_guard.py blocks it ({r})")
        elif _covers(eff["deny"] + eff["ask"], a):
            stay.append(f"{a}: not advised, your own deny or ask rule overrides any allow")
        elif not _covers(eff["allow"], a):
            keep.append(a)
    if keep and not eff["enabled"]:
        keep = []
        notes.append("Allow rules withheld: the sandbox is not enabled in the settings that apply. Enable it first "
                     "(sandbox.enabled above), then run this again for the allow rules.")
    elif keep:
        notes.append("Disclosure: these allow rules run repo-controlled code (a test runner executes conftest, config files "
                     "and build scripts, and no static check can make that safe); they are safe only with the sandbox "
                     "enabled, which confines writes to the repo and the network to the allowlist.")
    sb, net = {}, {}
    if not eff["enabled"]:
        sb["enabled"] = True
    if eff["retry"] is not False:
        sb["allowUnsandboxedCommands"] = False
    ex = [e for e in sorted(exclude) if not _covers(eff["exclude"], e)]
    if ex:
        sb["excludedCommands"] = ex
    stay += [f"{e}: your existing allow rule also covers it, so it will run outside the sandbox with no prompt"
             for e in sorted(exclude) if _covers(eff["allow"], e)]
    dm = [d for d in sorted(domains) if not _domain_covered(eff["domains"], d)]
    if dm:
        net["allowedDomains"] = dm
    if binding and mac and not eff["binding"]:
        net["allowLocalBinding"] = True
    if net:
        sb["network"] = net
    wr = [w for w in sorted(writes) if not _path_covered(eff["write"], w)]
    if wr:
        sb["filesystem"] = {"allowWrite": wr}
    perm = {}
    if keep:
        perm["allow"] = [f"Bash({a})" for a in keep]
    ak = [f"Bash({a})" for a in ASK + tuple(sorted(ship)) if not _covers(eff["ask"] + eff["deny"], a)]
    if ak:
        perm["ask"] = ak
    dn = [f"Bash({d})" for d in DENY if not _covers(eff["deny"], d)]
    if dn:
        perm["deny"] = dn
    shown = set(ex) | set(wr) | set(keep) | ({"allowLocalBinding"} if net.get("allowLocalBinding") else set())
    return {"snippet": {k: v for k, v in (("permissions", perm), ("sandbox", sb)) if v},
            "why": [t for ents, t in why if not ents or shown & set(ents)], "stay": stay, "notes": notes}


def advise(repo, home=None, platform=None):
    """The "To run autonomously, add:" section; a one-line all-clear when the settings already cover the repo."""
    r = analyze(repo, home, platform)
    if not r["snippet"]:
        return "To run autonomously: nothing to add; your settings already cover this repo's gate, build and push commands."
    out = ["To run autonomously, add (advice only: nothing is written; you apply what you choose):",
           "Merge this into .claude/settings.local.json (untracked, yours) or ~/.claude/settings.json (every project):",
           json.dumps(r["snippet"], indent=2)]
    out += r["notes"]
    if r["why"]:
        out.append("Why (a text scan of package.json, Makefile, git hooks and scripts: a lead, not a verdict):")
        out += [f"  - {w}" for w in r["why"]]
    out.append('In a session, /sandbox exclude "<pattern>" excludes one pattern (named by Claude Code\'s own sandbox error '
               "text; the docs pages checked on 2026-10-16 show only the sandbox.excludedCommands setting).")
    out.append("Stays blocked or asks you, on purpose:")
    out += [f"  - {s}" for s in STAY + tuple(r["stay"])]
    out.append("Per host:")
    out += [f"  - {h}" for h in HOSTS]
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--home", default=str(Path.home()))
    a = ap.parse_args(argv)
    print(advise(Path(a.repo).resolve(), Path(a.home)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
