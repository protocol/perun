#!/usr/bin/env python3
"""Profile a delivery pipeline: map suites to stages, measure, rank bottlenecks, price each fix, verify the speed-up.

WHY THIS EXISTS (the failure it closes)
---------------------------------------
A coordinator spent weeks tuning single stages (faster runners, parallel test workers, affected-test selection).
Every stage got faster and the pipeline stayed slow, because the same suites still ran at commit, at push, in a
pre-PR check, in CI and at the merge gate. Nobody had drawn the suite x stage map, so nobody saw the duplicates, and
"never weaken a gate" was read as "never move a check". Another engineer fixed it in a day: commit and push hooks run
quick checks only, the full suites run ONCE at the merge gate, which still blocks red. This script makes that order
mechanical: map first, measure second, price third, verify last (`references/pipeline-optimizer.md`).

COMMANDS
--------
  map      Step 1, MANDATORY. Suite x stage map (commit, push, precheck, ci, train) read from hooks, workflows and
           docs. Flags every suite that runs at more than one stage and names the latest blocking gate to keep.
  time     Record one local timing (wall + cpu): `time --stage push --name hook:pre-push -- CMD ARGS`.
  hooks    List the commit/push hooks; with --run, execute each against HEAD and record its real wall time.
  suites   Time each duplicated suite once at the local stages that would be dropped (dry list without --run).
  profile  Measure: per-stage wall time on the critical path, CI job/step times, queue wait, push-to-merge lead
           time, reruns and flakes, duplicated suites (in seconds), cache hit rate. Ranked bottleneck table.
  fixes    Price the fix catalogue from a profile; each saving is computed from measured numbers. Duplicate
           removal always ranks first when it saves anything.
  compare  BEFORE.json AFTER.json: measured delta and a KEEP / REVERT / UNVERIFIED verdict for one change;
           KEEP also needs lead time and merge rate not to regress (`--stage-only` skips that).

DATA SOURCES (stdlib only)
--------------------------
GitHub REST (`/actions/runs`, `/actions/runs/{id}/jobs`, `/pulls`): public repos work unauthenticated until the
rate limit (60 requests/hour per IP) runs out; set GH_TOKEN or GITHUB_TOKEN to lift it. The token is read from
those two variables only and never forwarded across a redirect. `--data FILE` is a read-write bundle: responses
already in it are reused, so a rate-limited run resumes instead of restarting, and the analysis can be re-run
offline. A missing input is reported as `n/a` / `unverified`, never filled with a guess. Local timings come from
`time`, `hooks --run` and `suites --run` (TSV at `<git-common-dir>/pipeline-timings.tsv`, or `--log FILE`).

Exit codes: 0 ok (compare: KEEP), 1 compare REVERT, 2 usage, unreadable input or UNVERIFIED verdict.
Side effects: `time` appends to the timings TSV; `hooks --run` executes the repo's own hooks; `profile --data` and
`--json` write the named files; nothing else is written. Pure analysis functions take plain dicts (see the tests).
"""
from __future__ import annotations

import argparse
import datetime
import gzip
import http.client
import json
import os
import posixpath
import re
import resource
import shlex
import statistics
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

STAGES = ("commit", "push", "precheck", "ci", "train")
BLOCKING = ("ci", "train")  # server-enforced; hooks and manual prechecks are bypassable self-report
API = "https://api.github.com"
NOISE_FLOOR_S = 1.0  # a saving below this (and below 1% of the per-PR time) is not a lever
MIN_GAIN = 0.05  # compare: KEEP needs the target to drop by more than this fraction (and NOISE_FLOOR_S)


# --------------------------------------------------------------------------- small helpers
def ts(s):
    """GitHub ISO-8601 ('...Z') -> epoch seconds, or None when absent/unparseable."""
    if not s:
        return None
    try:
        return datetime.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def span(a, b):
    """Seconds between two ISO timestamps (never negative), or None if either is missing."""
    x, y = ts(a), ts(b)
    return None if x is None or y is None else max(0.0, y - x)


def med(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def p90(xs):
    xs = sorted(x for x in xs if x is not None)
    return xs[min(len(xs) - 1, int(0.9 * len(xs)))] if xs else None


def fmt(s):
    """Seconds -> '12.3s' / '4m05s' / '1h02m'; None -> 'n/a'."""
    if s is None:
        return "n/a"
    if s < 60:
        return "%.1fs" % s
    if s < 3600:
        return "%dm%02ds" % (s // 60, s % 60)
    return "%dh%02dm" % (s // 3600, (s % 3600) // 60)


def git(root, *args):
    p = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True)
    return p.stdout if p.returncode == 0 else ""


def die(msg):
    """Usage or unreadable-input error: message on stderr, exit 2."""
    print(msg, file=sys.stderr)
    sys.exit(2)


def read(path):
    """Text of a file, or '' when unreadable (a missing hook or doc is simply absent)."""
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return ""


def load_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def save_json(path, obj):
    """Write `obj` as JSON through a temp file in the same directory, then os.replace: a crash or a TypeError
    mid-dump leaves the old file whole (a resumable bundle must never be truncated)."""
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", suffix=".tmp", dir=os.path.dirname(path) or ".")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(obj, fh, indent=1)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# --------------------------------------------------------------------------- command -> suite key
_ENV = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
_INTERP = {"bash", "sh", "zsh", "python", "python3", "node", "ruby", "perl", "deno", "bun"}
_WRAP = {"env", "time", "nohup", "exec", "sudo", "command", "xvfb-run", "if", "then", "else", "elif", "do",
         "while", "until", "!", "{"}
_IGNORE_HEAD = {"echo", "printf", "grep", "egrep", "fgrep", "cat", "sed", "awk", "git", "gh", "curl", "wget", "rm",
                "cp", "mv", "mkdir", "ls", "cd", "test", "[", "[[", "export", "set", "unset", "local", "readonly",
                "declare", "trap", "source", ".", "exit", "return", "true", "false", ":", "sleep", "wait", "tee",
                "head", "tail", "wc", "sort", "find", "xargs", "tr", "cut", "date", "touch", "chmod"}
_RUN = {"pytest", "ruff", "mypy", "pyright", "flake8", "pylint", "black", "isort", "eslint", "tsc", "prettier",
        "jest", "vitest", "playwright", "cypress", "rspec", "shellcheck", "hadolint", "golangci-lint", "bandit",
        "semgrep", "pre-commit", "phpunit", "phpstan", "stylelint", "biome"}
_PKG = {"npm", "pnpm", "yarn", "bun", "make", "cargo", "go", "mvn", "gradle", "bundle", "tox", "nox", "dotnet", "rake"}
_UNWRAP = {("uv", "run"), ("poetry", "run"), ("pipenv", "run"), ("pnpm", "exec"), ("yarn", "exec"), ("pipx", "run")}
_UNWRAP1 = {"npx", "bunx", "pnpx"}
_SETUP = {"install", "ci", "add", "sync", "download", "get", "mod", "fetch", "update", "upgrade", "i", "prune",
          "cache", "init", "config", "version", "help", "login"}
_SUB = re.compile(r"^[a-z][a-z0-9_-]{1,24}$")
_EXT = (".sh", ".bash", ".py", ".js", ".mjs", ".ts", ".rb", ".pl")
_OPS = {"&&", "||", ";", ";;", "|", "&", "(", ")"}


def _lex(line):
    try:
        lx = shlex.shlex(line, posix=True, punctuation_chars=True)
        lx.whitespace_split = True
        lx.commenters = "#"
        return list(lx)
    except ValueError:  # unbalanced quote: fall back to whitespace split
        return line.split()


def _script_key(script, rest, syntax_only=False):
    """Normalised key of one script invocation; None for a dynamic or non-path operand."""
    if any(c in script for c in "${`"):
        return None
    if "/" not in script and not script.endswith(_EXT):
        return None
    key = posixpath.normpath(script)
    if syntax_only:
        key = "syntax-check " + key
    if "--selftest" in rest:
        return key + " --selftest"
    if rest and not rest[0].startswith("-") and _SUB.match(rest[0]):
        return key + " " + rest[0]
    return key


def suite_key(t):
    """Tokens of one simple command -> ('key', k) | ('inline', script) | None (plumbing, setup or dynamic).

    The key is `<script path> [subcommand|--selftest]` or `<runner> [subcommand]`, so the same check run at two
    stages with different arguments (a base ref, a path) still maps to one suite."""
    i = 0
    while i < len(t) and (_ENV.match(t[i]) or t[i] in _WRAP):
        i += 1
    t = t[i:]
    while t:  # `uv run pytest`, `npx eslint`: the wrapped tool is the suite
        h = posixpath.basename(t[0])
        if h in _UNWRAP1:
            t = t[1:]
        elif len(t) > 1 and (h, t[1]) in _UNWRAP:
            t = t[2:]
        else:
            break
    if not t:
        return None
    head = posixpath.basename(t[0])
    if head in _IGNORE_HEAD:
        return None
    for j, w in enumerate(t):
        if posixpath.basename(w) not in _INTERP:
            continue
        k, syntax = j + 1, False
        while k < len(t) and t[k].startswith("-"):
            if t[k] == "-c":
                return ("inline", t[k + 1]) if k + 1 < len(t) else None
            if t[k] == "-m":
                mod = t[k + 1] if k + 1 < len(t) else ""
                return ("key", mod) if mod and mod not in ("pip", "venv", "ensurepip") else None
            syntax = syntax or t[k] == "-n"
            k += 1
        key = _script_key(t[k], t[k + 1:], syntax) if k < len(t) else None
        return ("key", key) if key else None
    if head in _RUN:
        if head == "pre-commit" and len(t) > 1 and t[1] in ("install", "uninstall", "autoupdate", "clean", "gc"):
            return None
        return ("key", head)
    if head in _PKG:
        args = [a for a in t[1:] if not a.startswith("-")]
        sub = args[0] if args else ""
        if sub in _SETUP:
            return None
        if head in ("npm", "pnpm", "yarn", "bun") and sub == "run" and len(args) > 1:
            return ("key", "%s run %s" % (head, args[1]))
        return ("key", ("%s %s" % (head, sub)).strip())
    if "/" in t[0] and (t[0].endswith(_EXT) or t[0].startswith("./")):
        key = _script_key(t[0], t[1:])
        return ("key", key) if key else None
    return None


def logical_lines(text):
    """Shell/doc text -> logical command lines: continuations joined, comments and heredoc bodies dropped."""
    out, buf, tag = [], "", None
    for raw in text.splitlines():
        if tag is not None:
            if raw.strip() == tag:
                tag = None
            continue
        line = raw.rstrip()
        if buf:
            line, buf = buf + " " + line.lstrip(), ""
        if line.endswith("\\"):
            buf = line[:-1]
            continue
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        m = re.search(r"(?<!<)<<(?!<)-?\s*['\"]?([A-Za-z_][A-Za-z0-9_]*)['\"]?", s)
        if m:
            tag = m.group(1)
        out.append(s)
    return out


def _strip_redirects(p):
    """Drop `> file`, `>> file`, `2>&1`, `< file` from one simple command so its text can be replayed as-is."""
    out, i = [], 0
    while i < len(p):
        if re.fullmatch(r"\d*[<>]+&?", p[i]):
            i += 2
        elif re.fullmatch(r"[012]", p[i]) and i + 1 < len(p) and re.fullmatch(r"[<>]+&?", p[i + 1]):
            i += 3
        else:
            out.append(p[i])
            i += 1
    return out


def commands(text, hook_dir=None, depth=0):
    """Extract (command text, suite key, blocking) triples from shell text. `|| true` marks a warn-only command."""
    found = []
    for line in logical_lines(text):
        if hook_dir is not None:
            line = re.sub(r'\$\(dirname\s+"?\$0"?\)|\$\{0%/\*\}', hook_dir, line)
        parts, cur = [], []
        for tok in _lex(line):
            if tok in _OPS:
                parts.append(cur)
                cur = []
            else:
                cur.append(tok)
        parts.append(cur)
        warn_only = bool(re.search(r"\|\|\s*(true|:)\s*$", line))
        for p in parts:
            p = _strip_redirects(p)
            r = suite_key(p) if p else None
            if r is None:
                continue
            if r[0] == "inline":
                if depth < 1:
                    found += commands(r[1], hook_dir, depth + 1)
                continue
            found.append((shlex.join(p), r[1], not warn_only))
    return found


# --------------------------------------------------------------------------- workflow reader
def _unq(v):
    v = v.strip()
    if v[:1] in "\"'":
        q = v[0]
        end = v.find(q, 1)
        return v[1:end] if end > 0 else v[1:]
    return re.sub(r"\s+#.*$", "", v)


def _ind(s):
    return len(s) - len(s.lstrip(" "))


def _step(block):
    """One `- ...` step (list of raw lines) -> {name, uses, run, if, coe}. coe = continue-on-error."""
    first = re.sub(r"^(\s*)- ", lambda m: m.group(1) + "  ", block[0], count=1)
    lines = [first] + block[1:]
    base = _ind(first)
    step = {"name": None, "uses": None, "run": None, "if": None, "coe": False}
    i = 0
    while i < len(lines):
        m = re.match(r"^(\s*)([A-Za-z0-9_-]+):\s*(.*)$", lines[i])
        if m and len(m.group(1)) == base:
            k, v = m.group(2), m.group(3)
            if k == "run" and re.match(r"^[|>][+-]?\s*(#.*)?$", v):
                j, body = i + 1, []
                while j < len(lines) and (not lines[j].strip() or _ind(lines[j]) > base):
                    body.append(lines[j])
                    j += 1
                pad = min((_ind(x) for x in body if x.strip()), default=0)
                step["run"] = "\n".join(x[pad:] for x in body)
                i = j
                continue
            if k == "run":
                step["run"] = _unq(v)
            elif k in ("name", "uses", "if"):
                step[k] = _unq(v)
            elif k == "continue-on-error":
                step["coe"] = _unq(v).lower() != "false"  # fail closed: an expression or any non-false value may not block
        i += 1
    return step


def parse_workflow(text):
    """GitHub Actions YAML subset (PyYAML is not stdlib) -> {on: set, jobs: {id: {name, if, steps}}}."""
    lines = text.splitlines()
    wf, n, i = {"on": set(), "on_keys": {}, "jobs": {}}, len(lines), 0
    while i < n:
        s = lines[i]
        if re.match(r"^['\"]?on['\"]?:", s):
            rest = re.sub(r"\s*#.*$", "", s.split(":", 1)[1]).strip()
            if rest:
                wf["on"] |= set(re.findall(r"[A-Za-z_]+", rest))
            else:
                j, base, ev = i + 1, None, None
                while j < n and (not lines[j].strip() or _ind(lines[j]) > 0):
                    t = lines[j]
                    if t.strip() and not t.lstrip().startswith("#"):
                        base = _ind(t) if base is None else base
                        km = re.match(r"\s*(?:-\s+)?([A-Za-z_]+)", t)
                        if _ind(t) == base and km:
                            ev = km.group(1)
                            wf["on"].add(ev)
                        elif km and ev:
                            wf["on_keys"].setdefault(ev, set()).add(km.group(1))
                    j += 1
                i = j - 1
        elif s.startswith("jobs:"):
            j, jind, cur = i + 1, None, None
            while j < n and (not lines[j].strip() or lines[j].lstrip().startswith("#") or _ind(lines[j]) > 0):
                t = lines[j]
                if t.strip() and not t.lstrip().startswith("#"):
                    jind = _ind(t) if jind is None else jind
                    m = re.match(r"^\s*([A-Za-z0-9_-]+):\s*$", t)
                    if _ind(t) == jind and m:
                        cur = wf["jobs"].setdefault(m.group(1), {"name": m.group(1), "if": None, "coe": False, "steps": []})
                    elif cur is not None and _ind(t) == jind + 2:
                        m = re.match(r"^\s*(name|if|continue-on-error):\s*(.*)$", t)
                        if m and m.group(1) == "continue-on-error":
                            cur["coe"] = _unq(m.group(2)).lower() != "false"  # fail closed, as for a step
                        elif m:
                            cur[m.group(1)] = _unq(m.group(2))
                        elif re.match(r"^\s*steps:\s*$", t):
                            k, sind, blocks = j + 1, None, []
                            while k < n and (not lines[k].strip() or lines[k].lstrip().startswith("#")
                                             or _ind(lines[k]) > jind + 2):
                                u = lines[k]
                                if u.strip() and not u.lstrip().startswith("#"):
                                    sind = _ind(u) if sind is None else sind
                                    if _ind(u) == sind and u.lstrip().startswith("- "):
                                        blocks.append([u])
                                    elif blocks:
                                        blocks[-1].append(u)
                                elif blocks:
                                    blocks[-1].append(u)
                                k += 1
                            cur["steps"] = [_step(b) for b in blocks]
                            j = k - 1
                j += 1
            i = j - 1
        i += 1
    return wf


def step_label(st):
    """The name GitHub reports for a step in the jobs API (named steps keep their name)."""
    if st.get("name"):
        return st["name"]
    if st.get("uses"):
        return "Run " + st["uses"]
    first = (st.get("run") or "").strip().splitlines()
    return "Run " + first[0].strip() if first else ""


# --------------------------------------------------------------------------- suite x stage map
def _hook_files(root):
    """Hook scripts in `core.hooksPath`, .githooks, .husky and .git/hooks (samples skipped) -> {stage: [path]}."""
    dirs = []
    for cfg in (git(root, "config", "core.hooksPath").strip(), git(root, "rev-parse", "--git-path", "hooks").strip()):
        if cfg:  # the second is the real hooks dir even inside a linked worktree
            dirs.append(cfg if os.path.isabs(cfg) else os.path.join(root, cfg))
    dirs += [os.path.join(root, ".githooks"), os.path.join(root, ".husky")]
    out = {"commit": [], "push": []}
    for d in dirs:
        for stage, name in (("commit", "pre-commit"), ("push", "pre-push")):
            p = os.path.join(d, name)
            if os.path.isfile(p) and p not in out[stage]:
                out[stage].append(p)
    return out


def _hook_refs(root, path, text):
    """In-repo shell/python scripts a hook names (a path relative to the hook or to the repo root)."""
    refs = []
    for m in re.finditer(r"[\w./-]+\.(?:sh|bash|py)", " ".join(logical_lines(text))):
        for base in (os.path.dirname(path), root):
            cand = os.path.normpath(os.path.join(base, m.group(0).lstrip("/")))
            if os.path.isfile(cand) and cand != path and cand not in refs:
                refs.append(cand)
                break
    return refs


def _hook_commands(root, path):
    """Commands a hook runs. A thin hook (<= 7 command lines) that names one in-repo script IS that script."""
    text = read(path)
    found = commands(text, hook_dir=os.path.relpath(os.path.dirname(path), root))
    refs = _hook_refs(root, path, text)
    if len(logical_lines(text)) <= 7 and len(refs) == 1:
        wrapper = posixpath.normpath(os.path.relpath(refs[0], root))
        inner = commands(read(refs[0]), hook_dir=os.path.relpath(os.path.dirname(refs[0]), root))
        return [c for c in found if c[1] != wrapper] + inner
    return found


def _doc_commands(root):
    """Fenced shell blocks under a pre-commit / before-you-open-a-PR style heading -> [(stage, cmds)]."""
    out = []
    for name in ("CONTRIBUTING.md", "README.md", "AGENTS.md", "CLAUDE.md"):
        p = os.path.join(root, name)
        if not os.path.isfile(p):
            continue
        heading, fence, buf = "", False, []
        for ln in read(p).splitlines():
            if ln.lstrip().startswith("```"):
                if fence and buf:
                    h = heading.lower()
                    stage = ("commit" if re.search(r"pre-?commit|before (every|each) commit", h) else
                             "precheck" if re.search(r"before you (open|push|submit)|before (opening|pushing|submitting)"
                                                     r"|pre-?push|pre-?merge|precheck|pre-?pr\b", h) else None)
                    if stage:
                        out.append((stage, name, commands("\n".join(buf))))
                fence, buf = not fence, []
            elif fence:
                buf.append(ln)
            elif ln.startswith("#"):
                heading = ln.lstrip("# ").strip()
    return out


_EVENT_IF = re.compile(r"^github\.event_name\s*(==|!=)\s*'(merge_group|pull_request)'$")


def _wf_stage(wf, st, job):
    """-> (stages, enforced). Stages: 'ci' on PR/push events, 'train' on merge_group. `enforced` is True only when the
    step provably gates a PR or the merge group: a push-only workflow never does, and an `if:` we do not recognise
    (anything but none, success(), always() or an event_name test against merge_group / pull_request) may skip the
    step, so it counts as not enforced. Fail closed: an unproven gate is never a reason to drop a local check."""
    ev = set(wf["on"])
    pk = wf.get("on_keys", {}).get("push", set())
    if "tags" in pk and "branches" not in pk:  # a tag-push workflow is a release, not a merge gate
        ev.discard("push")
    stages = []
    if ev & {"pull_request", "pull_request_target", "push"}:
        stages.append("ci")
    if "merge_group" in ev:
        stages.append("train")
    enforced = bool(ev & {"pull_request", "pull_request_target", "merge_group"})
    for cond in (job.get("if"), st.get("if")):
        if not cond:
            continue
        c = re.sub(r"^\$\{\{\s*|\s*\}\}$", "", cond.strip())
        m = _EVENT_IF.match(c)
        if m and m.group(2) == "merge_group":
            stages = [s for s in stages if (s == "train") == (m.group(1) == "==")]
        elif m:  # == 'pull_request' (!= is not a recognised form)
            if m.group(1) == "==":
                stages = [s for s in stages if s == "ci"]
            else:
                enforced = False
        elif c not in ("success()", "always()"):
            enforced = False
    return stages, enforced


def stage_map(root, extra=None):
    """Build the suite x stage map. Returns {entries, suites, duplicates}.

    `extra` = {stage: [command, ...]} declares stages that cannot be read from files (a merge-train verify
    command, a project-specific precheck)."""
    entries = []

    def add(stage, src, cmds, step=None, blocking=True):
        for text, key, blk in cmds:
            entries.append({"stage": stage, "key": key, "cmd": text, "source": src, "step": step,
                            "blocking": blk and blocking})

    wfs = []
    wdir = os.path.join(root, ".github", "workflows")
    for fn in sorted(os.listdir(wdir)) if os.path.isdir(wdir) else []:
        if fn.endswith((".yml", ".yaml")):
            wf = parse_workflow(read(os.path.join(wdir, fn)))
            wfs.append((fn, wf))
            for job in wf["jobs"].values():
                for st in job["steps"]:
                    if not st["run"]:
                        continue
                    stages, enforced = _wf_stage(wf, st, job)
                    for stage in stages:
                        add(stage, ".github/workflows/" + fn, commands(st["run"]), step_label(st),
                            enforced and not st["coe"] and not job["coe"])
    step_names = {step_label(st): st for _, wf in wfs for job in wf["jobs"].values() for st in job["steps"]}
    for stage, paths in _hook_files(root).items():
        for p in paths:
            rel = os.path.relpath(p, root)
            add(stage, rel, _hook_commands(root, p))
            text = read(p) + "".join(read(q) for q in _hook_refs(root, p, read(p)))
            for name, st in step_names.items():  # a hook that quotes a CI step's name runs that step
                if len(name) >= 8 and ('"%s"' % name) in text and st["run"]:
                    add(stage, rel + " (runs CI step)", commands(st["run"]), name, not st["coe"])  # a local hook is bypassable: never a server gate
    for stage, src, cmds in _doc_commands(root):
        add(stage, src, cmds)
    for stage, cmds in (extra or {}).items():
        add(stage, "declared", commands("\n".join(cmds)))
    suites = {}
    for e in entries:
        s = suites.setdefault(e["key"], {"key": e["key"], "stages": [], "entries": []})
        if e["stage"] not in s["stages"]:
            s["stages"].append(e["stage"])
        s["entries"].append(e)
    dups = []
    for s in suites.values():
        s["stages"].sort(key=STAGES.index)
        if len(s["stages"]) < 2:
            continue
        blocking = [x for x in s["stages"] if any(e["stage"] == x and e["blocking"] for e in s["entries"])]
        server = [x for x in blocking if x in BLOCKING]
        keep = server[-1] if server else None  # no proven server gate: keep every run, advise dropping none
        dups.append({"key": s["key"], "stages": s["stages"], "keep": keep,
                     "drop": [x for x in s["stages"] if x != keep] if keep else [],
                     "enforced": bool(server), "blocking_stages": blocking})
    return {"entries": entries, "suites": list(suites.values()), "duplicates": dups}


# --------------------------------------------------------------------------- local timings
def timings_path(root, override=None):
    if override or os.environ.get("PIPELINE_TIMINGS"):
        return override or os.environ["PIPELINE_TIMINGS"]
    common = git(root, "rev-parse", "--git-common-dir").strip()
    base = common if common and os.path.isabs(common) else os.path.join(root, common or ".")
    return os.path.join(base, "pipeline-timings.tsv")


def record_timing(path, stage, name, cmd, argv, shell=False, cwd=None, ok_rc=()):
    """Run `argv` (or `bash -c cmd` with shell), append one TSV row, return (rc, wall_s, cpu_s).

    A row counts toward medians only when its command succeeded (rc 0) or exited with a code in `ok_rc`: a suite
    with known environment failures still ran to completion, and its time is real, but say so when you report it."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.monotonic()
    rc = subprocess.run(["bash", "-c", cmd] if shell else argv, cwd=cwd).returncode
    wall = time.monotonic() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    cpu = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write("\t".join([datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), stage,
                            name.replace("\t", " "), "%.3f" % wall, "%.3f" % cpu, str(rc),
                            cmd.replace("\t", " ").replace("\n", " "), "1" if rc == 0 or rc in ok_rc else "0"]) + "\n")
    return rc, wall, cpu


def load_timings(path):
    """TSV -> rows [{stage, name, key, wall, cpu, rc, ok}]. Rows that failed (ok false) are kept, not used for medians.
    A row written before the `ok` column existed is ok when its rc is 0."""
    rows = []
    for ln in read(path).splitlines():
        c = ln.split("\t")
        if len(c) < 7 or c[1] not in STAGES:
            continue
        try:
            wall, cpu, rc = float(c[3]), float(c[4]), int(c[5])
        except ValueError:
            continue
        found = commands(c[6])
        rows.append({"stage": c[1], "name": c[2], "key": found[0][1] if found else None, "wall": wall, "cpu": cpu,
                     "rc": rc, "ok": (c[7] == "1") if len(c) > 7 else rc == 0})
    return rows


def local_summary(rows):
    """Median wall/cpu per (stage, name) over passing runs, and the per-stage hook total."""
    groups = {}
    for r in rows:
        if r["ok"]:
            groups.setdefault((r["stage"], r["name"], r["key"]), []).append(r)
    out = [{"stage": s, "name": n, "key": k, "n": len(v), "wall_median_s": med([x["wall"] for x in v]),
            "cpu_median_s": med([x["cpu"] for x in v])} for (s, n, k), v in sorted(groups.items())]
    stage_s, by_name = {}, {}
    for o in out:
        if o["name"].startswith("hook:"):
            stage_s[o["stage"]] = o["wall_median_s"]
        by_name[o["name"]] = o["wall_median_s"]  # `compare --metric local.by_name.<name>` reads one timed command
    return {"rows": out, "stage_s": stage_s, "by_name": by_name}


# --------------------------------------------------------------------------- GitHub REST (read-only)
class RateLimited(Exception):
    """Raised when the API says the rate limit is exhausted; .reset is the epoch second it refills."""

    def __init__(self, reset):
        super().__init__("rate limited until %s" % reset)
        self.reset = reset


def api_get(path, token=None, params=None, opener=None):
    """GET one REST page -> parsed JSON. The token is added as an unredirected header (never sent to a redirect).

    gzip is requested because a proxy that cuts long bodies leaves a compressed one whole; a short read is retried
    once (each request counts against the rate limit), then raised as ValueError."""
    url = API + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json", "Accept-Encoding": "gzip",
                                               "User-Agent": "perun-pipeline-profile"})
    if token:
        req.add_unredirected_header("Authorization", "Bearer " + token)
    for attempt in (1, 2):
        try:
            with (opener or urllib.request.urlopen)(req, timeout=30) as r:
                raw = r.read()
                if (getattr(r, "headers", None) or {}).get("Content-Encoding") == "gzip":
                    raw = gzip.decompress(raw)
                return json.loads(raw)
        except urllib.error.HTTPError as e:
            limited = e.code in (403, 429) and e.headers.get("x-ratelimit-remaining") == "0"
            reset = int(e.headers.get("x-ratelimit-reset") or 0)
            e.close()
            if limited:
                raise RateLimited(reset)
            raise
        except (http.client.IncompleteRead, EOFError, zlib.error, gzip.BadGzipFile) as e:
            if attempt == 2:
                raise ValueError("response cut short twice (%s)" % type(e).__name__) from e


def _run_row(r):
    return {k: r.get(k) for k in ("id", "name", "event", "head_branch", "head_sha", "run_attempt", "run_started_at",
                                  "created_at", "updated_at", "conclusion", "status")} | {
        "prs": [p.get("number") for p in r.get("pull_requests") or []],
        "msg": ((r.get("head_commit") or {}).get("message") or "").split("\n")[0]}


def _job_row(j):
    return {"id": j.get("id"), "name": j.get("name"), "conclusion": j.get("conclusion"),
            "created_at": j.get("created_at"), "started_at": j.get("started_at"),
            "completed_at": j.get("completed_at"),
            "steps": [{k: s.get(k) for k in ("name", "number", "conclusion", "started_at", "completed_at")}
                      for s in j.get("steps") or []]}


def fetch_bundle(repo, bundle, n_runs, workflow=None, token=None, opener=None):
    """Fill `bundle` {runs, jobs, pulls, limits} from the API, reusing what is already there. Stops at the rate
    limit and records it in bundle['limits'] instead of failing."""
    bundle.setdefault("runs", [])
    bundle.setdefault("jobs", {})
    bundle.setdefault("pulls", [])
    bundle["limits"] = []
    base = "/repos/%s" % repo
    try:
        if len(bundle["runs"]) < n_runs:
            path = base + ("/actions/workflows/%s/runs" % workflow if workflow else "/actions/runs")
            got = api_get(path, token, {"per_page": min(n_runs, 100), "status": "completed",
                                        "event": "pull_request"}, opener)
            bundle["runs"] = [_run_row(r) for r in got.get("workflow_runs", [])][:n_runs]
        for r in bundle["runs"]:
            if str(r["id"]) not in bundle["jobs"]:
                got = api_get("%s/actions/runs/%s/jobs" % (base, r["id"]), token,
                              {"per_page": 100, "filter": "latest"}, opener)
                bundle["jobs"][str(r["id"])] = [_job_row(j) for j in got.get("jobs", [])]
        for page in (1, 2, 3):  # a PR object is ~17 KB: keep pages small enough for a proxy that cuts long bodies
            if len(bundle["pulls"]) >= n_runs or bundle.get("pulls_pages", 0) >= page:
                continue
            got = api_get(base + "/pulls", token, {"state": "closed", "per_page": 10, "page": page, "sort": "updated",
                                                   "direction": "desc"}, opener)
            bundle["pulls"] += [{"number": p["number"], "created_at": p.get("created_at"),
                                 "merged_at": p.get("merged_at"), "head_ref": (p.get("head") or {}).get("ref")}
                                for p in got if p.get("merged_at")]
            bundle["pulls_pages"] = page
    except RateLimited as e:
        bundle["limits"].append("GitHub API rate limit exhausted; refills at epoch %s. Re-run with the same --data "
                                "file to resume (set GH_TOKEN to lift the limit)." % e.reset)
    except (urllib.error.URLError, OSError, ValueError) as e:
        bundle["limits"].append("GitHub API unreachable or cut short: %s. Re-run with the same --data file to resume." % e)
    return bundle


# --------------------------------------------------------------------------- measurement (pure functions)
def _chain(jobs):
    """Critical chain of one run: the last-finishing job plus the job that finished just before each started."""
    done = [j for j in jobs if ts(j.get("started_at")) is not None and ts(j.get("completed_at")) is not None]
    if not done:
        return []
    cur = max(done, key=lambda j: ts(j["completed_at"]))
    chain = [cur]
    while True:
        prev = [j for j in done if j not in chain and ts(j["completed_at"]) <= ts(cur["started_at"]) + 2]
        if not prev:
            return chain[::-1]
        cur = max(prev, key=lambda j: ts(j["completed_at"]))
        chain.append(cur)


def ci_metrics(bundle):
    """Per-run wall (queue + exec), queue wait, critical-chain steps with median seconds, reruns, flakes, red-run
    step order for fail-fast pricing."""
    sampled, jobs_by = bundle.get("runs") or [], bundle.get("jobs") or {}
    runs = [r for r in sampled if r.get("conclusion") in ("success", "failure", "timed_out")]  # cancelled/skipped: noise
    walls, execs, queues, chains = [], [], [], []
    step_s, crit_jobs, per_run_steps = {}, {}, []
    for r in runs:
        jobs = jobs_by.get(str(r["id"])) or []
        chain = _chain(jobs)
        if not chain:
            continue
        created = min(ts(j.get("created_at")) or ts(j["started_at"]) for j in chain)
        t0, t1 = ts(chain[0]["started_at"]), ts(chain[-1]["completed_at"])
        execs.append(t1 - t0)
        walls.append(t1 - created)
        queues.append(sum(max(0.0, ts(j["started_at"]) - (ts(j.get("created_at")) or ts(j["started_at"])))
                          for j in chain))
        chains.append(len(chain))
        for j in chain:
            crit_jobs[j["name"]] = crit_jobs.get(j["name"], 0) + 1
            for s in j.get("steps") or []:
                d = span(s.get("started_at"), s.get("completed_at"))
                if d is not None and s.get("conclusion") != "skipped":
                    step_s.setdefault((j["name"], s["name"]), []).append(d)
        per_run_steps.append((r, chain))
    steps = [{"job": j, "name": n, "median_s": med(v), "n": len(v)} for (j, n), v in step_s.items()]
    steps.sort(key=lambda s: -(s["median_s"] or 0))
    completed = [r for r in runs if r.get("conclusion")]
    failed = [r for r in completed if r["conclusion"] in ("failure", "timed_out")]
    reruns = [r for r in completed if (r.get("run_attempt") or 1) > 1]
    flaky = [r for r in reruns if r["conclusion"] == "success"]
    exec_med = med(execs)
    waste = sum((exec_med or 0) * ((r.get("run_attempt") or 1) - 1) for r in reruns)
    return {
        "runs": len(sampled), "cancelled_or_skipped": len(sampled) - len(runs), "measured_runs": len(execs),
        "wall_s": {"median": med(walls), "p90": p90(walls)}, "exec_s": {"median": med(execs), "p90": p90(execs)},
        "queue_s": {"median": med(queues), "p90": p90(queues)},
        "critical_jobs": sorted(crit_jobs, key=lambda k: -crit_jobs[k]), "steps": steps,
        "flake": {"completed": len(completed), "failed": len(failed), "reruns": len(reruns),
                  "flake_suspects": len(flaky), "red_rate": (len(failed) / len(completed)) if completed else None,
                  "rerun_waste_s_per_run": (waste / len(completed)) if completed else None},
        "fail_fast": _fail_fast(per_run_steps, step_s, len(completed)),
    }


def _fail_fast(per_run_steps, step_s, n_completed):
    """Seconds saved per CI run if the job's steps ran cheapest-first (stop at the first red).

    For each red run: time spent up to and including the failing step in the actual order, minus the same in
    ascending-median order. Averaged over all completed runs (green runs save nothing)."""
    def dur(s):
        return span(s.get("started_at"), s.get("completed_at")) or 0.0

    saved = []
    for r, chain in per_run_steps:
        if r.get("conclusion") not in ("failure", "timed_out"):
            continue
        for j in chain:
            sts = [s for s in j.get("steps") or [] if s.get("conclusion") != "skipped"]
            bad = [s for s in sts if s.get("conclusion") == "failure"]
            work = [s for s in sts if not _SETUPISH.search(s["name"])]  # setup/teardown steps cannot move
            if not bad or bad[0] not in work:
                continue
            f = bad[0]
            cost = {s["name"]: med(step_s.get((j["name"], s["name"]), [])) or dur(s) for s in work}
            order = sorted(work, key=lambda s: cost[s["name"]])
            old = sum(dur(s) for s in sts if s["number"] <= f["number"])
            fixed = sum(dur(s) for s in sts if s["number"] <= f["number"] and s not in work)
            saved.append(max(0.0, old - fixed - sum(cost[s["name"]] for s in order[: order.index(f) + 1])))
            break
    return {"red_runs": len(saved), "mean_saved_per_red_run_s": mean(saved),
            "saved_per_run_s": (sum(saved) / n_completed) if n_completed else None}


_UPDATE_MSG = re.compile(r"^Merge (remote-tracking )?branch '?[^ ']+'? (of \S+ )?into ")


def lead_metrics(bundle):
    """Push-to-merge lead time per merged PR, post-green wait, cycles per PR, and seconds spent re-running CI
    because the base moved (runs whose head commit is a base-into-branch merge)."""
    runs, pulls = bundle.get("runs") or [], bundle.get("pulls") or []
    ref_to_pr = {p["head_ref"]: p["number"] for p in pulls if p.get("head_ref")}
    by_pr = {}
    for r in runs:  # a run of a fork's PR lists no pull_requests: fall back to its head branch name
        for n in r.get("prs") or ([ref_to_pr[r["head_branch"]]] if r.get("head_branch") in ref_to_pr else []):
            by_pr.setdefault(n, []).append(r)
    firsts, lasts, waits, cycles, upd = [], [], [], [], []
    for p in pulls:
        rs = by_pr.get(p["number"])
        if not rs or not p.get("merged_at"):
            continue
        rs = sorted(rs, key=lambda r: ts(r["created_at"]) or 0)
        cycles.append(len({r["head_sha"] for r in rs}))
        firsts.append(span(rs[0]["created_at"], p["merged_at"]))
        lasts.append(span(rs[-1]["created_at"], p["merged_at"]))
        greens = [r for r in rs if r.get("conclusion") == "success"]
        if greens:
            waits.append(span(max(greens, key=lambda r: ts(r["updated_at"]) or 0)["updated_at"], p["merged_at"]))
        upd.append(sum(span(r["created_at"], r["updated_at"]) or 0.0 for r in rs if _UPDATE_MSG.match(r.get("msg") or "")))
    merged = [ts(p["merged_at"]) for p in pulls if p.get("merged_at") and ts(p["merged_at"]) is not None]
    days = {int(t // 86400) for t in merged}  # UTC days; merge rate = merged PRs / calendar days from first to last merge
    per_day = len(merged) / (max(days) - min(days) + 1) if len(merged) >= 2 else None
    return {"prs": len(cycles), "cycles_median": med(cycles), "first_push_to_merge_s": med(firsts),
            "last_push_to_merge_s": med(lasts), "post_green_wait_s": med(waits),
            "update_branch_ci_s_per_pr": mean(upd), "merged_per_day": per_day}


def cache_metrics(root, logs=None):
    """Cache steps found in the workflows and, when job logs are supplied, the measured hit rate. Without logs the
    rate is None: GitHub exposes hit/miss only in the step log, so any other figure would be a guess."""
    found = []
    wdir = os.path.join(root, ".github", "workflows")
    for fn in sorted(os.listdir(wdir)) if os.path.isdir(wdir) else []:
        text = read(os.path.join(wdir, fn))
        for m in re.finditer(r"uses:\s*(actions/cache\S*|[\w./-]*(?:cache)[\w./-]*@\S+)|^\s+cache:\s*\S+", text, re.M):
            found.append({"workflow": fn, "match": m.group(0).strip()[:80]})
    hits = sum(t.count("Cache restored from key") for t in logs or [])
    miss = sum(t.count("Cache not found for input keys") for t in logs or [])
    rate = hits / (hits + miss) if (hits + miss) else None
    note = ("no cache step in any workflow" if not found else
            "hit rate measured from %d log(s)" % len(logs or []) if rate is not None else
            "unverified: hit/miss is only in the step log; pass --logs DIR of downloaded job logs")
    return {"steps": found, "hits": hits, "misses": miss, "hit_rate": rate, "note": note}


def dup_seconds(smap, ci_steps, local):
    """Seconds per stage for every duplicated suite.

    ci / train: the median seconds of the CI step that runs the suite, split evenly over that step's commands.
    commit / push / precheck: the median `time` rows with the same suite key; for a hook stage with no per-suite row,
    the hook's own median wall time split evenly over the suites the hook runs (an even split, not a measurement).
    waste = seconds at every stage except the one to keep (known stages only; unmeasured ones are listed)."""
    by_step = {s["name"]: s["median_s"] for s in ci_steps if s["median_s"] is not None}
    n_cmds, stage_keys = {}, {}
    for e in smap["entries"]:
        stage_keys.setdefault(e["stage"], set()).add(e["key"])
        if e["step"] and e["source"].startswith(".github/workflows/"):
            n_cmds.setdefault(e["step"], set()).add(e["cmd"])
    loc = {}
    for r in local.get("rows", []):
        if r["key"]:
            loc.setdefault((r["stage"], r["key"]), []).append(r["wall_median_s"])
    out = []
    for d in smap["duplicates"]:
        secs = {}
        for st in d["stages"]:
            es = [e for e in smap["entries"] if e["key"] == d["key"] and e["stage"] == st]
            if st in BLOCKING:
                vals = [by_step[e["step"]] / len(n_cmds[e["step"]]) for e in es if e["step"] in by_step]
                secs[st] = sum(vals) if vals else None
                continue
            secs[st] = med(loc.get((st, d["key"]), []))
            if secs[st] is None and local.get("stage_s", {}).get(st):
                secs[st] = local["stage_s"][st] / len(stage_keys[st])
        known = {s: v for s, v in secs.items() if v is not None and s in d["drop"]}
        out.append({**{k: d[k] for k in ("key", "stages", "keep", "drop", "enforced")}, "seconds": secs,
                    "waste_s": sum(known.values()),
                    "unmeasured": [s for s in d["stages"] if secs[s] is None and s in d["drop"]]})
    return out


def local_breakeven(dups, queue_s, red_rate):
    """Red rate above which keeping ONE local run of the duplicated suites beats running them once at the merge
    gate: the run costs `local` seconds every cycle and saves red_rate x (CI seconds + queue) per cycle. Only suites
    with both a local and a CI time contribute; None when no suite has both."""
    local = ci = 0.0
    for d in dups:
        loc = [v for s, v in d["seconds"].items() if s != d["keep"] and s != "ci" and s != "train" and v is not None]
        if loc and d["seconds"].get(d["keep"]) is not None:
            local, ci = local + min(loc), ci + d["seconds"][d["keep"]]
    if not ci:
        return None
    need = local / (ci + (queue_s or 0.0))
    return {"local_s": local, "ci_s": ci, "queue_s": queue_s or 0.0, "red_rate_needed": need,
            "red_rate_observed": red_rate, "pays_off": red_rate is not None and red_rate > need}


def git_history(root, n=30):
    """Last `n` first-parent merges/commits -> {merges: [changed file lists], tracked, tests, lock_stable}."""
    raw = git(root, "log", "--first-parent", "-m", "-n", str(n), "--name-only", "--format=@@%H")
    merges = [[f for f in blk.splitlines()[1:] if f] for blk in raw.split("@@")[1:]]
    merges = [m for m in merges if m]
    tracked = [f for f in git(root, "ls-files").splitlines() if f]
    locks = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock", "Pipfile.lock",
             "Cargo.lock", "go.sum", "Gemfile.lock", "composer.lock", "requirements.txt"}
    has_lock = any(posixpath.basename(f) in locks for f in tracked)
    stable = [not any(posixpath.basename(f) in locks for f in m) for m in merges]
    return {"merges": merges, "tracked": tracked, "has_lock": has_lock,
            "lock_stable": (sum(stable) / len(stable)) if stable else None}


_TESTISH = re.compile(r"(^|/)(tests?|__tests__|spec)/|(^|/)test[-_][^/]*$|[-_.]tests?\.[a-z]+$|[-_.]spec\.[a-z]+$")


def select_frequency(root, hist, cap=300):
    """{test file: share of recent merges a name-reference selector would run it for}. A test is tied to a merge when
    it is itself changed or mentions the basename of a changed file: the selector a repo can build without a
    dependency graph (a real graph can only do better)."""
    tests = [f for f in hist["tracked"] if _TESTISH.search(f)][:cap]
    if not tests or not hist["merges"]:
        return {}
    text = {t: read(os.path.join(root, t)) for t in tests}
    hits = dict.fromkeys(tests, 0)
    for ch in hist["merges"]:
        names = {posixpath.basename(c) for c in ch}
        for t in tests:
            if t in ch or any(n in text[t] for n in names):
                hits[t] += 1
    return {t: n / len(hist["merges"]) for t, n in hits.items()}


def affected_fraction(root, hist, cap=300):
    """Mean share of test files such a selector runs per merge (None without tests or history)."""
    return mean(list(select_frequency(root, hist, cap).values()))


def change_fraction(hist):
    """Mean fraction of tracked files touched per merge (the work an incremental tool cannot skip)."""
    if not hist["tracked"] or not hist["merges"]:
        return None
    return mean([len(m) / len(hist["tracked"]) for m in hist["merges"]])


# --------------------------------------------------------------------------- the profile
_SETUPISH = re.compile(r"^(Set up job|Complete job|Post |Run actions/(checkout|cache|setup-))", re.I)
_INSTALLISH = re.compile(r"install|setup|set up|restore|download|dependenc|\bpip\b|\bnpm\b|yarn|bundle|\bapt\b|build", re.I)
_TESTISH_STEP = re.compile(r"test|pytest|jest|spec|e2e|eval|check", re.I)
_LINTISH = re.compile(r"lint|type|mypy|ruff|eslint|tsc|pyright|flake8|format|style", re.I)


def build_profile(root, bundle, local, smap, hist=None, cache=None, repo=None, sections=None):
    """Assemble every measurement into one JSON-able profile and rank the bottlenecks (pure given its inputs).

    `sections` = {CI step name: {section: weight}}: timings of the sections inside a monolithic step, in any one unit
    (CPU seconds are steadier than wall time on a busy host). They are scaled to the step's CI median and let the
    shard fix price splitting that step."""
    ci = ci_metrics(bundle)
    lead = lead_metrics(bundle)
    dups = dup_seconds(smap, ci["steps"], local)
    cycles = lead["cycles_median"] or 1.0
    P = {"schema": 1, "repo": repo, "generated": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "stage_map": {"suites": len(smap["suites"]), "duplicates": len(smap["duplicates"])},
         "ci": {k: ci[k] for k in ("runs", "cancelled_or_skipped", "measured_runs", "wall_s", "exec_s", "queue_s",
                                   "critical_jobs", "steps")},
         "flake": ci["flake"], "fail_fast": ci["fail_fast"], "lead": lead, "cache": cache or cache_metrics(root),
         "local": local, "dups": dups, "cycles": cycles, "limits": bundle.get("limits", []),
         "breakeven": local_breakeven(dups, ci["queue_s"]["median"], ci["flake"]["red_rate"])}
    P["sections"] = sections or {}
    if hist is not None:
        freq = select_frequency(root, hist)
        P["history"] = {"merges": len(hist["merges"]), "tracked": len(hist["tracked"]), "has_lock": hist["has_lock"],
                        "lock_stable": hist["lock_stable"], "change_fraction": change_fraction(hist),
                        "affected_fraction": mean(list(freq.values())), "select_freq": freq}
    P["stages_s"] = {"commit": local["stage_s"].get("commit"), "push": local["stage_s"].get("push"),
                     "ci_queue": ci["queue_s"]["median"], "ci_exec": ci["exec_s"]["median"],
                     "merge_wait": lead["post_green_wait_s"]}
    rows = []
    for s in ci["steps"]:
        if s["median_s"]:
            rows.append(("ci", "%s / %s" % (s["job"], s["name"]), s["median_s"], cycles,
                         "median of %d run(s)" % s["n"]))
    if ci["queue_s"]["median"]:
        rows.append(("ci", "queue wait (runner pickup)", ci["queue_s"]["median"], cycles,
                     "median over %d run(s)" % ci["measured_runs"]))
    if lead["post_green_wait_s"]:
        rows.append(("merge", "post-green wait (approval, merge train)", lead["post_green_wait_s"], 1,
                     "median over %d merged PR(s)" % lead["prs"]))
    if lead["update_branch_ci_s_per_pr"]:
        rows.append(("ci", "CI re-runs forced by base updates", lead["update_branch_ci_s_per_pr"], 1,
                     "mean seconds per merged PR"))
    if ci["flake"]["rerun_waste_s_per_run"]:
        rows.append(("ci", "reruns (%d flake suspect(s))" % ci["flake"]["flake_suspects"],
                     ci["flake"]["rerun_waste_s_per_run"], cycles, "attempts x median run, over completed runs"))
    for o in local["rows"]:
        if o["name"].startswith("hook:") and o["wall_median_s"]:
            rows.append((o["stage"], "local %s" % o["name"], o["wall_median_s"], cycles, "median of %d timing(s)" % o["n"]))
    for d in dups:
        if d["waste_s"] > 0:
            rows.append(("duplicate", "%s at %s (keep %s)" % (d["key"], "+".join(d["stages"]), d["keep"]),
                         d["waste_s"], cycles, "sum of the dropped stages' seconds"))
    ref = lead["first_push_to_merge_s"]
    total = sum(r[2] * r[3] for r in rows)
    rows.sort(key=lambda r: -r[2] * r[3])
    P["bottlenecks"] = [{"rank": i + 1, "stage": st, "item": it, "per_cycle_s": s, "per_pr_s": s * c,
                         "share": (s * c / ref) if ref else ((s * c / total) if total else None), "evidence": ev}
                        for i, (st, it, s, c, ev) in enumerate(rows)]
    P["share_basis"] = "first-push-to-merge median" if ref else "sum of ranked rows (no lead-time data)"
    top = next((s for s in ci["steps"] if s["median_s"] and not _SETUPISH.search(s["name"])), None)
    exe = ci["exec_s"]["median"]
    P["dominant"] = ({"step": top["name"], "median_s": top["median_s"], "share": top["median_s"] / exe,
                      "sectioned": top["name"] in P["sections"]}
                     if top and exe and top["median_s"] / exe > 0.5 else None)
    return P


# --------------------------------------------------------------------------- fix catalogue
def _steps_matching(P, rx, work_only=True):
    return [s for s in P["ci"]["steps"] if s["median_s"] and rx.search(s["name"])
            and not (work_only and _SETUPISH.search(s["name"]))]


def _lpt(durs, k):
    """Longest-processing-time-first makespan of `durs` over k workers."""
    load = [0.0] * k
    for d in sorted(durs, reverse=True):
        load[load.index(min(load))] += d
    return max(load)


def f_dedup(P, a):
    unm = sum(len(d["unmeasured"]) for d in P["dups"])
    w = sum(d["waste_s"] for d in P["dups"])
    return (w if P["dups"] else 0.0,
            "%d duplicated suite(s); seconds of every stage except the one kept; %d stage run(s) unmeasured%s" % (
                len(P["dups"]), unm, " (time them with `time`)" if unm else ""))


def f_fail_fast(P, a):
    ff = P["fail_fast"]
    if not P["ci"]["measured_runs"]:
        return None, "no CI runs measured"
    if not ff["red_runs"]:
        return 0.0, "no red run in the sample: nothing to fail earlier"
    return ff["saved_per_run_s"], "%d red run(s): mean %s saved by cheapest-first order, spread over %d completed runs" % (
        ff["red_runs"], fmt(ff["mean_saved_per_red_run_s"]), P["flake"]["completed"])


def f_flake(P, a):
    w = P["flake"]["rerun_waste_s_per_run"]
    if w is None:
        return None, "no completed CI runs measured"
    return w, "%d rerun(s), %d flake suspect(s) of %d runs; attempts x median run" % (
        P["flake"]["reruns"], P["flake"]["flake_suspects"], P["flake"]["completed"])


def f_cache(P, a):
    h = P.get("history")
    inst = sum(s["median_s"] for s in _steps_matching(P, _INSTALLISH))
    if h is None:
        return None, "unverified: needs git history (run inside a checkout)"
    if not h["has_lock"]:
        return 0.0, "no dependency manifest or lockfile tracked: nothing to cache"
    if P["cache"]["steps"] and P["cache"]["hit_rate"] is None:
        return None, "a cache step exists but its hit rate is unverified (pass --logs)"
    rate = P["cache"]["hit_rate"] if P["cache"]["steps"] else h["lock_stable"]
    if rate is None:
        return None, "no merge history"
    gain = inst * (1 - P["cache"]["hit_rate"]) if P["cache"]["steps"] else inst * rate
    return gain, "install/setup/build steps %s x %s (%s)" % (
        fmt(inst), "%.0f%%" % (100 * (1 - P["cache"]["hit_rate"] if P["cache"]["steps"] else rate)),
        "current miss rate" if P["cache"]["steps"] else "share of merges that left the lockfile unchanged")


def f_affected(P, a):
    """Per CI step that runs test files: step seconds x (1 - how often a name-reference selector runs its files).
    A monolithic test script is one file, so it is skipped only as often as no changed file name appears in it."""
    h = P.get("history")
    freq = (h or {}).get("select_freq") or {}
    if not freq:
        return None, "unverified: needs git history with tracked test files"
    gain, n = 0.0, 0
    for s in P["ci"]["steps"]:
        if not s["median_s"] or _SETUPISH.search(s["name"]):
            continue
        files = {e["key"].split(" ")[0] for e in a.entries if e["stage"] == "ci" and e["step"] == s["name"]}
        files = {f for f in files if _TESTISH.search(f)}
        if files:  # a test file the selector cannot see is assumed to run every time
            gain, n = gain + s["median_s"] * (1 - mean([freq.get(f, 1.0) for f in files])), n + 1
    return gain, "%d test step(s): step seconds x (1 - share of the last %d merges a name-reference selector runs its test files for)" % (
        n, h["merges"])


def f_shard(P, a):
    """Independent steps (and, for a step with measured sections, those sections scaled to the step's CI median)
    over k jobs by longest-processing-time-first, plus each job's setup. The gain is serial minus that wall time."""
    secs = P.get("sections") or {}
    work, split = [], 0
    for s in P["ci"]["steps"]:
        if not s["median_s"] or _SETUPISH.search(s["name"]):
            continue
        sec = secs.get(s["name"])
        if sec and sum(sec.values()) > 0:
            work += [v * s["median_s"] / sum(sec.values()) for v in sec.values()]
            split += 1
        else:
            work.append(s["median_s"])
    setup = sum(s["median_s"] for s in P["ci"]["steps"] if s["median_s"] and _SETUPISH.search(s["name"]))
    if not work:
        return None, "no CI step timings"
    k = a.shards
    makespan = _lpt(work, k)
    gain = max(0.0, sum(work) - makespan - setup)
    return gain, "%d independent unit(s) %s%s -> %d-way LPT makespan %s + per-job setup %s (units assumed independent)" % (
        len(work), fmt(sum(work)), " (%d step(s) split into measured sections)" % split if split else "", k,
        fmt(makespan), fmt(setup))


def f_queue(P, a):
    u = P["lead"]["update_branch_ci_s_per_pr"]
    if u is None:
        return None, "unverified: needs merged-PR and run data"
    return u / (P["cycles"] or 1.0), "mean CI seconds per PR spent on base-into-branch re-runs (a queue builds the merge once)"


def f_incremental(P, a):
    h = P.get("history")
    t = sum(s["median_s"] for s in _steps_matching(P, _LINTISH))
    if h is None or h["change_fraction"] is None:
        return None, "unverified: needs git history"
    return t * (1 - h["change_fraction"]), "lint/type/format steps %s x (1 - %.1f%% of tracked files change per merge)" % (
        fmt(t), 100 * h["change_fraction"])


def f_move_local(P, a):
    ci = {s["name"]: s["median_s"] for s in P["ci"]["steps"] if s["median_s"]}
    gain, n = 0.0, 0
    for o in P["local"]["rows"]:
        for e in a.entries:
            if e["key"] == o["key"] and e["stage"] == "ci" and e["step"] in ci and o["stage"] != "ci":
                d = ci[e["step"]] - (o["wall_median_s"] or 0)
                if d > 0:
                    gain, n = gain + d, n + 1
    if not P["local"]["rows"]:
        return None, "unverified: no local timings recorded (use `time`)"
    return gain, "%d CI-only suite(s) measured faster locally (CI step - local wall); needs a non-bypassable gate elsewhere" % n


def f_runner(P, a):
    use = {}
    for o in P["local"]["rows"]:
        if o["wall_median_s"] and o["cpu_median_s"]:
            use[o["key"]] = o["cpu_median_s"] / o["wall_median_s"]
    gain = 0.0
    for e in a.entries:
        s = next((x for x in P["ci"]["steps"] if x["name"] == e["step"]), None)
        u = use.get(e["key"])
        if s and s["median_s"] and u:
            gain += s["median_s"] * (1 - 1 / min(a.runner_ratio, max(1.0, u)))
    if not use:
        return None, "unverified: needs local cpu/wall timings to know whether any step uses more than one core"
    return gain, "step seconds x (1 - 1/min(%gx cores, observed cpu/wall)); a serial step (cpu/wall ~1) gains nothing" % a.runner_ratio


# (id, name, relative effort 1/2/4, source ids in docs/standards-index.md, formula, how)
FIXES = [
    ("dedup", "Remove duplicate runs: each blocking check once, at the latest gate that still blocks merge", 1,
     ["swe-ci", "fowler-ci"], f_dedup,
     "Delete the earlier runs of every flagged suite (hook line, doc step, CI step); keep the latest blocking gate."),
    ("fail-fast", "Fail-fast ordering: cheapest checks first, stop at the first red", 1, ["fowler-ci", "gh-matrix"],
     f_fail_fast, "Reorder steps by ascending duration; keep fail-fast on shards."),
    ("flake", "Quarantine flaky tests, stop blind reruns", 2, ["google-flaky", "swe-ci"], f_flake,
     "Track pass/fail per test, quarantine above a flake threshold, rerun a failure at most once."),
    ("cache", "Dependency and build caching", 1, ["gh-cache", "actions-cache-src"], f_cache,
     "Cache keyed on the lockfile hash with restore-keys; measure the hit rate from the step logs."),
    ("affected", "Affected / changed-test selection", 4, ["pts-paper", "swe-ci"], f_affected,
     "Run tests that reference changed files on PRs; run the full suite once at the merge gate."),
    ("shard", "Test sharding and parallelism", 2, ["gh-matrix", "xdist", "pw-shard", "gh-hosted-runners", "amdahl", "cpm"], f_shard,
     "Split independent steps over parallel jobs; keep one aggregate job under the required check name."),
    ("queue", "Merge queue / batching", 2, ["gh-merge-queue"], f_queue,
     "Enable the queue, add the merge_group trigger, build the merge group once."),
    ("incremental", "Incremental type check and lint", 1, ["eslint-cache", "ts-incremental", "ruff-cache", "mypy-daemon"],
     f_incremental, "Turn on the tool's cache / incremental mode and persist its cache dir."),
    ("move-local", "Move a check local, keep one blocking gate", 2, ["git-hooks", "swe-ci"], f_move_local,
     "Run it in the push hook only if an unbypassable gate (train, integrator) still blocks merge."),
    ("runner", "Faster runners", 1, ["gh-larger-runners", "amdahl"], f_runner,
     "Larger runner for steps that already use several cores; costs money, helps only parallel work."),
]


def price_fixes(P, entries, shards=4, runner_ratio=2.0):
    """Run every catalogue formula against a profile -> ranked list. Duplicate removal ranks first when it saves
    more than the noise floor; the rest rank by saving per relative effort; unpriced fixes go last."""
    a = argparse.Namespace(shards=shards, runner_ratio=runner_ratio, entries=entries)
    ref = P["lead"]["first_push_to_merge_s"] or sum(b["per_pr_s"] for b in P["bottlenecks"]) or 0
    floor = max(NOISE_FLOOR_S, 0.01 * ref)
    out = []
    for fid, name, effort, src, fn, how in FIXES:
        cyc, basis = fn(P, a)
        per_pr = None if cyc is None else cyc * P["cycles"]
        out.append({"id": fid, "name": name, "effort": effort, "per_cycle_s": cyc, "per_pr_s": per_pr,
                    "score": None if per_pr is None else per_pr / effort, "basis": basis, "sources": src, "how": how,
                    "lever": per_pr is not None and per_pr >= floor,
                    "unmeasured": sum(len(d["unmeasured"]) for d in P["dups"]) if fid == "dedup" else 0})

    def key(f):
        if f["per_pr_s"] is None:
            return (2, 0)
        if f["id"] == "dedup" and f["lever"]:
            return (0, 0)
        return (1, -f["score"])
    out.sort(key=key)
    for i, f in enumerate(out):
        f["rank"] = i + 1
    return out


GUARD_LEAD, GUARD_RATE = "lead.first_push_to_merge_s", "lead.merged_per_day"  # compare outcome guardrails


def get_path(P, path):
    """Dotted-path lookup in a profile dict; None when any step is missing."""
    cur = P
    for part in path.split("."):
        cur = cur.get(part) if isinstance(cur, dict) else None
    return cur


def compare_profiles(before, after, metric, min_gain=MIN_GAIN, min_n=3, stage_only=False):
    """KEEP only if the target metric dropped by more than min_gain (and the noise floor), both profiles have
    at least min_n measured runs behind it, AND the delivery outcome did not regress: lead.first_push_to_merge_s
    must not rise and lead.merged_per_day must not fall by more than min_gain. A stage that got faster while
    delivery got slower is REVERT; outcome data missing on either side is UNVERIFIED unless stage_only (then KEEP,
    labelled stage-only). REVERT if the target did not drop; UNVERIFIED if it cannot be read."""
    def get(P):
        return get_path(P, metric)
    def runs(P):  # samples behind the metric: measured CI runs, or recorded hook timings for a local stage
        if metric.startswith(("ci.", "lead.", "flake.")):
            return (P.get("ci") or {}).get("measured_runs") or 0
        rows = (P.get("local") or {}).get("rows", [])
        if metric.startswith("stages_s."):
            stage = metric.split(".")[1]
            if stage in ("commit", "push"):
                return min([r["n"] for r in rows if r["name"].startswith("hook:") and r["stage"] == stage] or [0])
        if metric.startswith("local.by_name."):
            return min([r["n"] for r in rows if r["name"] == metric.split(".", 2)[2]] or [0])
        if metric in ("stages_s.ci_queue", "stages_s.ci_exec"):
            return (P.get("ci") or {}).get("measured_runs") or 0
        if metric == "stages_s.merge_wait":
            return (P.get("lead") or {}).get("prs") or 0
        return None  # unknown metric: no sample count to check, so no KEEP

    b, a = get(before), get(after)
    if not isinstance(b, (int, float)) or not isinstance(a, (int, float)):
        return {"verdict": "UNVERIFIED", "reason": "metric %r missing in %s" % (
            metric, "both" if b is None and a is None else "before" if b is None else "after")}
    ns = [x for x in (runs(before), runs(after)) if x is not None]
    if not ns:
        return {"verdict": "UNVERIFIED", "reason": "no sample count known for metric %r; cannot call it a drop" % metric,
                "before": b, "after": a}
    if min(ns) < min_n:
        return {"verdict": "UNVERIFIED", "reason": "only %d sample(s) on the smaller side; need >= %d" % (min(ns), min_n),
                "before": b, "after": a}
    delta = a - b
    gain = (b - a) / b if b else 0.0
    ok = delta < 0 and gain > min_gain and (b - a) > NOISE_FLOOR_S
    n = " [n=%d]" % min(ns) if ns else ""
    if ok and stage_only:
        n += " [stage-only: delivery outcome not checked]"
    elif ok:
        for g, up_is_bad, f in ((GUARD_LEAD, True, fmt), (GUARD_RATE, False, lambda v: "%.2f/day" % v)):
            gb, ga = get_path(before, g), get_path(after, g)
            if not isinstance(gb, (int, float)) or not isinstance(ga, (int, float)):
                return {"verdict": "UNVERIFIED", "metric": metric, "before": b, "after": a,
                        "reason": "outcome not measured: %s missing in %s (use --stage-only to accept a stage-only KEEP)" % (
                            g, "both" if gb is None and ga is None else "before" if gb is None else "after")}
            worse = (ga - gb) if up_is_bad else (gb - ga)
            if worse > 0 and worse > min_gain * gb:
                return {"verdict": "REVERT", "metric": metric, "before": b, "after": a, "delta_s": delta, "gain": gain,
                        "reason": "stage improved but delivery outcome regressed: %s %s->%s" % (g, f(gb), f(ga))}
    return {"verdict": "KEEP" if ok else "REVERT", "metric": metric, "before": b, "after": a, "delta_s": delta,
            "gain": gain, "reason": "dropped %.1f%% (%s -> %s)%s" % (100 * gain, fmt(b), fmt(a), n) if ok else
            "did not drop by more than %.0f%% and %s%s" % (100 * min_gain, fmt(NOISE_FLOOR_S), n)}


# --------------------------------------------------------------------------- output
def print_map(smap):
    ks = sorted(smap["suites"], key=lambda s: (-len(s["stages"]), s["key"]))
    w = min(60, max([len(s["key"]) for s in ks] + [5]))
    print("SUITE x STAGE MAP  (%d suites, %d at more than one stage)" % (len(ks), len(smap["duplicates"])))
    print("%-*s  %s" % (w, "suite", "  ".join("%-8s" % s for s in STAGES)))
    for s in ks:
        k = s["key"] if len(s["key"]) <= w else "..." + s["key"][-(w - 3):]  # keep the tail: the script and flag
        print("%-*s  %s%s" % (w, k, "  ".join("%-8s" % ("X" if st in s["stages"] else ".") for st in STAGES),
                              "   <-- DUPLICATE" if len(s["stages"]) > 1 else ""))
    if smap["duplicates"]:
        print("\nDUPLICATES: run each blocking check once, at the latest gate that still blocks merge")
        for d in smap["duplicates"]:
            if d["enforced"]:
                print("  %s: keep at %s, drop from %s" % (d["key"], d["keep"], ", ".join(d["drop"])))
            else:
                print("  %s: no gate proven to block merge runs it (push-only, advisory or conditional): "
                      "drop nothing" % d["key"])
    elif not ks:
        print("(no suites found: declare them with --stage STAGE=CMD)")


def print_profile(P):
    print("PIPELINE PROFILE  %s  %s" % (P["repo"] or "(local)", P["generated"]))
    for lim in P["limits"]:
        print("  LIMIT: " + lim)
    ci, ld, fl = P["ci"], P["lead"], P["flake"]
    print("\nPER-STAGE WALL TIME ON THE CRITICAL PATH (medians)")
    for k, label in (("commit", "local commit hook"), ("push", "local push hook"), ("ci_queue", "CI queue wait"),
                     ("ci_exec", "CI execution"), ("merge_wait", "post-green wait (approval / merge train)")):
        print("  %-42s %s" % (label, fmt(P["stages_s"][k])))
    print("\nLEAD TIME  prs=%d  cycles/PR=%s  first push->merge %s  last push->merge %s" % (
        ld["prs"], "%.1f" % P["cycles"], fmt(ld["first_push_to_merge_s"]), fmt(ld["last_push_to_merge_s"])))
    print("CI         runs=%d (cancelled/skipped %d) measured=%d  wall median %s p90 %s  exec median %s" % (
        ci["runs"], ci.get("cancelled_or_skipped", 0), ci["measured_runs"], fmt(ci["wall_s"]["median"]),
        fmt(ci["wall_s"]["p90"]), fmt(ci["exec_s"]["median"])))
    print("FLAKE      red %s  reruns %d  flake suspects %d" % (
        "n/a" if fl["red_rate"] is None else "%.0f%%" % (100 * fl["red_rate"]), fl["reruns"], fl["flake_suspects"]))
    print("CACHE      steps=%d  hit rate %s  (%s)" % (
        len(P["cache"]["steps"]), "n/a" if P["cache"]["hit_rate"] is None else "%.0f%%" % (100 * P["cache"]["hit_rate"]),
        P["cache"]["note"]))
    unm = sum(len(d["unmeasured"]) for d in P["dups"])
    print("DUPLICATES %d suite(s) at >1 stage; wasted per cycle %s%s" % (
        len(P["dups"]), fmt(sum(d["waste_s"] for d in P["dups"])),
        "; %d stage run(s) not timed yet (suites --run, hooks --run)" % unm if unm else ""))
    be = P.get("breakeven")
    if be:
        obs = "n/a" if be["red_rate_observed"] is None else "%.0f%%" % (100 * be["red_rate_observed"])
        print("           one local full run of them %s (%s local vs %s CI + %s queue; observed red rate %s)" % (
            "never pays off: it costs more than the CI run it could save" if be["red_rate_needed"] >= 1 else
            "pays off only above a red rate of %.0f%%" % (100 * be["red_rate_needed"]),
            fmt(be["local_s"]), fmt(be["ci_s"]), fmt(be["queue_s"]), obs))
    print("\nBOTTLENECKS (ranked by seconds per merged PR; share = of %s)" % P["share_basis"])
    print("  %-3s %-9s %-62s %9s %9s %6s" % ("#", "stage", "item", "s/cycle", "s/PR", "share"))
    for b in P["bottlenecks"][:15]:
        print("  %-3d %-9s %-62s %9s %9s %6s" % (b["rank"], b["stage"], b["item"][:62], fmt(b["per_cycle_s"]),
                                                  fmt(b["per_pr_s"]), "n/a" if b["share"] is None else "%.0f%%" % (100 * b["share"])))
    if not P["bottlenecks"]:
        print("  (no measurements: no CI data and no local timings)")
    dm = P.get("dominant")
    if dm:
        print("\nDOMINANT STEP: '%s' is %.0f%% of CI execution (%s). %s" % (
            dm["step"], 100 * dm["share"], fmt(dm["median_s"]),
            "Its %d timed sections price the shard fix." % len(P["sections"][dm["step"]]) if dm.get("sectioned") else
            "Sharding is unpriced until its internals are timed (--sections), and any fix that leaves it whole caps "
            "the speed-up (Amdahl)."))


def print_fixes(fixes, accept_unmeasured=False):
    print("FIX CATALOGUE (saving computed from the profile; effort is relative 1/2/4, not hours)")
    print("  %-3s %-12s %9s %7s  %s" % ("#", "fix", "s/PR", "effort", "basis"))
    for f in fixes:
        print("  %-3d %-12s %9s %7d  %s%s" % (f["rank"], f["id"], fmt(f["per_pr_s"]), f["effort"], f["basis"],
                                              "" if f["lever"] or f["per_pr_s"] is None else "  [below noise floor]"))
    dd = next((f for f in fixes if f["id"] == "dedup"), None)
    if dd and dd["unmeasured"] and not accept_unmeasured:  # duplicates rank first once priced: do not tune a stage before
        print("\nDECIDE: measure first -- %d duplicated stage run(s) are not timed (`suites --run`, `hooks --run`), so the "
              "fix that ranks first is unpriced. Re-run with --accept-unmeasured only when they cannot be timed." %
              dd["unmeasured"])
        return
    pick = next((f for f in fixes if f["lever"]), None)
    if pick:
        print("\nDECIDE: %s -- %s\n  how: %s\n  then: re-measure and `compare`; keep only if the target metric dropped." % (
            pick["id"], pick["name"], pick["how"]))
    else:
        print("\nDECIDE: no priced fix clears the noise floor. Measure what is missing (see `unverified` rows) "
              "before changing anything.")


# --------------------------------------------------------------------------- CLI
def _repo_slug(root):
    u = git(root, "remote", "get-url", "origin").strip()
    m = re.search(r"github\.com[:/]([^/\s]+/[^/\s]+?)(?:\.git)?$", u)
    return m.group(1) if m else None


def _extra(args):
    extra = {}
    for item in getattr(args, "declare", None) or []:
        st, _, cmd = item.partition("=")
        if st not in STAGES or not cmd:
            die("pipeline_profile: --declare expects one of %s=CMD, got %r" % ("|".join(STAGES), item))
        extra.setdefault(st, []).append(cmd)
    p = os.path.join(args.root, ".perun", "pipeline.json")
    if os.path.isfile(p):
        try:
            for st, cmds in load_json(p).get("stages", {}).items():
                if st in STAGES:
                    extra.setdefault(st, []).extend(cmds)
        except (OSError, ValueError):
            die("pipeline_profile: unreadable %s" % p)
    return extra


def cmd_map(args):
    smap = stage_map(args.root, _extra(args))
    if args.json:
        print(json.dumps({k: smap[k] for k in ("suites", "duplicates")}, indent=1))
    else:
        print_map(smap)
    return 0


def cmd_time(args):
    if not args.cmd:
        die("pipeline_profile: time needs `-- CMD ARGS`")
    argv = args.cmd[1:] if args.cmd[0] == "--" else args.cmd
    text = " ".join(argv) if args.shell else " ".join(shlex.quote(x) for x in argv)  # --shell: the text is a script
    rc, wall, cpu = record_timing(timings_path(args.root, args.log), args.stage, args.name, text, argv, args.shell,
                                  ok_rc=tuple(args.ok_rc or ()))
    print("timed: stage=%s name=%s wall=%s cpu=%s rc=%d" % (args.stage, args.name, fmt(wall), fmt(cpu), rc))
    return rc


def cmd_hooks(args):
    hooks = _hook_files(args.root)
    path = timings_path(args.root, args.log)
    head = git(args.root, "rev-parse", "HEAD").strip()
    branch = git(args.root, "rev-parse", "--abbrev-ref", "HEAD").strip() or "HEAD"
    rc_all = 0
    for stage, paths in hooks.items():
        for p in paths:
            print("%s hook: %s" % (stage, os.path.relpath(p, args.root)))
            if not args.run:
                continue
            if git(args.root, "status", "--porcelain").strip():
                print("  skipped: working tree is dirty (hooks verify the checked-out tree); commit or stash first")
                rc_all = 2
                continue
            env = dict(os.environ, DCR_PREPUSH_SKIP_CACHE="1")
            feed = ("refs/heads/%s %s refs/heads/%s %s\n" % (branch, head, branch, "0" * len(head))) if stage == "push" else ""
            argv = [p, "origin", "(pipeline-profile)"] if stage == "push" else [p]
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            t0 = time.monotonic()
            r = subprocess.run(argv, cwd=args.root, input=feed, text=True, env=env, capture_output=True)
            wall = time.monotonic() - t0
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            cpu = after.ru_utime - before.ru_utime + after.ru_stime - before.ru_stime
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            with open(path, "a", encoding="utf-8") as fh:
                fh.write("\t".join([datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), stage,
                                    "hook:" + os.path.basename(p), "%.3f" % wall, "%.3f" % cpu, str(r.returncode),
                                    os.path.relpath(p, args.root)]) + "\n")
            print("  ran: wall=%s cpu=%s rc=%d" % (fmt(wall), fmt(cpu), r.returncode))
    if not args.run:
        print("(dry list; add --run to execute each hook against HEAD and record its wall time)")
    return rc_all


def cmd_suites(args):
    """Time every duplicated suite at the stages that would be dropped, so dedup is priced from real seconds."""
    smap = stage_map(args.root, _extra(args))
    path, picks = timings_path(args.root, args.log), {}
    for d in smap["duplicates"]:
        for e in smap["entries"]:
            if e["key"] == d["key"] and e["stage"] in d["drop"] and (not args.stage or e["stage"] in args.stage):
                if "$" in e["cmd"]:
                    print("skip   %-8s %s (dynamic argument, cannot replay)" % (e["stage"], d["key"]))
                elif e["stage"] != "ci":  # CI seconds come from the API, not from a local replay
                    picks.setdefault((e["stage"], d["key"]), e["cmd"])
    for (st, key), cmd in sorted(picks.items()):
        if not args.run:
            print("would time  %-8s %s" % (st, cmd[:110]))
            continue
        rc, wall, cpu = record_timing(path, st, key, cmd, None, True, args.root)
        print("timed  %-8s %-8s rc=%d  %s" % (st, fmt(wall), rc, key))
    if not args.run:
        print("(dry list; add --run to execute each once and record its wall time)")
    return 0


def _load_logs(d):
    out = []
    for fn in sorted(os.listdir(d)) if d and os.path.isdir(d) else []:
        out.append(read(os.path.join(d, fn)))
    return out


def cmd_profile(args):
    smap = stage_map(args.root, _extra(args))
    local = local_summary(load_timings(timings_path(args.root, args.log)))
    repo = args.repo or _repo_slug(args.root)
    bundle = {}
    if args.data and os.path.isfile(args.data):
        try:
            bundle = load_json(args.data)
        except (OSError, ValueError):
            die("pipeline_profile: unreadable bundle %s" % args.data)
    if repo and not args.offline:
        bundle = fetch_bundle(repo, bundle, args.runs, args.workflow,
                              os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN"))
        if args.data:
            save_json(args.data, bundle)
    elif not bundle:
        bundle = {"limits": ["no GitHub data: %s" % ("offline without a --data bundle" if repo else
                                                     "no origin remote and no --repo")]}
    try:
        sections = load_json(args.sections) if args.sections else None
    except (OSError, ValueError):
        die("pipeline_profile: unreadable sections file %s" % args.sections)
    P = build_profile(args.root, bundle, local, smap, git_history(args.root, args.merges),
                      cache_metrics(args.root, _load_logs(args.logs)), repo, sections)
    if args.out:
        save_json(args.out, P)
    print_profile(P)
    return 0


def _load_profile(path):
    try:
        return load_json(path)
    except (OSError, ValueError):
        die("pipeline_profile: unreadable profile %s" % path)


def cmd_fixes(args):
    P = _load_profile(args.profile)
    fixes = price_fixes(P, stage_map(args.root, _extra(args))["entries"], args.shards, args.runner_ratio)
    if args.json:
        print(json.dumps(fixes, indent=1))
    else:
        print_fixes(fixes, args.accept_unmeasured)
    return 0


def cmd_compare(args):
    r = compare_profiles(_load_profile(args.before), _load_profile(args.after), args.metric, args.min_gain,
                         args.min_samples, args.stage_only)
    print("%s  %s" % (r["verdict"], r["reason"]))
    return {"KEEP": 0, "REVERT": 1}.get(r["verdict"], 2)


def selftest():
    """Offline checks of the parser, map, pricing and compare on synthetic data (no network, no repo)."""
    assert suite_key(["bash", "scripts/ci-gates.sh", "size-ratchet", "--base", "x"]) == ("key", "scripts/ci-gates.sh size-ratchet")
    assert suite_key(["python3", "./a/b.py", "--selftest"]) == ("key", "a/b.py --selftest")
    assert suite_key(["FOO=1", "pytest", "-q"]) == ("key", "pytest")
    assert suite_key(["npm", "ci"]) is None and suite_key(["echo", "bash", "x.sh"]) is None
    assert suite_key(["uv", "run", "pytest"]) == ("key", "pytest")
    assert [c[1] for c in commands("make test && make lint || true")] == ["make test", "make lint"]
    wf = parse_workflow("on:\n  pull_request:\n  merge_group:\njobs:\n  a:\n    steps:\n      - name: T\n"
                        "        run: |\n          bash t.sh\n          bash u.sh\n")
    assert wf["on"] == {"pull_request", "merge_group"} and len(wf["jobs"]["a"]["steps"]) == 1
    assert ts("2026-01-01T00:00:10Z") - ts("2026-01-01T00:00:00Z") == 10
    b = {"limits": [], "runs": [], "jobs": {}, "pulls": []}
    smap = {"suites": [], "duplicates": [], "entries": []}
    P = build_profile(".", b, {"rows": [], "stage_s": {}}, smap, None, {"steps": [], "hit_rate": None, "note": ""}, None)
    assert price_fixes(P, [])[0]["per_pr_s"] in (0.0, None)
    assert compare_profiles({"ci": {"measured_runs": 5, "exec_s": {"median": 100.0}}},
                            {"ci": {"measured_runs": 5, "exec_s": {"median": 60.0}}}, "ci.exec_s.median",
                            stage_only=True)["verdict"] == "KEEP"
    ld = lambda f, r: {"ci": {"measured_runs": 5, "exec_s": {"median": 100.0 if f == 1000 else 60.0}},
                       "lead": {"first_push_to_merge_s": f, "merged_per_day": r}}
    assert compare_profiles(ld(1000, 5), ld(1500, 5), "ci.exec_s.median")["verdict"] == "REVERT"  # proxy better, outcome worse
    assert compare_profiles(ld(1000, 5), ld(1100, 5), "ci.exec_s.median")["verdict"] == "REVERT"
    assert compare_profiles(ld(1000, 5), ld(500, 5), "ci.exec_s.median")["verdict"] == "KEEP"
    assert compare_profiles(ld(1000, 5), ld(500, 4), "ci.exec_s.median")["verdict"] == "REVERT"  # merge rate fell
    assert compare_profiles(ld(1000, 5), {"ci": ld(500, 5)["ci"]}, "ci.exec_s.median")["verdict"] == "UNVERIFIED"
    assert compare_profiles({"ci": {"measured_runs": 5, "exec_s": {"median": 100.0}}},
                            {"ci": {"measured_runs": 5, "exec_s": {"median": 99.0}}}, "ci.exec_s.median")["verdict"] == "REVERT"
    print("pipeline_profile selftest: ok")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="pipeline_profile.py", description=__doc__.split("\n")[0])
    ap.add_argument("--selftest", action="store_true")
    sub = ap.add_subparsers(dest="cmd_name")

    def common(p, declare=False):
        p.add_argument("--root", default=".")
        p.add_argument("--log", help="local timings TSV (default <git-common-dir>/pipeline-timings.tsv)")
        if declare:
            p.add_argument("--declare", action="append", metavar="STAGE=CMD",
                           help="add a stage command no file shows, e.g. train='bash scripts/verify.sh' (repeatable)")

    p = sub.add_parser("map", help="suite x stage map (step 1)")
    common(p, True)
    p.add_argument("--json", action="store_true", help="print JSON instead of the table")
    p.set_defaults(fn=cmd_map)
    p = sub.add_parser("time", help="record one local timing")
    common(p)
    p.add_argument("--name", required=True)
    p.add_argument("--stage", dest="stage", required=True, choices=STAGES)
    p.add_argument("--shell", action="store_true", help="run the command text through bash -c")
    p.add_argument("--ok-rc", type=int, action="append", metavar="N",
                   help="an exit code that still counts as a completed run (a suite with known failures); repeatable")
    p.add_argument("cmd", nargs=argparse.REMAINDER)
    p.set_defaults(fn=cmd_time)
    p = sub.add_parser("hooks", help="list / time the commit and push hooks")
    common(p)
    p.add_argument("--run", action="store_true")
    p.set_defaults(fn=cmd_hooks)
    p = sub.add_parser("suites", help="time each duplicated suite at the stages to drop")
    common(p, True)
    p.add_argument("--stage", action="append", choices=STAGES, help="only these stages (repeatable)")
    p.add_argument("--run", action="store_true")
    p.set_defaults(fn=cmd_suites)
    p = sub.add_parser("profile", help="measure and rank bottlenecks")
    common(p, True)
    p.add_argument("--out", metavar="FILE", help="write the profile JSON here (input of `fixes` and `compare`)")
    p.add_argument("--repo", help="OWNER/NAME (default: origin remote)")
    p.add_argument("--workflow", help="workflow file to sample, e.g. ci.yml (default: all)")
    p.add_argument("--runs", type=int, default=30, help="completed PR runs to sample (default 30)")
    p.add_argument("--merges", type=int, default=30, help="recent merges to read from git (default 30)")
    p.add_argument("--data", metavar="FILE", help="read-write API bundle (resume, offline re-analysis)")
    p.add_argument("--offline", action="store_true", help="never call the API; use --data only")
    p.add_argument("--logs", metavar="DIR", help="downloaded job logs, for the cache hit rate")
    p.add_argument("--sections", metavar="FILE", help='timings of the sections inside a dominant CI step, '
                   '{"<step name>": {"<section>": weight}}; prices splitting that step')
    p.set_defaults(fn=cmd_profile)
    p = sub.add_parser("fixes", help="price the fix catalogue from a profile")
    common(p, True)
    p.add_argument("--json", action="store_true", help="print JSON instead of the table")
    p.add_argument("--accept-unmeasured", action="store_true",
                   help="decide even though some duplicated stage runs could not be timed")
    p.add_argument("profile")
    p.add_argument("--shards", type=int, default=4, help="parallel jobs assumed for the shard fix (default 4)")
    p.add_argument("--runner-ratio", type=float, default=2.0, help="core multiple of the faster runner (default 2)")
    p.set_defaults(fn=cmd_fixes)
    p = sub.add_parser("compare", help="BEFORE.json AFTER.json -> KEEP / REVERT / UNVERIFIED")
    p.add_argument("before")
    p.add_argument("after")
    p.add_argument("--metric", default=GUARD_LEAD, help="dotted path in the profile (default %s)" % GUARD_LEAD)
    p.add_argument("--stage-only", action="store_true",
                   help="KEEP on the stage metric alone, labelled stage-only; skips the delivery-outcome guardrails")
    p.add_argument("--min-gain", type=float, default=MIN_GAIN)
    p.add_argument("--min-samples", type=int, default=3, help="runs or timings needed on each side (default 3)")
    p.set_defaults(fn=cmd_compare)
    args = ap.parse_args(argv)
    if args.selftest:
        return selftest()
    if not getattr(args, "fn", None):
        ap.print_help()
        return 2
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
