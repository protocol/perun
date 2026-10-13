#!/usr/bin/env python3
"""perun uninstall: undo install.sh in a target repo, using only what the install marker recorded.

Usage: python3 scripts/perun_uninstall.py [REPO] [--apply]

Default is a dry run: it prints the full plan and changes nothing. `--apply` performs it.
Source of truth is REPO/.claude/.perun-install.json (written by install.sh). Without it
nothing is removed (re-run install.sh once to write it).

Plan, built and validated before anything is touched:
  * settings.local.json is parsed first; invalid JSON aborts with no change. Only hook
    entries and env values recorded in the marker (and still equal to the recorded value)
    are removed, and the "model" key only if Perun set it. Written via temp file + rename.
  * Skill dirs: only files whose sha256 still equals the recorded install hash are removed.
    Files you added or edited are kept and listed; the dir stays if any are kept. When a
    dir is fully removed, the oldest pre-install backup (no VERSION file) is restored.
  * Slash commands in .claude/commands are removed only if install wrote them and they are unchanged.
  * delivery-lane.md is removed only if Perun created it and it is unchanged.
Leaves .bak.<ts> files and AGENTS.md blocks alone. Stdlib only.
"""
import argparse, json, os, shutil, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import perun_marker  # noqa: E402

SRC = Path(__file__).resolve().parent.parent


def plan(repo):
    """Return (ops, notes). ops = list of (description, callable). Raises ValueError before any change."""
    m = perun_marker.load(repo)
    if m is None:
        raise ValueError("no .claude/.perun-install.json marker: nothing is safe to remove (re-run install.sh to write one)")
    ops, notes = [], []
    cfg = repo / ".claude/settings.local.json"
    if cfg.is_file() and (m.get("hooks") or m.get("env") or m.get("model")):
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

        def write(c=c):
            tmp = cfg.with_name(cfg.name + ".perun-tmp")
            tmp.write_text(json.dumps(c, indent=2) + "\n")
            os.replace(tmp, cfg)
        ops.append((f"settings.local.json: remove {n} hook entr{'y' if n == 1 else 'ies'}, {envn} env value(s)" + (", model pin" if model else ""), write))
    for d, files in sorted(m.get("skills", {}).items()):
        dest = repo / d
        if not dest.is_dir():
            continue
        keep = [str(p.relative_to(dest)) for p in sorted(dest.rglob("*")) if p.is_file()
                and "__pycache__" not in p.parts and files.get(str(p.relative_to(dest))) != perun_marker.sha(p)]
        gone = [r for r in files if (dest / r).is_file() and r not in keep]

        def rm(dest=dest, gone=gone):
            for r in gone:
                (dest / r).unlink()
            for dp, _, _ in sorted(os.walk(dest), reverse=True):
                if not any(Path(dp).iterdir()):
                    Path(dp).rmdir()
            shutil.rmtree(dest / "__pycache__", ignore_errors=True)
        ops.append((f"{d}: remove {len(gone)} installed file(s)" + (f"; KEEP {len(keep)} added/edited: {', '.join(keep[:5])}" if keep else ""), rm))
        host, _, name = d.partition("/skills/")
        orig = sorted(b for b in (repo / host / "skill-backups").glob(name + "-*") if b.is_dir() and not (b / "VERSION").exists())
        if orig and not keep:
            ops.append((f"{d}: restore {orig[0].relative_to(repo)}", lambda b=orig[0], dest=dest: shutil.copytree(b, dest)))
        elif keep:
            notes.append(f"{d}: kept files, so the pre-install backup was not restored (see {host}/skill-backups)")
    for f, h in sorted(m.get("files", {}).items()):
        if (repo / f).is_file() and perun_marker.sha(repo / f) == h:
            ops.append((f"remove {f}", (repo / f).unlink))
    a = m.get("agent")
    if a and (repo / a["path"]).is_file() and perun_marker.sha(repo / a["path"]) == a["sha"]:
        ops.append((f"remove {a['path']}", (repo / a["path"]).unlink))
    return ops, notes


def finish(repo):
    for f in (".claude/.dcr-install-flags", ".claude/.dcr-install-flags.local", perun_marker.MARKER):
        (repo / f).unlink(missing_ok=True)


def run(repo, apply=False):
    """Print the plan; apply it only when apply=True. Returns the list of plan lines."""
    ops, notes = plan(repo)
    lines = [d for d, _ in ops] + notes
    if apply:
        for _, fn in ops:
            fn()
        finish(repo)
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
