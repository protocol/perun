#!/usr/bin/env python3
"""vendor_drift.py TARGET [--src DIR] — list vendored skill files in TARGET that differ from the canonical source.

WHY: a target repo's copy of a skill (`TARGET/.claude/skills/<name>/...`) silently falls behind or gets hand-edited.
Compares sha256 of every file under each canonical `<src>/<name>/` (default: this repo's `.claude/skills`) that TARGET also
vendors. Prints `DRIFT <rel>` (content differs), `MISSING <rel>` (canonical file absent from the copy) and `EXTRA <rel>`
(file only in the copy). `__pycache__`, `*.pyc` and `.DS_Store` are ignored. By default only skills TARGET has a dir for are compared;
`--skills a,b` names the skills TARGET must vendor, and one whose dir is gone prints `MISSING <name>/` (a deleted copy is drift).
A canonical file whose first line says "(install placeholder)" is hashed as `<src>/../../docs/<same name>`, the file install.sh copies over it;
when that docs file is missing it is hashed as the stub itself, so an installed full copy then reads DRIFT (fail closed).
Exit 0 = no drift, 1 = drift, a skills dir missing, or nothing compared (fail closed: zero overlap is not "clean"), 2 = usage. Read-only.
Caller: scripts/update-installed.sh runs it on each TARGET after the update and warns on drift.
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILLS = ".claude/skills"


def tree(root, docs=None):
    """{relative path: sha256}. With `docs`, a stub (first line holds "(install placeholder)") is hashed as docs/<its name> when that file exists."""
    out = {}
    for d, _, fs in os.walk(root):
        for f in fs:
            if f == ".DS_Store" or f.endswith(".pyc") or "__pycache__" in d:
                continue
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                data = fh.read()
            if docs and b"(install placeholder)" in data.split(b"\n", 1)[0] and os.path.isfile(os.path.join(docs, f)):
                with open(os.path.join(docs, f), "rb") as fh:
                    data = fh.read()
            out[os.path.relpath(p, root)] = hashlib.sha256(data).hexdigest()
    return out


def drift(target, src, want=()):
    """Drift lines for every skill under `src` that `target` vendors (plus any `want` skill it lacks); None when a skills dir is missing or nothing was compared."""
    tdir = os.path.join(target, SKILLS)
    if not (os.path.isdir(src) and os.path.isdir(tdir)):
        return None
    lines, compared = [], 0
    docs = os.path.normpath(os.path.join(src, "..", "..", "docs"))  # <canonical src root>/docs: what install.sh copies over a stub
    for name in sorted(set(want) | set(os.listdir(src))):
        if not os.path.isdir(os.path.join(src, name)):
            continue
        if not os.path.isdir(os.path.join(tdir, name)):
            if name in want:
                lines.append(f"MISSING {name}/")
            continue
        compared += 1
        a, b = tree(os.path.join(src, name), docs), tree(os.path.join(tdir, name))
        for rel in sorted(set(a) | set(b)):
            tag = "MISSING" if rel not in b else "EXTRA" if rel not in a else "DRIFT" if a[rel] != b[rel] else ""
            if tag:
                lines.append(f"{tag} {name}/{rel}")
    return lines if compared or lines else None


def main(argv):
    src = os.path.join(HERE, "..", "..")
    if "--src" in argv:
        i = argv.index("--src")
        src = argv[i + 1]
        del argv[i:i + 2]
    want = ()
    if "--skills" in argv:
        i = argv.index("--skills")
        want = [x for x in argv[i + 1].split(",") if x]
        del argv[i:i + 2]
    if len(argv) != 1:
        print("usage: vendor_drift.py TARGET [--src DIR] [--skills a,b]", file=sys.stderr)
        return 2
    d = drift(argv[0], os.path.normpath(src), want)
    if d is None:
        print("vendor_drift: skills dir missing, or no skill in common; nothing compared", file=sys.stderr)
        return 1
    print("\n".join(d) if d else "no drift")
    return 1 if d else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
