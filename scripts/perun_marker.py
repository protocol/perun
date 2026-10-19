#!/usr/bin/env python3
"""Install marker: what install.sh itself added to a repo, so uninstall removes only that.

Usage (called by install.sh): perun_marker.py TARGET --dirs REL... [--pre FILE --template FILE] [--agent-created] [--files REL...] [--backups REL...] [--agents-block NAME...] [--agents-created] [--settings-created] [--version V] [--remote URL]
       perun_marker.py backup-ok TARGET BACKUP_ROOT      (exit 1 when BACKUP_ROOT or a parent below TARGET is a symlink)
       perun_marker.py dedupe BACKUP_ROOT NEW DEST       (drop NEW only when identical to the installed DEST)

Writes TARGET/.claude/.perun-install.json, merged with any previous marker:
  skills: {<host>/skills/<name>: {<file>: sha256}}  hashes of the copy just installed
  hooks:  [{event, entry}]  operating-layer entries absent before this install
  env:    {key: value}      env keys absent before this install
  model:  "sonnet" | null   set only when the settings had no "model" before
  autocompact: 200000       set only when the settings had no "autoCompactWindow" before
  statusline: {type, command}  the cost statusLine, set only when the settings had no "statusLine" before
  files:  {<rel>: sha256}  slash commands, house-defaults.md and settings .bak files install wrote fresh (never pre-existing files)
  backups: [<rel dir>]  skill-backups dirs this install created (still on disk); never deleted unless every file is a shipped copy
  preinstall: [<rel dir>]  the backups that hold what was in a skill dir before Perun first wrote it (uninstall moves one back)
  shipped: {<skill>: {<file>: [sha256]}}  every hash install itself copied in, per release: the only content uninstall may delete
  settings: {sandbox, permissions}  only the values the operating layer added (nested; lists hold the added items)
  settings_created: true when install created settings.local.json
  agents_md: {blocks: [name], created: bool}  AGENTS.md blocks install wrote, and whether it created the file
  agent:  {path, sha} | null  delivery-lane.md when install created it
  version, remote             the installed release and where it came from (perun_auto_update.py)
Stdlib only.
"""
import argparse, hashlib, json, os, re, sys
from pathlib import Path

MARKER = ".claude/.perun-install.json"


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def hash_dir(d):
    return {str(p.relative_to(d)): sha(p) for p in sorted(Path(d).rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def load(target):
    f = Path(target) / MARKER
    return json.loads(f.read_text()) if f.is_file() else None


def added(have, tpl):
    """What template `tpl` contributes that `have` lacks: dicts recurse, lists keep missing items, an existing scalar wins."""
    if isinstance(tpl, dict):
        out = {k: a for k, v in tpl.items() if (a := added(have.get(k) if isinstance(have, dict) else None, v)) not in (None, {}, [])}
        return out
    if isinstance(tpl, list):
        return [x for x in tpl if x not in (have if isinstance(have, list) else [])]
    return tpl if have is None else None


def merge(a, b):
    """Union of two `added` trees (marker memory across re-runs)."""
    if isinstance(a, dict) and isinstance(b, dict):
        return {k: merge(a.get(k), b.get(k)) if k in a and k in b else a.get(k, b.get(k)) for k in {**a, **b}}
    if isinstance(a, list) and isinstance(b, list):
        return a + [x for x in b if x not in a]
    return b


def _entries(d, pycache=False):
    """Every entry under d as relative paths (None when any entry is a symlink: never trusted, never walked through).
    __pycache__ entries are left out unless pycache=True."""
    out = []
    for dp, dn, fn in os.walk(d, followlinks=False):
        for n in dn + fn:
            if (Path(dp) / n).is_symlink():
                return None
            out.append(str((Path(dp) / n).relative_to(d)))
    return sorted(x for x in out if pycache or "__pycache__" not in Path(x).parts)


def symlink_free(root, path):
    """True when no component of `path` below `root` (and `path` itself) is a symlink."""
    root, p = Path(root), Path(path)
    try:
        parts = p.relative_to(root).parts
    except ValueError:
        return False
    return not any((root.joinpath(*parts[:i + 1])).is_symlink() for i in range(len(parts)))


def drop_identical_backup(root, new, dest):
    """Remove the fresh backup `new` only when it is provably the shipped copy: byte-identical to the just-installed `dest`
    (same entries, same sha256), with no symlink in either tree or anywhere on the path. Anything else stays. Returns a status line."""
    root, new, dest = Path(root), Path(new), Path(dest)
    if not (symlink_free(root, new) and new.is_dir() and dest.is_dir() and not dest.is_symlink()):
        return "backup: kept (symlink or unexpected path)"
    ne, de = _entries(new, True), _entries(dest, True)  # every entry counts, __pycache__ included
    if ne is None or de is None or ne != de or any((new / e).is_file() != (dest / e).is_file() or ((new / e).is_file() and sha(new / e) != sha(dest / e)) for e in ne):
        return "backup: kept (differs from the installed copy)"
    for f in sorted(new.rglob("*"), reverse=True):  # files first, then dirs, one at a time; the walk above proved no symlinks
        (f.rmdir if f.is_dir() else f.unlink)()
    new.rmdir()
    return "backup: identical to the installed copy, not kept"


def _skill_of(backup):
    """host/skill-backups/<name>-<timestamp> -> host/skills/<name> (None when it does not look like one)."""
    m = re.match(r"^(.*)/skill-backups/(.+)-\d{8}-\d{6}(-\d+)?$", backup)
    return f"{m.group(1)}/skills/{m.group(2)}" if m else None


def record(target, dirs, pre=None, template=None, agent_created=False, files=(), version=None, remote=None, backups=(), agents_blocks=(), agents_created=False, settings_created=False):
    target = Path(target)
    m = load(target) or {}
    m.update({k: v for k, v in (("version", version), ("remote", remote)) if v})
    first = {d for d in dirs if d not in m.get("skills", {})}  # skill dirs Perun had never written before this run
    m.setdefault("skills", {}).update({d: hash_dir(target / d) for d in dirs if (target / d).is_dir()})
    for d in dirs:  # the copy install just wrote is the shipped release: remember its hashes (never the hashes of whatever was there before)
        if (target / d).is_dir() and not (target / d).is_symlink():
            for f, h in hash_dir(target / d).items():
                sh = m.setdefault("shipped", {}).setdefault(d.rsplit("/", 1)[-1], {}).setdefault(f, [])
                if h not in sh:
                    sh.append(h)
    m.setdefault("hooks", []); m.setdefault("env", {}); m.setdefault("model", None); m.setdefault("agent", None)
    cfg = target / ".claude/settings.local.json"
    if pre and template and cfg.is_file():
        before, now, t = (json.loads(Path(x).read_text()) for x in (pre, cfg, template))
        for ev, entries in t.get("hooks", {}).items():
            for e in entries:
                if "<" in (e.get("matcher") or ""):
                    continue
                item = {"event": ev, "entry": e}
                if e not in before.get("hooks", {}).get(ev, []) and e in now.get("hooks", {}).get(ev, []) and item not in m["hooks"]:
                    m["hooks"].append(item)
        for k, v in t.get("env", {}).items():
            if k not in before.get("env", {}) and now.get("env", {}).get(k) == v:
                m["env"][k] = v
        if "model" not in before and now.get("model") == "sonnet":
            m["model"] = "sonnet"
        if "autoCompactWindow" not in before and now.get("autoCompactWindow") == 200000:
            m["autocompact"] = 200000
        if "statusLine" not in before and t.get("statusLine") and now.get("statusLine") == t["statusLine"]:
            m["statusline"] = t["statusLine"]
        for k in ("sandbox", "permissions"):
            if k in t and (a := added(before.get(k), t[k])):
                m.setdefault("settings", {})[k] = merge(m.get("settings", {}).get(k, {}), a)
    if settings_created:
        m["settings_created"] = True
    if agents_blocks:
        am = m.setdefault("agents_md", {"blocks": [], "created": False})
        am["blocks"] += [b for b in agents_blocks if b not in am["blocks"]]
        am["created"] = am["created"] or agents_created
    m["backups"] = sorted(d for d in {*m.get("backups", []), *backups} if (target / d).is_dir())
    pre = {b for b in backups if _skill_of(b) in first}
    m["preinstall"] = sorted(b for b in {*m.get("preinstall", []), *pre} if b in m["backups"])
    m.setdefault("files", {}).update({f: sha(target / f) for f in files if (target / f).is_file()})
    agent = target / ".claude/agents/delivery-lane.md"
    if agent_created and agent.is_file():
        m["agent"] = {"path": ".claude/agents/delivery-lane.md", "sha": sha(agent)}
    out = target / MARKER
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(m, indent=2) + "\n")
    return m


if __name__ == "__main__":
    if sys.argv[1:2] == ["backup-ok"]:
        sys.exit(0 if symlink_free(sys.argv[2], sys.argv[3]) else 1)
    if sys.argv[1:2] == ["dedupe"]:
        print(drop_identical_backup(*sys.argv[2:5]))
        sys.exit(0)
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--dirs", nargs="*", default=[])
    ap.add_argument("--files", nargs="*", default=[])
    ap.add_argument("--pre")
    ap.add_argument("--template")
    ap.add_argument("--agent-created", action="store_true")
    ap.add_argument("--backups", nargs="*", default=[])
    ap.add_argument("--agents-block", nargs="*", default=[])
    ap.add_argument("--agents-created", action="store_true")
    ap.add_argument("--settings-created", action="store_true")
    ap.add_argument("--version")
    ap.add_argument("--remote")
    a = ap.parse_args()
    record(a.target, a.dirs, a.pre, a.template, a.agent_created, a.files, a.version, a.remote, a.backups, a.agents_block, a.agents_created, a.settings_created)
