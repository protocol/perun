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

And the single low-context entry point:
  `.claude/skills/INDEX.md` — one line per skill (the first sentence of its
  SKILL.md frontmatter `description:`: what it is for and when to use it), one
  line per `commands/*.md` slash command and one line per shipped
  `scripts/*.py|*.sh` (`name: purpose — arguments`, arguments only when the
  script's own header documents them), plus where to read next: a skill's
  SKILL.md when its line matches, its INDEX.md for references and scripts. It
  points; it never restates a checklist. Its byte size is frozen by a row in
  scripts/size-budgets.tsv (the only INDEX.md with one), because it is read whole.

Output is deterministic: sorted paths, no timestamps, no run-dependent data.
The per-skill INDEX.md files are lookup aids, not references: not must-load,
no routing/size-budget obligation (scripts/ci-gates.sh's `routing` and `size`
subcommands read SKILL.md and references/*.md, plus the one entry-index row).

USAGE
  python3 scripts/skill_index.py             generate/overwrite every INDEX.md
  python3 scripts/skill_index.py --check     verify INDEX.md files match their
                                              sources and that every shipped
                                              script and command is listed; no writes
  python3 scripts/skill_index.py --tokens    print the always-loaded surface
                                              (skill descriptions, entry index,
                                              SessionStart host rules) in bytes and
                                              estimated tokens (bytes // 4)
  python3 scripts/skill_index.py --selftest  run this script's own self-tests

Exit codes: 0 ok; 1 stale INDEX.md or a script/command missing from the entry
index (--check), or a self-test failed (--selftest); 2 usage error.
"""
from __future__ import annotations

import argparse
import ast
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS_DIRNAME = ".claude/skills"

# The index-line helpers (_collapse, _short, _truncate, _strip_md, _table_cell, token_est, parse_reference_md) live in the
# shipped focus_kit.py, which cuts a project's docs/INDEX.md the same way: one home, no copy. A reference's
# trigger is its first paragraph after the H1 (no headings column: the routed file's own headings are one open
# away, and the column cost ~7K tokens per session).
sys.path.append(str(REPO_ROOT / SKILLS_DIRNAME / "agentic-delivery" / "scripts"))
from focus_kit import _collapse, _short, _strip_md, _table_cell, _truncate, parse_reference_md, token_est  # noqa: E402

BLOCK_MAX = 120
# Entry-index caps (the file is read whole, so every line stays short), cut at a word.
SKILL_LINE_MAX = 120
PURPOSE_MAX = 64
ARGS_MAX = 40
SCRIPTS_INLINE_MAX = 12  # more scripts than this: the script table moves to the lazy SCRIPTS_INDEX
SCRIPTS_INDEX = "INDEX-scripts.md"
SCRIPTS_POINTER = f"Read `{SCRIPTS_INDEX}` when you need a script"
COMMANDS_DIRNAME = "commands"
NO_CLI = "- No documented CLI: "  # a bullet of its own, after a skill's script lines

_UNDERLINE_RE = re.compile(r"^[-=]{3,}$")


# ---------------------------------------------------------------------------
# Script parsing. Both parsers return (trigger, usage parts): the first
# paragraph is the trigger; the usage parts are the documented CLI, an empty
# list when the script documents none (a bare script name is no usage).
# Python: a "Usage" section (heading line, optionally with inline content,
# followed by a block of non-blank lines), else a `name.py ARGS — purpose`
# first line, else the first docstring line that is itself a call of the script.
# ---------------------------------------------------------------------------
def _docstring(path: Path) -> str:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return ""
    return ast.get_docstring(tree) or ""


def _paragraphs(doc: str) -> list[str]:
    """The docstring's paragraphs, each joined into one markdown-stripped line."""
    out: list[str] = []
    para: list[str] = []
    for line in [*doc.splitlines(), ""]:
        if line.strip():
            para.append(line.strip())
        elif para:
            out.append(_strip_md(" ".join(para)))
            para = []
    return out


# `name.py ARGS — purpose` (also ` - ` and ` -- `): the usual one-line script header.
_HEADER_RE = re.compile(r"^(?P<cli>\S+\.(?:py|sh)\b.*?)\s+(?:—|--?)\s+(?P<rest>.+)$")

# "usage" must stand alone as a heading word: followed by a colon, whitespace, or
# end of line. Prose that merely starts a docstring line with "usage)." or
# "usage," is not a CLI section (it leaked a sentence fragment into a CLI cell).
_USAGE_RE = re.compile(r"^usage(?=:|\s|$)\s*:?\s*(?P<inline>.*)$", re.IGNORECASE)


def _split_header(para: str) -> tuple[str, str]:
    """`name.py ARGS — purpose` -> (`name.py ARGS`, `purpose`); ("", para) for any other shape."""
    m = _HEADER_RE.match(para)
    return (m.group("cli"), m.group("rest")) if m else ("", para)


def _usage_parts(doc_lines: list[str]) -> list[str]:
    """The lines of the first non-empty `Usage` section: the heading's inline text, then the block under it."""
    for idx, line in enumerate(doc_lines):
        m = _USAGE_RE.match(line.strip())
        if not m:
            continue
        parts = [m.group("inline").strip()]
        j = idx + 1
        while j < len(doc_lines) and doc_lines[j].strip():
            candidate = doc_lines[j].strip()
            if not _UNDERLINE_RE.match(candidate):
                parts.append(candidate)
            j += 1
        parts = [_strip_md(p) for p in parts if p]
        if parts:
            return parts
    return []


def _invocation(doc_lines: list[str], name: str) -> str | None:
    """The first docstring line that is itself a call of `name` with options or placeholders.

    Column-aligned text after the call (2+ spaces: a description or `# comment`) is dropped; a shell
    chain (`&&`) is an example inside prose, not the script's usage."""
    call = re.compile(rf"^(?:python3?\s+|bash\s+)?(?:\S*/)?{re.escape(name)}\s+(?P<args>\S.*)$")
    for line in doc_lines:
        m = call.match(line.strip())
        if m and "&&" not in line and re.search(r"(?:^|\s)(?:-{1,2}\w|\[|<)", m.group("args")):
            args = re.split(r"\s{2,}", m.group("args"))[0]
            return f"{name} {_strip_md(args)}"
    return None


def parse_script_py(path: Path) -> tuple[str, list[str]]:
    """(trigger, usage parts) from a Python script's module docstring; see the section comment above."""
    doc = _docstring(path)
    if not doc:
        return "(no module docstring)", []
    paras = _paragraphs(doc)
    cli, purpose = _split_header(paras[0])
    if not cli and paras[0].startswith(path.name + " ") and len(paras) > 1:
        cli, purpose = paras[0], re.sub(r"^WHY:\s*", "", paras[1])  # a bare usage line: the purpose is next
    doc_lines = doc.splitlines()
    parts = _usage_parts(doc_lines)
    if not parts and " " in cli:
        parts = [cli]
    if not parts:
        call = _invocation(doc_lines, path.name)
        parts = [call] if call else []
    return _short(purpose), parts


def parse_script_sh(path: Path) -> tuple[str, list[str]]:
    """Same pair from a shell script's leading comment block: `name.sh args — text`
    or a `Usage: ...` line gives the CLI."""
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
        return "(no header comment)", []
    first = _strip_md(para[0])
    m = re.match(r"^(\S+\.sh\b[^—]*?)\s+[—-]\s+(.*)$", first)
    usage = None
    if m:
        usage = m.group(1)
        para[0] = m.group(2)
    else:
        u = next((l for l in block if l.lower().startswith("usage:")), None)
        if u:
            usage = _strip_md(u.split(":", 1)[1])
    return _short(_strip_md(" ".join(para))), [usage] if usage else []


# ---------------------------------------------------------------------------
# SKILL.md frontmatter: the whole `description:` (inline or block scalar),
# whitespace-collapsed. The entry index keeps its first sentence only.
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
                return _collapse(rest)
            capturing = True
            continue
        if line.strip() == "" or line.startswith(" "):
            if line.strip():
                desc_lines.append(line.strip())
            continue
        break
    return _collapse(" ".join(desc_lines))


def read_command(path: Path) -> tuple[str, str]:
    """(description, argument-hint) from a commands/*.md frontmatter; "" for an absent field."""
    lines = path.read_text(encoding="utf-8").splitlines()
    vals: dict[str, str] = {}
    if lines and lines[0].strip() == "---":
        for line in lines[1:]:
            if line.strip() == "---":
                break
            key, _, val = line.partition(":")
            vals[key.strip()] = val.strip().strip("\"'")
    return vals.get("description", ""), vals.get("argument-hint", "")


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


def shipped_scripts(skill_dir: Path) -> list[Path]:
    """A skill's shipped scripts: `scripts/*.py|*.sh`, sorted (nested fixture dirs are data, not scripts)."""
    d = skill_dir / "scripts"
    return sorted([*d.glob("*.py"), *d.glob("*.sh")]) if d.is_dir() else []


def shipped_commands(root: Path) -> list[Path]:
    """The slash commands install.sh ships: `commands/*.md`, sorted."""
    d = root / COMMANDS_DIRNAME
    return sorted(d.glob("*.md")) if d.is_dir() else []


def parse_script(path: Path) -> tuple[str, list[str]]:
    """(trigger, usage parts) for a shipped script, by suffix."""
    return parse_script_sh(path) if path.suffix == ".sh" else parse_script_py(path)


def _split_scripts(scripts: list[Path]) -> bool:
    """A skill with more than SCRIPTS_INLINE_MAX scripts keeps its script table in the lazy INDEX-scripts.md."""
    return len(scripts) > SCRIPTS_INLINE_MAX


def _script_rows(scripts: list[Path]) -> list[str]:
    out = ["| File | Trigger | CLI (— = open the header) |", "|---|---|---|"]
    for scr in scripts:
        trigger, parts = parse_script(scr)
        cli = _truncate(" ".join(parts), BLOCK_MAX)
        out.append(f"| `scripts/{scr.name}` | {_table_cell(trigger)} | {_table_cell(cli)} |")
    return out


def generate_skill_index(skill_dir: Path) -> str:
    name = skill_dir.name
    refs = sorted((skill_dir / "references").glob("*.md")) if (skill_dir / "references").is_dir() else []
    scripts = shipped_scripts(skill_dir)

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
    if _split_scripts(scripts):
        out.append(f"{len(scripts)} scripts. {SCRIPTS_POINTER} (a trigger and CLI per script). "
                   f"`../INDEX.md`, `### {name}`, has only each one-line purpose and arguments.")
    elif scripts:
        out += _script_rows(scripts)
    else:
        out.append("_No scripts/*.py or *.sh in this skill._")
    out.append("")
    return "\n".join(out)


def generate_scripts_index(skill_dir: Path) -> str:
    """The lazy half of a split skill index: one row per script, with trigger and CLI."""
    return "\n".join([
        f"# INDEX-scripts — {skill_dir.name}",
        "",
        "Generated by `scripts/skill_index.py` (do not hand-edit). The script half of `INDEX.md`, read only "
        "to find a tool: triggers are cut to one line, the full text is in the script's own header.",
        "",
        *_script_rows(shipped_scripts(skill_dir)),
        "",
    ])


def _args(parts: list[str], name: str) -> str:
    """The arguments of the first documented call: the interpreter, path and script name are the line's key."""
    i = parts[0].find(name)
    return _truncate(parts[0][i + len(name):] if i >= 0 else parts[0], ARGS_MAX, words=True)


def _entry(key: str, purpose: str, args: str) -> str:
    """One entry-index line, `key: purpose — args`; the key is not repeated inside the purpose."""
    purpose = re.sub(rf"^{re.escape(key)}\s*[:—-]+\s*", "", purpose)
    line = f"- {key}: {_truncate(purpose, PURPOSE_MAX, words=True)}"
    return f"{line} — {args}" if args else line


def generate_repo_index(root: Path, skill_dirs: list[Path]) -> str:
    out = [
        "# Skills index",
        "",
        "Single entry point, generated in the Perun source repo by `scripts/skill_index.py` (never hand-edit it). Paths are "
        "relative to this directory. Open only what a line points to.",
        "",
        "## Skills",
        "",
        "Read `<skill>/SKILL.md` when its line matches. `<skill>/INDEX.md` lists its "
        "`references/` (each with a read-when trigger); large script tables are in `INDEX-scripts.md`.",
        "",
    ]
    out += [f"- {d.name}: {_short(read_description(d / 'SKILL.md'), SKILL_LINE_MAX, words=True)}" for d in skill_dirs]
    commands = shipped_commands(root)
    if commands:
        out += ["", "## Commands", ""]
        for cmd in commands:
            purpose, hint = read_command(cmd)
            out.append(_entry(f"/{cmd.stem}", purpose, _truncate(hint, ARGS_MAX, words=True)))
    groups = [(d, [(s, *parse_script(s)) for s in shipped_scripts(d)]) for d in skill_dirs]
    if any(scripts for _, scripts in groups):
        out += [
            "",
            "## Scripts",
            "",
            "Run `python3 <skill>/scripts/<name>` (`bash` for `.sh`). `name: purpose — arguments` for a "
            "script whose header documents a CLI; the rest (hooks, sourced helpers, undocumented tools) "
            "are listed by name, their purpose is in `<skill>/INDEX*.md`.",
        ]
        for d, scripts in groups:
            if scripts:
                out += ["", f"### {d.name}"]
                out += [_entry(s.name, purpose, _args(parts, s.name)) for s, purpose, parts in scripts if parts]
                bare = [s.name for s, _, parts in scripts if not parts]
                if bare:
                    out.append(NO_CLI + ", ".join(bare))
    out.append("")
    return "\n".join(out)


def index_targets(root: Path) -> dict[Path, str]:
    """Map each INDEX.md path (repo-level + per-skill) to its generated content."""
    skill_dirs = find_skill_dirs(root)
    targets = {root / SKILLS_DIRNAME / "INDEX.md": generate_repo_index(root, skill_dirs)}
    for skill_dir in skill_dirs:
        targets[skill_dir / "INDEX.md"] = generate_skill_index(skill_dir)
        if _split_scripts(shipped_scripts(skill_dir)):  # --check flags a leftover file when a skill shrinks below the cap
            targets[skill_dir / SCRIPTS_INDEX] = generate_scripts_index(skill_dir)
    return targets


def cmd_generate(root: Path) -> int:
    for path, content in sorted(index_targets(root).items()):
        path.write_text(content, encoding="utf-8")
        print(f"wrote {path.relative_to(root)}")
    return 0


def _shipped(root: Path) -> set[str]:
    """Every shipped script and command, as the keys the entry index lists: `<skill>/<script>`, `/<command>`."""
    keys = {f"{d.name}/{s.name}" for d in find_skill_dirs(root) for s in shipped_scripts(d)}
    return keys | {f"/{c.stem}" for c in shipped_commands(root)}


def _listed(index_text: str) -> set[str]:
    """The keys an entry index lists, read back from its text (not from the generator)."""
    keys: set[str] = set()
    section = skill = ""
    for line in index_text.splitlines():
        if line.startswith("### "):
            skill = line[4:].strip()
        elif line.startswith("## "):
            section, skill = line[3:].strip(), ""
        elif section == "Scripts" and skill and line.startswith(NO_CLI):
            keys |= {f"{skill}/{name}" for name in line[len(NO_CLI):].split(", ")}
        elif line.startswith("- ") and ":" in line:
            key = line[2:].split(":", 1)[0]
            if section == "Commands":
                keys.add(key)
            elif section == "Scripts" and skill:
                keys.add(f"{skill}/{key}")
    return keys


def cmd_check(root: Path) -> int:
    problems = []
    targets = index_targets(root)
    for path, content in sorted(targets.items()):
        rel = path.relative_to(root)
        if not path.is_file():
            problems.append(f"MISSING: {rel}")
        elif path.read_text(encoding="utf-8") != content:
            problems.append(f"STALE: {rel} (run: python3 scripts/skill_index.py)")
    problems += [f"ORPHAN: {f.relative_to(root)} (skill is under the script cap; delete it)"
                 for d in find_skill_dirs(root) if (f := d / SCRIPTS_INDEX).is_file() and f not in targets]
    # Coverage gate: read back from the file on disk, independent of the generator, so a filter
    # added to the generator (or a hand edit) cannot hide a shipped script or command.
    entry = root / SKILLS_DIRNAME / "INDEX.md"
    shipped = _shipped(root)
    if entry.is_file():
        listed = _listed(entry.read_text(encoding="utf-8"))
        problems += [f"NOT IN INDEX: {key} (not listed in {entry.relative_to(root)})" for key in sorted(shipped - listed)]
    if problems:
        for line in problems:
            print(line, file=sys.stderr)
        print(f"skill_index --check: {len(problems)} problem(s)", file=sys.stderr)
        return 1
    print(f"skill_index --check: ok ({len(targets)} INDEX.md file(s) current, {len(shipped)} scripts/commands listed)")
    return 0


def _host_rules(root: Path) -> str:
    """The fixed text SessionStart always injects (HOST_RULES in the delivery skill), read without importing it."""
    src = root / SKILLS_DIRNAME / "agentic-delivery" / "scripts" / "subagent_start_inject.py"
    try:
        for node in ast.parse(src.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "HOST_RULES" for t in node.targets):
                return ast.literal_eval(node.value)
    except (OSError, SyntaxError, ValueError):
        pass
    return ""


def cmd_tokens(root: Path) -> int:
    """Print the always-loaded surface: what a session pays before any task work."""
    index = root / SKILLS_DIRNAME / "INDEX.md"
    descriptions = "".join(f"- {d.name}: {read_description(d / 'SKILL.md')}\n" for d in find_skill_dirs(root))
    surface = [
        ("skill descriptions", descriptions, "injected by the host every session"),
        ("SessionStart host rules", _host_rules(root), "injected every session (fixed part)"),
        (f"{SKILLS_DIRNAME}/INDEX.md", index.read_text(encoding="utf-8") if index.is_file() else "", "entry point, read first on demand"),
    ]
    total = 0
    for label, text, how in surface:
        size = len(text.encode("utf-8"))
        total += size // 4
        print(f"{label:<26} {size:>6} B {size // 4:>5} tok  {how}")
    print(f"{'total':<26} {'':>6}   {total:>5} tok")
    print("tok = bytes // 4, an estimate (this repo's chars/4), not a tokenizer count. The SessionStart "
          "report lines (<=3) and a handoff (<=2048 B) vary per session and are not counted.")
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
            "  Use when the fixture needs a widget, a first sentence long enough to be\n"
            "  truncated because it exceeds the one hundred fifty character cap by a wide "
            "  and deliberate margin here. A second sentence is dropped.\n"
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
        case("- widget-skill: Use when the fixture needs a widget" in repo_text, "repo index: lists the skill by name with its trigger")
        case("…" in repo_text and "second sentence" not in repo_text, "repo index: overlong first sentence truncated with an ellipsis, rest dropped")

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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="verify INDEX.md files are current and list every shipped script and command; no writes")
    mode.add_argument("--tokens", action="store_true", help="print the always-loaded surface in bytes and estimated tokens")
    mode.add_argument("--selftest", action="store_true", help="run this script's own self-tests")
    parser.add_argument("--root", default=str(REPO_ROOT), help="repo root (default: this script's repo)")
    args = parser.parse_args(argv)

    if args.selftest:
        return run_selftest()

    root = Path(args.root).resolve()
    if not (root / SKILLS_DIRNAME).is_dir():
        parser.error(f"no {SKILLS_DIRNAME} under root: {root}")

    if args.check:
        return cmd_check(root)
    if args.tokens:
        return cmd_tokens(root)
    return cmd_generate(root)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
