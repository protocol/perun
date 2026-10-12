#!/usr/bin/env python3
"""check_section_pointers.py — every "`<file>.md` **<Section>**" pointer in a skill's markdown must resolve.

A pointer names a file and a bold section title. The title text must appear in that file, so splitting or
renaming a reference cannot silently orphan the pointers to it. The file is found by basename under the skills tree; an unknown file is a finding.
Titles are compared case-insensitively with whitespace collapsed and a trailing ellipsis/colon dropped.

USAGE
  python3 scripts/check_section_pointers.py [--selftest]
Exit codes: 0 ok; 1 dangling pointer(s) or selftest failure.
"""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PTR = re.compile(r"`(?:[\w./-]*/)?([\w-]+\.md)`\s+\*\*([^*`]+?)\*\*")


def norm(s):
    return re.sub(r"\s+", " ", s.replace("*", "").replace("`", "")).strip().rstrip(".…:").lower()


def check(root):
    skills = root / ".claude" / "skills"
    by_name = {}
    for p in skills.rglob("*.md"):
        by_name.setdefault(p.name, []).append(p)
    cache, bad = {}, []
    for src in sorted(skills.rglob("*.md")):
        text = src.read_text(encoding="utf-8")
        for m in PTR.finditer(text):
            name, title = m.group(1), norm(m.group(2))
            if name not in by_name:
                continue  # not a skill file (e.g. README.md, CHANGELOG.md)
            if not any(title in cache.setdefault(p, norm(p.read_text(encoding="utf-8"))) for p in by_name[name]):
                bad.append(f"{src.relative_to(root)}:{text[:m.start()].count(chr(10)) + 1}: `{name}` has no section '{m.group(2).strip()}'")
    return bad


def selftest():
    with tempfile.TemporaryDirectory() as d:
        r = Path(d) / ".claude/skills/s/references"
        r.mkdir(parents=True)
        (r / "a.md").write_text("# A\n\n## Real section title here\n\n**Bold lead** text\n")
        (r / "b.md").write_text("see `a.md` **Real section title** and `a.md` **Bold lead** ok\n")
        assert check(Path(d)) == [], "good pointers must pass"
        (r / "b.md").write_text("see `a.md` **Moved section**\n")
        assert len(check(Path(d))) == 1, "dangling pointer must fail"
    print("check_section_pointers selftest: ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    bad = check(ROOT)
    print("\n".join(bad) or "check_section_pointers: ok")
    sys.exit(1 if bad else 0)
