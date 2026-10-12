#!/usr/bin/env python3
"""check_section_pointers.py — every "`<file>.md` **<Section>**" pointer in a skill's markdown must resolve.

A pointer names a file and a bold section title. The title must start a heading or a bold/italic span in that file, so splitting or
renaming a reference cannot silently orphan the pointers to it. The file is found by basename under the skills tree; an unknown file is a finding.
A pointer to an unknown file, with an unparseable title, or zero pointers in total is a finding. Titles are compared case-insensitively with whitespace collapsed and a trailing ellipsis/colon dropped.

USAGE
  python3 scripts/check_section_pointers.py [--selftest]
Exit codes: 0 ok; 1 dangling pointer(s) or selftest failure.
"""
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = re.compile(r"`(?:[\w./-]*/)?([\w-]+\.md)`\s+(?=\*)")
TITLE = re.compile(r"(\*{1,2})([^*\s].*?)\*{1,2}", re.S)


def norm(s):
    return re.sub(r"\s+", " ", s.replace("*", "").replace("`", "")).strip().rstrip(".…:").lower()


def leads(path):
    """Normalised heading lines and bold/italic spans (a span may wrap lines) of a file."""
    text = path.read_text(encoding="utf-8")
    out = [norm(m.group(1)) for m in re.finditer(r"^#+\s+(.*)$", text, re.M)]
    for para in re.split(r"\n\s*\n", text):  # a stray * only breaks its own paragraph
        for m in re.finditer(r"\*\*(.+?)\*\*|(?<!\*)\*([^*\n]+?)\*(?!\*)", para, re.S):
            out.append(norm(m.group(1) or m.group(2)))
    return out


def check(root, want_pointers=False):
    skills = root / ".claude" / "skills"
    by_name = {}
    for p in root.rglob("*.md"):
        if ".git" not in p.parts:
            by_name.setdefault(p.name, []).append(p)
    cache, bad, n = {}, [], 0
    for src in sorted([*skills.rglob("*.md"), *skills.rglob("evals/*.json")]):
        text = src.read_text(encoding="utf-8")
        for f in FILE.finditer(text):
            if text.rfind("\n", 0, f.start()) >= 0 and text[text.rfind("\n", 0, f.start()) + 1:f.start()].startswith("#"):
                continue  # a heading that names a file, followed by a new paragraph
            n += 1
            where = f"{src.relative_to(root)}:{text[:f.start()].count(chr(10)) + 1}"
            name = f.group(1)
            m = TITLE.match(text, f.end())
            if not m:
                bad.append(f"{where}: pointer to `{name}` has an unparseable title")
            elif len(m.group(2).split()) < (3 if len(m.group(1)) == 1 else 2):
                continue  # a lone bold word or short italics is emphasis, not a section title
            elif name not in by_name:
                bad.append(f"{where}: pointer to unknown file `{name}`")
            else:
                t = norm(m.group(2))
                if not any(l.startswith(t) for p in by_name[name] for l in cache.setdefault(p, leads(p))):
                    bad.append(f"{where}: `{name}` has no heading or bold/italic span '{m.group(2).strip()}'")
    if n == 0:
        bad.append("no section pointers found (the pattern or the tree is wrong)")
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
        (r / "b.md").write_text("see `gone.md` **Real section title**\n")
        assert len(check(Path(d))) == 1, "unknown file must fail"
        (r / "b.md").write_text("see `a.md` **Real** section\n and `a.md` *Real section title* and `a.md` ***\n")
        assert len(check(Path(d))) == 1, "italic ok, unparseable title must fail"
        (r / "b.md").write_text("see `a.md` **text in body** only\n")
        (r / "a.md").write_text("# A\n\nprose with text in body\n")
        assert len(check(Path(d))) == 1, "title in prose (not a lead) must fail"
        (r / "b.md").write_text("no pointers\n")
        assert len(check(Path(d))) == 1, "zero pointers must fail"
    print("check_section_pointers selftest: ok")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
        sys.exit(0)
    bad = check(ROOT)
    print("\n".join(bad) or "check_section_pointers: ok")
    sys.exit(1 if bad else 0)
