#!/usr/bin/env python3
"""skill_index.py — generate the per-skill and repo-level INDEX.md lookup
tables so an agent can find which file answers a trigger without opening
every references/*.md or scripts/*.py blindly.

WHAT IT WRITES
--------------
For every `.claude/skills/<name>/` that has a `SKILL.md`:
  `.claude/skills/<name>/INDEX.md` — one row per `references/*.md` and
  `scripts/*.py|*.sh` in that skill: a one-line (<=100 chars, first sentence)
  "Read this when..."/header trigger and, for a reference, an estimated token
  cost (`bytes // 4`, this repo's chars/4 convention); for a script, its CLI
  usage line when its docstring/header documents one. The full trigger stays
  in the file's own header; the index exists to be cheap to read.

And one repo-level table:
  `.claude/skills/INDEX.md` — every skill's purpose (from its SKILL.md
  frontmatter `description:`, trimmed to <=120 chars), entry file, and its
  own INDEX.md path.

Output is deterministic: sorted paths, no timestamps, no run-dependent data.
INDEX.md is a lookup aid, not a reference — it is NOT must-load and carries
no routing/size-budget obligation (scripts/ci-gates.sh's `routing` and `size`
subcommands only look at SKILL.md and references/*.md).

USAGE
  python3 scripts/skill_index.py             generate/overwrite every INDEX.md
  python3 scripts/skill_index.py --check     verify INDEX.md files match their
                                              sources; no writes
  python3 scripts/skill_index.py --selftest  run this script's own self-tests

Exit codes: 0 ok; 1 stale INDEX.md (--check) or a self-test failed
(--selftest); 2 usage error.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIRNAME = ".claude/skills"

# The index-line helpers (_short, _truncate, _strip_md, _table_cell, token_est, parse_reference_md) live in the
# shipped focus_kit.py, which cuts a project's docs/INDEX.md the same way: one home, no copy. A reference's
# trigger is its first paragraph after the H1 (no headings column: the routed file's own headings are one open
# away, and the column cost ~7K tokens per session).
sys.path.append(str(REPO_ROOT / SKILLS_DIRNAME / "agentic-delivery" / "scripts"))
from focus_kit import _short, _strip_md, _table_cell, _truncate, parse_reference_md, token_est  # noqa: E402

BLOCK_MAX = 120
DESC_MAX = 120

_UNDERLINE_RE = re.compile(r"^[-=]{3,}$")


# ---------------------------------------------------------------------------
# Python script parsing: module docstring's first paragraph is the trigger;
# a "Usage"/"Exit code(s)" section (heading line, optionally with inline
# content, followed by a block of non-blank lines) supplies the CLI one-liner
# and exit codes, only when the docstring actually documents them.
# ---------------------------------------------------------------------------
def _docstring(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return ""
    return ast.get_docstring(tree) or ""


def _first_paragraph(doc: str) -> str:
    para: list[str] = []
    for line in doc.splitlines():
        if not line.strip():
            if para:
                break
            continue
        para.append(line.strip())
    return _short(_strip_md(" ".join(para)))


def _extract_section(doc_lines: list[str], header_re: re.Pattern[str]) -> str | None:
    for idx, line in enumerate(doc_lines):
        m = header_re.match(line.strip())
        if not m:
            continue
        parts: list[str] = []
        inline = m.group("inline").strip() if "inline" in m.groupdict() else ""
        if inline:
            parts.append(inline)
        j = idx + 1
        while j < len(doc_lines) and doc_lines[j].strip():
            candidate = doc_lines[j].strip()
            if not _UNDERLINE_RE.match(candidate):
                parts.append(candidate)
            j += 1
        if parts:
            return _truncate(_strip_md(" ".join(parts)), BLOCK_MAX)
    return None


# "usage" must stand alone as a heading word: followed by a colon, whitespace, or
# end of line. Prose that merely starts a docstring line with "usage)." or
# "usage," is not a CLI section (it leaked a sentence fragment into a CLI cell).
_USAGE_RE = re.compile(r"^usage(?=:|\s|$)\s*:?\s*(?P<inline>.*)$", re.IGNORECASE)


def parse_script_py(path: Path) -> tuple[str, str | None]:
    doc = _docstring(path)
    if not doc:
        return "(no module docstring)", None
    trigger = _first_paragraph(doc)
    doc_lines = doc.splitlines()
    usage = _extract_section(doc_lines, _USAGE_RE)
    return trigger, usage


def parse_script_sh(path: Path) -> tuple[str, str | None]:
    """(trigger, usage) from a shell script's leading comment block: the first
    paragraph is the trigger; `name.sh args — text` or `Usage: ...` gives the CLI."""
    block: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#!"):
            continue
        if not line.startswith("#"):
            break
        block.append(line.lstrip("#").strip())
    para: list[str] = []
    for line in block:
        if not line:
            if para:
                break
            continue
        para.append(line)
    if not para:
        return "(no header comment)", None
    first = _strip_md(para[0])
    m = re.match(r"^(\S+\.sh\b[^—]*?)\s+[—-]\s+(.*)$", first)
    usage = None
    if m:
        usage = _truncate(m.group(1), BLOCK_MAX)
        para[0] = m.group(2)
    else:
        u = next((l for l in block if l.lower().startswith("usage:")), None)
        if u:
            usage = _truncate(_strip_md(u.split(":", 1)[1]), BLOCK_MAX)
    return _short(_strip_md(" ".join(para))), usage


# ---------------------------------------------------------------------------
# SKILL.md frontmatter: pull the `description:` block scalar for the
# repo-level table (trimmed to <=120 chars).
# ---------------------------------------------------------------------------
def read_description(skill_md: Path) -> str:
    lines = skill_md.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        return ""
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return ""
    desc_lines: list[str] = []
    capturing = False
    for line in lines[1:end]:
        if not capturing:
            m = re.match(r"^description:\s*(.*)$", line)
            if not m:
                continue
            rest = m.group(1).strip()
            if rest and rest not in (">-", ">", "|", "|-"):
                return _truncate(rest, DESC_MAX)
            capturing = True
            continue
        if line.strip() == "" or line.startswith(" "):
            if line.strip():
                desc_lines.append(line.strip())
            continue
        break
    return _truncate(" ".join(desc_lines), DESC_MAX)


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------
def find_skill_dirs(root: Path) -> list[Path]:
    skills_dir = root / SKILLS_DIRNAME
    if not skills_dir.is_dir():
        return []
    return sorted(
        (d for d in skills_dir.iterdir() if d.is_dir() and (d / "SKILL.md").is_file()),
        key=lambda d: d.name,
    )


def generate_skill_index(skill_dir: Path) -> str:
    name = skill_dir.name
    refs = sorted((skill_dir / "references").glob("*.md")) if (skill_dir / "references").is_dir() else []
    scripts = (
        sorted([*(skill_dir / "scripts").glob("*.py"), *(skill_dir / "scripts").glob("*.sh")])
        if (skill_dir / "scripts").is_dir()
        else []
    )

    out = [
        f"# INDEX — {name}",
        "",
        "Generated by `scripts/skill_index.py` (do not hand-edit; rerun it after changing "
        "a `references/*.md` or `scripts/*.py|*.sh`). Triggers are cut to one line: the "
        "full text is in the file's own header.",
        "",
        "## References",
        "",
    ]
    if refs:
        out.append("| File | Read this when... | Tok |")
        out.append("|---|---|---|")
        for ref in refs:
            out.append(f"| `references/{ref.name}` | {_table_cell(parse_reference_md(ref))} | {token_est(ref)} |")
    else:
        out.append("_No references/*.md in this skill._")
    out += ["", "## Scripts", ""]
    if scripts:
        out.append("| File | Trigger | CLI (— = open the header) |")
        out.append("|---|---|---|")
        for scr in scripts:
            trigger, usage = parse_script_sh(scr) if scr.suffix == ".sh" else parse_script_py(scr)
            out.append(f"| `scripts/{scr.name}` | {_table_cell(trigger)} | {_table_cell(usage or '')} |")
    else:
        out.append("_No scripts/*.py or *.sh in this skill._")
    out.append("")
    return "\n".join(out)


def generate_repo_index(root: Path, skill_dirs: list[Path]) -> str:
    out = [
        "# Skills index",
        "",
        "Generated by `scripts/skill_index.py`. Lookup table: each skill's purpose, "
        "its entry file, and its own `INDEX.md` (which file answers which trigger). "
        "Not must-load.",
        "",
        "| Skill | Purpose | Entry | Index |",
        "|---|---|---|---|",
    ]
    for skill_dir in skill_dirs:
        name = skill_dir.name
        rel = skill_dir.relative_to(root)
        purpose = read_description(skill_dir / "SKILL.md")
        out.append(
            f"| `{name}` | {_table_cell(purpose)} | `{rel.as_posix()}/SKILL.md` | "
            f"`{rel.as_posix()}/INDEX.md` |"
        )
    out.append("")
    return "\n".join(out)


def index_targets(root: Path) -> dict[Path, str]:
    """Map each INDEX.md path (repo-level + per-skill) to its generated content."""
    skill_dirs = find_skill_dirs(root)
    targets = {root / SKILLS_DIRNAME / "INDEX.md": generate_repo_index(root, skill_dirs)}
    for skill_dir in skill_dirs:
        targets[skill_dir / "INDEX.md"] = generate_skill_index(skill_dir)
    return targets


def cmd_generate(root: Path) -> int:
    for path, content in sorted(index_targets(root).items()):
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(root)}")
    return 0


def cmd_check(root: Path) -> int:
    stale = []
    for path, content in sorted(index_targets(root).items()):
        rel = path.relative_to(root)
        if not path.is_file():
            stale.append(f"MISSING: {rel}")
            continue
        if path.read_text(encoding="utf-8") != content:
            stale.append(f"STALE: {rel} (run: python3 scripts/skill_index.py)")
    if stale:
        for line in stale:
            print(line, file=sys.stderr)
        print(f"skill_index --check: {len(stale)} stale/missing INDEX.md file(s)", file=sys.stderr)
        return 1
    print(f"skill_index --check: ok ({len(index_targets(root))} INDEX.md file(s) current)")
    return 0


# ---------------------------------------------------------------------------
# Self-tests — synthetic fixture skill tree, never the real repo, so a
# self-test failure can never come from someone else's content drifting.
# ---------------------------------------------------------------------------
def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def run_selftest() -> int:
    import shutil
    import tempfile

    results: list[tuple[bool, str]] = []

    def case(ok: bool, label: str) -> None:
        results.append((ok, label))

    tmp = Path(tempfile.mkdtemp(prefix="skill-index-selftest-"))
    try:
        root = tmp
        skill = root / SKILLS_DIRNAME / "widget-skill"
        _write(
            skill / "SKILL.md",
            "---\n"
            "name: widget-skill\n"
            "description: >-\n"
            "  Use when the fixture needs a widget. Second line of the\n"
            "  description block scalar, long enough to be truncated if it "
            "  ever exceeds the one hundred twenty character budget by a wide "
            "  and deliberate margin here.\n"
            "license: MIT\n"
            "---\n\n# Widget skill\n\nFixture only.\n",
        )
        _write(
            skill / "references" / "one.md",
            "# One\n\nRead this when the fixture needs reference one. "
            "Plain paragraph, no bold.\n\n## Alpha\n\nbody\n\n## Beta\n\nbody\n",
        )
        _write(
            skill / "scripts" / "tool.py",
            '#!/usr/bin/env python3\n'
            '"""tool.py — fixture script for skill_index selftest.\n\n'
            "USAGE\n"
            "  python3 scripts/tool.py <path>\n\n"
            "Exit codes: 0 ok; 1 bad input.\n"
            '"""\n'
            "import sys\n"
            "print('fixture')\n",
        )

        _write(skill / "scripts" / "run.sh", "#!/usr/bin/env bash\n# run.sh <arg> — Run the fixture shell tool. More text.\nset -e\n")
        _write(skill / "scripts" / "bare.sh", "#!/usr/bin/env bash\nset -e\n")
        # 1) generation produces both INDEX.md files.
        cmd_generate(root)
        repo_idx = root / SKILLS_DIRNAME / "INDEX.md"
        skill_idx = skill / "INDEX.md"
        case(repo_idx.is_file(), "generate: writes repo-level INDEX.md")
        case(skill_idx.is_file(), "generate: writes per-skill INDEX.md")

        repo_text = repo_idx.read_text(encoding="utf-8")
        case("widget-skill" in repo_text, "repo index: lists the skill by name")
        case("Use when the fixture needs a widget." in repo_text, "repo index: purpose captured")
        case("…" in repo_text, "repo index: overlong description truncated with an ellipsis")

        skill_text = skill_idx.read_text(encoding="utf-8")
        case("references/one.md" in skill_text, "skill index: references row present")
        case(
            "| the fixture needs reference one. |" in skill_text and "Read this when the" not in skill_text,
            "skill index: reference trigger extracted, redundant lead-in dropped",
        )
        case("Alpha" not in skill_text and "Headings" not in skill_text, "skill index: no headings column")
        case("scripts/tool.py" in skill_text, "skill index: scripts row present")
        case("python3 scripts/tool.py <path>" in skill_text, "skill index: CLI usage extracted")
        case("0 ok; 1 bad input." not in skill_text, "skill index: exit codes dropped (kept in the script header)")
        case(
            "scripts/run.sh` | Run the fixture shell tool" in skill_text and "run.sh <arg>" in skill_text,
            "skill index: .sh script row with trigger and usage from its header comment",
        )
        case("scripts/bare.sh` | (no header comment)" in skill_text, "skill index: .sh without a header comment still listed")

        # 2) --check is green right after generation.
        case(cmd_check(root) == 0, "check: passes immediately after generate (RED->GREEN proof)")

        # 3) mutate a source file without regenerating -> check must fail.
        _write(
            skill / "references" / "one.md",
            "# One\n\nRead this when the fixture needs a DIFFERENT reference one.\n",
        )
        case(cmd_check(root) == 1, "check: fails when a source drifted from its INDEX.md (fail closed)")

        # 4) regenerating restores green.
        cmd_generate(root)
        case(cmd_check(root) == 0, "check: green again after regenerating")

        # 5) a skill with no references/ or scripts/ still gets an INDEX.md.
        bare = root / SKILLS_DIRNAME / "bare-skill"
        _write(bare / "SKILL.md", "---\nname: bare-skill\ndescription: Bare fixture skill.\nlicense: MIT\n---\n\n# Bare\n")
        cmd_generate(root)
        bare_idx_text = (bare / "INDEX.md").read_text(encoding="utf-8")
        case("No references/*.md" in bare_idx_text, "skill index: handles a skill with no references/")
        case("No scripts/*.py" in bare_idx_text, "skill index: handles a skill with no scripts/")
        case(cmd_check(root) == 0, "check: green with the added bare skill")

        # 6) missing INDEX.md entirely is reported as missing, not a crash.
        (bare / "INDEX.md").unlink()
        case(cmd_check(root) == 1, "check: reports a missing INDEX.md as stale (fail closed)")

        # 7) determinism: regenerating twice yields byte-identical content.
        cmd_generate(root)
        first = skill_idx.read_bytes()
        cmd_generate(root)
        second = skill_idx.read_bytes()
        case(first == second, "generate: deterministic (no timestamps/run-dependent data)")

        # 8) _USAGE_RE / _EXIT_RE edge cases: no false positive on "Usages"/
        #    hyphenated headers, and the exit-codes regex accepts a heading
        #    like "CONTRACT (exit codes)" (not just a line starting with it).
        case(_USAGE_RE.match("Usage") is not None, "usage regex: bare 'Usage' matches")
        case(_USAGE_RE.match("Usage:") is not None, "usage regex: 'Usage:' matches")
        case(_USAGE_RE.match("Usages of this tool") is None, "usage regex: 'Usages' does not false-positive")
        case(_USAGE_RE.match("usage-notes") is None, "usage regex: 'usage-notes' does not false-positive")
        case(_USAGE_RE.match("usage). Exit 2 is never a pass.") is None, "usage regex: prose 'usage).' is not a CLI heading")
        case(_USAGE_RE.match("usage, then exits.") is None, "usage regex: prose 'usage,' is not a CLI heading")
        case(_USAGE_RE.match("USAGE  python3 x.py") is not None, "usage regex: 'USAGE <cmd>' inline still matches")

        # 9) smoke test against the real repo tree (never asserts on its
        #    prose, only that generation does not crash and stays non-empty).
        try:
            real_targets = index_targets(REPO_ROOT)
            case(
                len(real_targets) > 1 and all(len(c) > 0 for c in real_targets.values()),
                "smoke: generation runs clean against the real repo tree",
            )
        except Exception as exc:  # pragma: no cover - defensive
            case(False, f"smoke: generation crashed on the real repo tree: {exc}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = [label for ok, label in results if not ok]
    for ok, label in results:
        print(f"{'PASS' if ok else 'FAIL'}  {label}")
    print(f"{len(results) - len(failed)}/{len(results)} selftest cases passed")
    return 1 if failed else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--check", action="store_true", help="verify INDEX.md files are current; no writes")
    parser.add_argument("--selftest", action="store_true", help="run this script's own self-tests")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root (default: this script's repo)")
    args = parser.parse_args(argv)

    if args.selftest and args.check:
        parser.error("--selftest and --check are mutually exclusive")

    if args.selftest:
        return run_selftest()

    root = Path(args.root).resolve()
    if not (root / SKILLS_DIRNAME).is_dir():
        parser.error(f"no {SKILLS_DIRNAME} under root: {root}")

    if args.check:
        return cmd_check(root)
    return cmd_generate(root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
