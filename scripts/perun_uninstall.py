#!/usr/bin/env python3
"""perun uninstall: undo install.sh in a target repo, using only what the install marker recorded.

Usage: python3 scripts/perun_uninstall.py [REPO] [--apply]

Default is a dry run: it prints the full plan and changes nothing. `--apply` performs it.
Source of truth is REPO/.claude/.perun-install.json (written by install.sh). Without it
nothing is removed (re-run install.sh once to write it).

Plan, built and validated before anything is touched:
  * settings.local.json is parsed first; invalid JSON aborts with no change. Only hook
    entries, env values and sandbox/permissions values recorded in the marker (and still
    equal to the recorded value) are removed, and the "model" key only if Perun set it.
    The file itself goes if install created it and nothing else is left. Temp file + rename.
  * Skill dirs: only files whose sha256 equals a hash install itself shipped are removed.
    Files you added or edited are kept and listed; the dir stays if any are kept. When a
    dir is fully removed, your oldest pre-install copy (a backup that is not a shipped copy)
    is moved back into place, never copied over or deleted.
  * skill-backups dirs install created: removed only when every file in them is a shipped copy
    (an older release, or an identical one). Any backup with a file that is not shipped, was edited,
    or sits behind a symlink is kept and listed as "kept: user content".
  * Slash commands, house-defaults.md and settings .bak.<ts> files: removed only if install
    wrote them and they are unchanged.
  * delivery-lane.md is removed only if Perun created it and it is unchanged.
  * AGENTS.md: the blocks install wrote are cut out; the file goes if install created it and nothing else is left.
Principle: nothing is deleted unless it is provably an unmodified, shipped Perun copy inside REPO. Marker keys
with "..", an absolute path, a path that escapes REPO, or a skills/backup dir of the wrong shape abort the run
with no change. A path with a symlink in any component is skipped, never walked. Every delete is one file at a
time (never rm -rf on a computed path); only __pycache__/*.pyc under a removed dir is removed without being listed.
Emptied directories are removed last (rmdir, never recursive). Stdlib only.
"""
import argparse, json, os, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perun_marker  # noqa: E402

SRC = Path(__file__).resolve().parent.parent


SKILL_RE = re.compile(r"^\.\w[\w.-]*/skills/\w[\w.-]*$")  # names start with a word char: "." and ".." never match
BACKUP_RE = re.compile(r"^\.\w[\w.-]*/skill-backups/(\w[\w.-]*)-\d{8}-\d{6}(-\d+)?$")
# The only loose files install writes (the marker `files` and `agent` keys): anything else in a marker is forged.
OWN_FILE_RE = re.compile(r"^(\.claude/(commands/\w[\w.-]*\.md|house-defaults\.md|settings\.local\.json\.bak\.[\w.-]+|agents/delivery-lane\.md)|\.\w[\w.-]*/skills/INDEX\.md)$")


def plain(rel):
    """True for a plain relative path: a string, not absolute, no ".." part. A bad marker key aborts the whole run."""
    return isinstance(rel, str) and bool(rel) and not os.path.isabs(rel) and ".." not in Path(rel).parts


def inside(repo, rel):
    """plain() and the realpath stays under repo. A path that fails only this (a symlink leads out) is skipped, never touched."""
    if not plain(rel):
        return False
    root = os.path.realpath(repo)
    real = os.path.join(os.path.realpath((repo / rel).parent), (repo / rel).name)
    return os.path.commonpath([root, real]) == root


def safe(repo, rel):
    """inside() and no component of repo/rel is a symlink."""
    return inside(repo, rel) and perun_marker.symlink_free(repo, repo / rel)


def rmf(repo, rel):
    """Unlink one file, only when safe(); a symlinked path is left alone."""
    if safe(repo, rel):
        (repo / rel).unlink(missing_ok=True)


def strip(c, tree):
    """Inverse of perun_marker.added: drop the recorded values from settings dict c; containers it empties go too. Returns count."""
    n = 0
    for k, v in tree.items():
        if k not in c:
            continue
        before = n
        if isinstance(v, dict) and isinstance(c[k], dict):
            n += strip(c[k], v)
        elif isinstance(v, list) and isinstance(c[k], list):
            keep = [x for x in c[k] if x not in v]
            n += len(c[k]) - len(keep)
            c[k] = keep
        elif c[k] == v:
            del c[k]
            n += 1
            continue
        if n > before and c[k] in ({}, []):
            del c[k]
    return n


def sweep(repo, rel):
    """rmdir the empty dirs under repo/rel, deepest first. Never follows a symlink: does nothing when rel or a parent is one."""
    if not safe(repo, rel):
        return
    for dp, _, _ in sorted(os.walk(repo / rel, followlinks=False), reverse=True):
        if not any(Path(dp).iterdir()):
            Path(dp).rmdir()


def prune_empty(repo, rels):
    """rmdir (never recursive) each path and its parents up to, not including, repo while they are empty. Skips a path with a symlink in it."""
    for rel in rels:
        p = repo / rel
        if not perun_marker.symlink_free(repo, p):
            continue
        while p != repo and p.is_relative_to(repo):
            try:
                p.rmdir()
            except FileNotFoundError:
                pass
            except OSError:
                break
            p = p.parent


def plan(repo):
    """Return (ops, notes). ops = list of (description, callable). Raises ValueError before any change."""
    m = perun_marker.load(repo)
    if m is None:
        raise ValueError("no .claude/.perun-install.json marker: nothing is safe to remove (re-run install.sh to write one)")
    ops, notes = [], []
    rels = [*m.get("files", {})] + [d + "/" + f for d, fs in m.get("skills", {}).items() for f in fs]
    if m.get("agent"):
        rels.append(m["agent"]["path"])
    bad = [r for r in rels if not plain(r)]
    bad += [d for d in m.get("skills", {}) if not (plain(d) and SKILL_RE.match(d))]
    bad += [d for d in m.get("backups", []) if not (plain(d) and BACKUP_RE.match(d))]
    bad += [f for f in [*m.get("files", {}), *([m["agent"]["path"]] if m.get("agent") else [])] if not (plain(f) and OWN_FILE_RE.match(f))]
    if bad:
        raise ValueError(f"marker lists a path outside {repo} or not a skills/backup dir ({bad[0]}); nothing changed")
    # Only hashes install recorded as shipped count. A marker without them proves nothing, so every file is kept.
    shipped = {n: {f: set(hs) for f, hs in fs.items()} for n, fs in m.get("shipped", {}).items()}

    def backup_files(rel):
        """Files of a backup dir when it is a real, symlink-free dir, else None."""
        b = repo / rel
        ents = perun_marker._entries(b) if b.is_dir() and safe(repo, rel) else None
        return None if ents is None else [e for e in ents if (b / e).is_file()]

    def is_shipped(rel):
        """True only when every file in the backup is a byte-identical shipped copy (and there is nothing else in it)."""
        name, files = BACKUP_RE.match(rel).group(1), backup_files(rel)
        return files is not None and all(f in shipped.get(name, {}) and perun_marker.sha(repo / rel / f) in shipped[name][f] for f in files)

    cfg = repo / ".claude/settings.local.json"
    if cfg.is_file() and not safe(repo, ".claude/settings.local.json"):
        notes.append(".claude/settings.local.json: kept: symlink in path, not touched")
    elif cfg.is_file() and (m.get("hooks") or m.get("env") or m.get("model") or m.get("autocompact") or m.get("statusline") or m.get("settings") or m.get("settings_created")):
        try:
            c = json.loads(cfg.read_text())
        except ValueError as e:
            raise ValueError(f"{cfg} is not valid JSON ({e}); fix it first, nothing changed")
        n = 0
        for item in m.get("hooks", []):
            have = c.get("hooks", {}).get(item["event"], [])
            if item["entry"] in have:
                have.remove(item["entry"]); n += 1
                if not have:
                    del c["hooks"][item["event"]]
        if "hooks" in c and not c["hooks"]:
            del c["hooks"]
        envn = 0
        for k, v in m.get("env", {}).items():
            if c.get("env", {}).get(k) == v:
                del c["env"][k]; envn += 1
        if "env" in c and not c["env"]:
            del c["env"]
        model = bool(m.get("model")) and c.get("model") == m["model"]
        if model:
            del c["model"]
        if m.get("autocompact") and c.get("autoCompactWindow") == m["autocompact"]:
            del c["autoCompactWindow"]
        if m.get("statusline") and c.get("statusLine") == m["statusline"]:
            del c["statusLine"]
        sn = strip(c, m.get("settings", {}))

        def write(c=c):
            if not c and m.get("settings_created"):
                cfg.unlink()
                return
            tmp = cfg.with_name(cfg.name + ".perun-tmp")
            tmp.write_text(json.dumps(c, indent=2) + "\n")
            os.replace(tmp, cfg)
        ops.append((f"settings.local.json: remove {n} hook entr{'y' if n == 1 else 'ies'}, {envn} env value(s), {sn} sandbox/permissions value(s)" + (", model pin" if model else ""), write))
    restored = set()
    for d, files in sorted(m.get("skills", {}).items()):
        dest, name = repo / d, d.rsplit("/", 1)[-1]
        if dest.is_symlink() and os.readlink(dest) == f"../../.claude/skills/{name}":  # install's host link to the canonical copy
            ops.append((f"{d}: remove symlink to the .claude copy", dest.unlink))
            continue
        if dest.is_symlink() or (dest.exists() and not safe(repo, d)):
            notes.append(f"{d}: kept: symlink in path, not touched")
            continue
        if not dest.is_dir():
            continue
        keep, gone = [], []
        for dp, dn, fn in os.walk(dest, followlinks=False):  # a symlinked dir is listed but never descended
            for n in fn + dn:
                q = Path(dp) / n
                if "__pycache__" in q.parts or not (q.is_symlink() or q.is_file()):
                    continue
                r = str(q.relative_to(dest))
                ok = not q.is_symlink() and files.get(r) == perun_marker.sha(q) and perun_marker.sha(q) in shipped.get(name, {}).get(r, ())
                (gone if ok else keep).append(r)
        gone.sort(); keep.sort()

        def rm(dest=dest, gone=gone, d=d):
            for r in gone:
                rmf(repo, f"{d}/{r}")
            for pyc in sorted(dest.rglob("__pycache__/*.pyc")):  # bytecode a skill run left behind: not in the marker, so not listed
                rmf(repo, str(pyc.relative_to(repo)))
            sweep(repo, d)
        ops.append((f"{d}: remove {len(gone)} installed file(s)" + (f"; KEEP {len(keep)} added/edited: {', '.join(keep[:5])}" if keep else ""), rm))
        host = d.partition("/skills/")[0]
        mine = [str(b.relative_to(repo)) for b in sorted((repo / host / "skill-backups").glob(name + "-*")) if b.is_dir() and BACKUP_RE.match(str(b.relative_to(repo)))]
        pre = m.get("preinstall", [])  # no list (an older marker): nothing is provably pre-install, so nothing is moved back
        orig = [b for b in mine if BACKUP_RE.match(b).group(1) == name and backup_files(b) is not None and b in pre]
        if orig and not keep:
            restored.add(orig[0])

            def back(b=orig[0], dest=dest):
                if not dest.exists():  # the removal above emptied it; if anything is left there, the backup stays where it is
                    os.rename(repo / b, dest)
            ops.append((f"{d}: restore your pre-install copy from {orig[0]} (moved back, not copied)", back))
        elif keep:
            notes.append(f"{d}: kept files, so the pre-install backup was not restored (see {host}/skill-backups)")
    for d in m.get("backups", []):
        if not (repo / d).is_dir() and not (repo / d).is_symlink():
            continue
        if d in restored:
            continue
        files = backup_files(d)
        if files is None or not is_shipped(d):
            notes.append(f"{d}: kept: user content (not a shipped copy, edited, or behind a symlink)")
            continue

        def rmb(d=d, files=files):
            for r in files:
                rmf(repo, f"{d}/{r}")
            for pyc in sorted((repo / d).rglob("__pycache__/*.pyc")):
                rmf(repo, str(pyc.relative_to(repo)))
            sweep(repo, d)
        ops.append((f"{d}: remove {len(files)} shipped backup file(s)", rmb))
    for f, h in sorted(m.get("files", {}).items()):
        if safe(repo, f) and (repo / f).is_file() and perun_marker.sha(repo / f) == h:
            ops.append((f"remove {f}", lambda f=f: rmf(repo, f)))
    a = m.get("agent")
    if a and safe(repo, a["path"]) and (repo / a["path"]).is_file() and perun_marker.sha(repo / a["path"]) == a["sha"]:
        ops.append((f"remove {a['path']}", lambda a=a: rmf(repo, a["path"])))
    am, ag = m.get("agents_md"), repo / "AGENTS.md"
    if am and ag.is_file() and not safe(repo, "AGENTS.md"):
        notes.append("AGENTS.md: kept: symlink in path, not touched")
    elif am and ag.is_file():
        text = new = ag.read_text()
        for b in am["blocks"]:
            new = re.sub(rf"\n?^<!-- {re.escape(b)}:begin -->\n.*?^<!-- {re.escape(b)}:end -->\n?", "", new, flags=re.S | re.M)
        if new != text:
            whole = am["created"] and new.strip() == "# AGENTS.md"

            def cut(new=new, whole=whole):
                ag.unlink() if whole else ag.write_text(new)
            ops.append((f"AGENTS.md: remove {len(am['blocks'])} Perun block(s)" + (" (and the file, install created it)" if whole else ""), cut))
    pol = ".perun/policy.json"
    if m.get("policy_role") and safe(repo, pol) and (repo / pol).is_file():  # undo only what install armed, and only while the file is still byte-for-byte what install wrote
        if perun_marker.sha(repo / pol) != m.get("policy_sha"):
            notes.append(f"{pol}: kept: changed since install, so the role it armed is not provably install's")
        else:
            def unarm(f=repo / pol):
                c = json.loads(f.read_text())
                del c["role"]
                if m["policy_role"] != "created":  # "created": install wrote the whole file (sha matches), so all of it goes
                    f.write_text(json.dumps(c, indent=2) + "\n")
                else:
                    f.unlink()
            ops.append((".perun/policy.json: undo the role=ceo install armed (the file too if install created it)", unarm))
    return ops, notes


def finish(repo, m):
    for f in (".claude/.dcr-install-flags", ".claude/.dcr-install-flags.local", perun_marker.MARKER):
        rmf(repo, f)
    prune_empty(repo, [*m.get("skills", {}), *(d.partition("/skills/")[0] + "/skill-backups" for d in m.get("skills", {})), *m.get("backups", []), *m.get("files", {}), ".claude/agents", ".claude", ".perun"])


def run(repo, apply=False):
    """Print the plan; apply it only when apply=True. Returns the list of plan lines."""
    ops, notes = plan(repo)
    lines = [d for d, _ in ops] + notes
    if apply:
        m = perun_marker.load(repo)
        for _, fn in ops:
            fn()
        finish(repo, m)
    return lines


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("repo", nargs="?", default=".")
    ap.add_argument("--apply", action="store_true", help="perform the plan (default: print it only)")
    a = ap.parse_args()
    repo = Path(a.repo).resolve()
    if repo == SRC:
        sys.exit("error: target is the checkout itself")
    try:
        out = run(repo, a.apply)
    except ValueError as e:
        sys.exit(f"error: {e}")
    print("\n".join(("" if a.apply else "would: ") + l for l in out) or "nothing to undo")
    if not a.apply:
        print("dry run: nothing changed; re-run with --apply to do it")
