#!/usr/bin/env python3
"""focus_kit.py — keep agents on task across long sessions and compactions: handoff, memory lint, docs map.

WHY: a compaction summary can drop the plan, a new session starts blind, memory files grow until the host
truncates them, and nobody can tell which doc to open. Four small commands, stdlib only. Doctrine and the
update cadence: `references/focus-kit.md`.

  handoff set|add SECTION TEXT  update ONE section of .claude/handoff.md in place (created from
        ../templates/handoff.md when absent). Every other section stays byte-identical. A result over
        HANDOFF_MAX bytes is refused, so handoff_inject.py (2048-byte cap) never truncates it.
  memory-lint [DIR]  report-only hygiene lint of an auto-memory dir (index budget and line length, one fact
        per file, duplicates, stale dates, paths and flags that no longer exist) plus the always-loaded
        CLAUDE.md and AGENTS.md. Never writes or deletes.
  docs-index [--check]  generate docs/INDEX.md, one "read this when" row per project doc, built with the same
        helpers as scripts/skill_index.py; --check fails when it is stale (the CI gate).
  measure  bytes an agent reads to recover state: every doc (baseline) vs the injected handoff plus the index.

USAGE
  focus_kit.py handoff set|add SECTION TEXT | memory-lint [DIR] | docs-index [--check] | measure

  e.g. focus_kit.py handoff set next "1. run tests 2. open the PR 3. wait for review"   (TEXT "-" reads stdin)

Exit codes: 0 ok; 1 findings, stale index or refused write; 2 usage or IO error.
Side effects: `handoff` writes the handoff file; `docs-index` writes <docs>/INDEX.md (not with --check);
`memory-lint` and `measure` write nothing.
"""
from __future__ import annotations

import argparse
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:  # appended, never first: a sibling script must not shadow a stdlib module
    sys.path.append(str(HERE))
import handoff_inject  # noqa: E402  (reads what `handoff` writes: CAP, render)

CMD = "python3 .claude/skills/agentic-delivery/scripts/focus_kit.py"
HANDOFF = ".claude/handoff.md"
HANDOFF_MAX = 1900  # handoff_inject.CAP (2048) minus its ~70-byte header and a margin; a test pins this
TRIGGER_MAX = 100
INDEX_NAME = "MEMORY.md"


# ---------------------------------------------------------------------------
# Index-line helpers. scripts/skill_index.py imports these, so a skill index and a docs index cut
# their "read this when" lines the same way (one home, no copy).
# ---------------------------------------------------------------------------
def _collapse(text: str) -> str:
    return " ".join(text.split())


def _truncate(text: str, limit: int) -> str:
    text = _collapse(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _short(text: str, limit: int = 0) -> str:
    """First sentence of `text`, collapsed, truncated to `limit` (default TRIGGER_MAX)."""
    text = _collapse(text)
    m = re.search(r"[.;] ", text)
    if m and m.start() > 20:
        text = text[: m.start() + (m.group(0) == ". ")]
    # the column header says "Read this when...", and a script row's file cell names it
    text = re.sub(r"^(?:read this when:?\s*|\S+\.(?:py|sh)\s+[—-]\s+)", "", text, flags=re.I)
    return _truncate(text, limit or TRIGGER_MAX)


def _strip_md(text: str) -> str:
    return text.replace("**", "").replace("`", "")


def _table_cell(text: str) -> str:
    """Escape a value for a Markdown table cell (pipes would break columns)."""
    return text.replace("|", "\\|") if text else "—"


def token_est(path: Path) -> int:
    """Rough token estimate: bytes // 4 (this repo's chars/4 convention)."""
    return path.stat().st_size // 4


def _paragraph(lines, i=None) -> str:
    """The paragraph starting at line `i` (default: the first after the H1 title), joined by spaces."""
    if i is None:
        i = 0
        while i < len(lines) and not lines[i].strip():
            i += 1
        if i < len(lines) and lines[i].lstrip().startswith("#"):
            i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
    para = []
    while i < len(lines) and lines[i].strip() and not lines[i].lstrip().startswith("#"):
        para.append(lines[i].strip())
        i += 1
    return " ".join(para)


def parse_reference_md(path: Path) -> str:
    """One-line trigger of a skill reference: its first paragraph after the H1, first sentence, <=100 chars."""
    return _short(_strip_md(_paragraph(path.read_text(encoding="utf-8").splitlines())))


DOC_MAX = 140  # a doc row carries its title too, so it gets more room than a skill reference's 100


def _doc_line(text: str, title: str = "") -> str:
    """A doc paragraph as one index line: links reduced to their text, emphasis and a leading "Bottom line:" /
    "BLUF:" / "Status:" label dropped, the shared first-sentence cut, then `title: ` in front (<=DOC_MAX chars)."""
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"^\W*(?:bottom line|bluf|status|tl;dr|summary)\b\W*", "", _strip_md(text).replace("*", ""), flags=re.I)
    line = _short(text, DOC_MAX)
    return _truncate(f"{title}: {line}", DOC_MAX) if title and line else line or title


def parse_doc_md(path: Path) -> str:
    """One-line "read this when" for a project doc, as `<H1 title>: <sentence>`. The sentence comes from a YAML
    front-matter `description:`, else the first "Read/Use this when ..." paragraph in the first 30 lines, else the
    first paragraph after the H1 (blockquote markers dropped). Reads at most 16KB; "(no summary)" when the doc
    has neither a paragraph nor a title."""
    with path.open(encoding="utf-8", errors="replace") as fh:
        text = fh.read(16384)
    m = re.match(r"---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    desc = ""
    if m:
        text = text[m.end():]
        d = re.search(r"(?m)^description:\s*(.+)$", m.group(1))
        if d and d.group(1).strip() not in (">", ">-", "|", "|-"):
            desc = d.group(1).strip(" \"'")
    t = re.search(r"(?m)^#\s+(.+?)\s*$", text)
    title = _collapse(_strip_md(t.group(1))) if t else ""
    lines = [re.sub(r"^\s*>\s?", "", ln) for ln in text.splitlines()]
    para = next((_paragraph(lines, i) for i, ln in enumerate(lines[:30]) if re.match(r"\W*(read|use) (this )?when\b", ln, re.I)), "")
    return _doc_line(desc or para or _paragraph(lines), title) or "(no summary)"


# ---------------------------------------------------------------------------
# handoff: update one section of .claude/handoff.md in place
# ---------------------------------------------------------------------------
class TooBig(Exception):
    """The update would push the handoff past HANDOFF_MAX bytes (nothing was written)."""


def _root(root=None) -> Path:
    return Path(root or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())


def _split(text: str):
    """(preamble, sections): a section starts at a line beginning '## '; preamble + "".join(sections) == text."""
    parts = re.split(r"(?m)^(?=## )", text)
    return parts[0], parts[1:]


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _find(sections, name: str) -> int:
    """Index of the section whose heading is `name` (case and punctuation ignored): exact, else a unique prefix."""
    want = _norm(name)
    heads = [_norm(s.split("\n", 1)[0][3:]) for s in sections]
    hits = [i for i, h in enumerate(heads) if h == want] or [i for i, h in enumerate(heads) if want and h.startswith(want)]
    if len(hits) != 1:
        titles = ", ".join(s.split("\n", 1)[0][3:].strip() for s in sections)
        raise ValueError(f"section {name!r} matches {len(hits)} headings (have: {titles})")
    return hits[0]


def handoff_update(path, name: str, mode: str, text: str, today=None) -> str:
    """Change ONE section of the handoff at `path` and return the new file text.

    mode "set" replaces the section body with `text`; "add" keeps the real lines, drops `<placeholder>` lines
    and appends `- <date>: <text>`. The file is created from templates/handoff.md when absent. Every other
    section is left byte-identical; only the preamble's `Updated:` line is re-stamped. Writes atomically.
    Raises ValueError (unknown or ambiguous section, a symlinked file, text with a `## ` line) or TooBig (result
    over HANDOFF_MAX bytes); the file is untouched in both cases."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError(f"{path} is a symlink; refusing to write through it")
    today = today or datetime.date.today().isoformat()
    old = (path if path.exists() else HERE.parent / "templates" / "handoff.md").read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError("TEXT is empty")
    if re.search(r"(?m)^## ", text):
        raise ValueError("TEXT may not contain a line starting with '## ' (it would add a section)")
    pre, secs = _split(old)
    i = _find(secs, name)
    head, _, body = secs[i].partition("\n")
    trail = re.search(r"\n*\Z", body).group() or "\n"  # the blank-line run that separates this section from the next
    body = body.rstrip("\n")
    if mode == "set":
        new = text.strip("\n")
    else:
        keep = [ln for ln in body.split("\n") if ln.strip() and not re.fullmatch(r"<.*>", ln.strip())]
        line = text.strip()
        dated = line if re.match(r"\d{4}-\d{2}-\d{2}", line) else f"{today}: {line}"
        new = "\n".join(keep + ["- " + dated])
    secs[i] = head + "\n" + new + trail
    out = re.sub(r"(?m)^Updated: .*$", f"Updated: {today}", pre, count=1) + "".join(secs)
    size = len(out.encode("utf-8"))
    if size > HANDOFF_MAX:
        sizes = ", ".join(s.split("\n", 1)[0][3:].strip() + " " + str(len(s.encode("utf-8"))) for s in secs)
        raise TooBig(f"{size} bytes > {HANDOFF_MAX}; trim a section first (bytes per section: {sizes})")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")  # not matched by handoff_inject's handoff*.md glob
    try:
        tmp.write_text(out, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink()
    return out


# ---------------------------------------------------------------------------
# memory-lint: report-only
# ---------------------------------------------------------------------------
_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s#]+\.md)(?:#[^)]*)?\)")
_SPAN = re.compile(r"`([^`\n]+)`")
_FLAG = re.compile(r"(?<![\w-])--[A-Za-z][\w-]*")
_EXT = re.compile(r"\.[A-Za-z0-9]{1,6}$")
_BAD = re.compile(r"[*?<>$|{}\[\]=]|://")


def _read(path: Path, limit: int = 1_000_000) -> str:
    """At most `limit` bytes of `path` as text (a lint must not slurp a huge file a note happens to name)."""
    with path.open("rb") as fh:
        return fh.read(limit).decode("utf-8", "replace")


def _headings(text: str):
    """Line numbers of Markdown headings outside fenced code blocks."""
    out, fenced = [], False
    for n, ln in enumerate(text.splitlines(), 1):
        if ln.lstrip().startswith("```"):
            fenced = not fenced
        elif not fenced and re.match(r"#{1,6}\s", ln):
            out.append(n)
    return out


def _path_tokens(span: str):
    """Repo-path-like tokens of one inline-code span: they contain '/', no glob, placeholder or URL character,
    and end in an extension or '/' (or start with ~/ or ./). A host-like head (example.com/x.html) is no path."""
    out = []
    for tok in span.split():
        tok = re.sub(r":\d+(?:-\d+)?$", "", tok.strip("\"'(").rstrip(".,;:)\"'"))
        if "/" not in tok or tok.startswith(("-", "//")) or _BAD.search(tok):
            continue
        if not (_EXT.search(tok) or tok.endswith("/") or tok.startswith(("~/", "./"))):
            continue
        head = tok.split("/", 1)[0]
        if "." in head and not head.startswith((".", "~")):
            continue
        out.append(tok)
    return out


def _refs(name: str, text: str, root: Path):
    """Findings for inline-code paths that do not exist and for `--flags` absent from the existing script named
    in the same span (a flag with no repo file beside it belongs to another tool and is not checked). A relative
    path counts only when its first component exists under `root`: `references/x.md` is relative to some other
    directory, so it is skipped rather than guessed. Absolute and ~/ paths are always checked."""
    out, seen, fenced = [], set(), False
    for n, line in enumerate(text.splitlines(), 1):
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        for span in _SPAN.findall(line):
            script = None
            for tok in _path_tokens(span):
                try:
                    p = Path(tok).expanduser()
                    if not p.is_absolute():
                        if not (root / tok.split("/", 1)[0]).exists():
                            continue
                        p = root / p
                    here = p.exists()
                except (OSError, ValueError, RuntimeError):  # name too long, NUL, unknown ~user: not checkable
                    continue
                if not here:
                    if ("path-gone", tok) not in seen:
                        seen.add(("path-gone", tok))
                        out.append((name, n, "path-gone", tok))
                elif p.is_file() and script is None:
                    script = (tok, p)
            if script:
                src = _read(script[1])
                for flag in _FLAG.findall(span):
                    if flag not in src and ("flag-gone", flag + script[0]) not in seen:
                        seen.add(("flag-gone", flag + script[0]))
                        out.append((name, n, "flag-gone", f"{flag} is not in {script[0]}"))
    return out


def _always_loaded(root: Path):
    """CLAUDE.md and AGENTS.md at the project root, de-duplicated when one links to the other."""
    out, seen = [], set()
    for n in ("CLAUDE.md", "AGENTS.md"):
        p = root / n
        if p.is_file() and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)
    return out


def lint_always_loaded(root, max_lines: int = 200, max_bytes: int = 10240):
    """Findings (file, line, code, detail) for the always-loaded layer: CLAUDE.md or AGENTS.md over the size
    budget (the host docs target <200 lines; cost-quality-guardrails.md says ~10KB) and dead paths or flags."""
    root, out = Path(root), []
    for p in _always_loaded(root):
        text, size = _read(p), p.stat().st_size
        lines = len(text.splitlines())
        if lines > max_lines or size > max_bytes:
            out.append((p.name, 0, "always-loaded-big", f"{lines} lines, {size} B > {max_lines} lines / {max_bytes} B; move detail to routed docs"))
        out += _refs(p.name, text, root)
    return out


def lint_memory(mem_dir, root, today=None, max_index_lines: int = 150, max_index_bytes: int = 20000,
                max_line: int = 150, max_file_bytes: int = 3072, stale_days: int = 30):
    """Report-only findings (file, line, code, detail) for an auto-memory dir (MEMORY.md index plus topic files).

    Codes: index-missing, index-lines, index-bytes (the host loads only the first 200 lines / 25KB of the index,
    so the defaults leave headroom), index-line-long, index-dangling, index-dup-link, index-dup-title, orphan
    (a topic file the index never links), file-big and multi-topic (proxies for "one fact per file"),
    near-duplicate (word-set Jaccard >= 0.8), stale-date (newest date in a file older than `stale_days`; 0 turns it
    off; a future date never counts), path-gone and flag-gone (see _refs; paths resolve against `root`, `~` is
    expanded). Reads only: never writes, deletes or renames; symlinks are skipped."""
    mem, root = Path(mem_dir), Path(root)
    today = today or datetime.date.today()
    out = []
    files = sorted(p for p in mem.glob("*.md") if p.name != INDEX_NAME and p.is_file() and not p.is_symlink())
    idx, linked, titles = mem / INDEX_NAME, {}, {}
    if not idx.is_file() or idx.is_symlink():
        out.append((INDEX_NAME, 0, "index-missing", "no MEMORY.md; the host loads only the index at session start"))
    else:
        lines, nbytes = _read(idx).splitlines(), idx.stat().st_size
        if len(lines) > max_index_lines:
            out.append((INDEX_NAME, 0, "index-lines", f"{len(lines)} lines > {max_index_lines}"))
        if nbytes > max_index_bytes:
            out.append((INDEX_NAME, 0, "index-bytes", f"{nbytes} B > {max_index_bytes}"))
        for n, ln in enumerate(lines, 1):
            if len(ln) > max_line:
                out.append((INDEX_NAME, n, "index-line-long", f"{len(ln)} chars > {max_line}"))
            for title, target in _LINK.findall(ln):
                target = os.path.normpath(target)
                if not (mem / target).is_file():
                    out.append((INDEX_NAME, n, "index-dangling", f"{target} does not exist"))
                if target in linked:
                    out.append((INDEX_NAME, n, "index-dup-link", f"{target} also on line {linked[target]}"))
                linked.setdefault(target, n)
                key = _norm(title)
                if key and key in titles:
                    out.append((INDEX_NAME, n, "index-dup-title", f"{title.strip()!r} also on line {titles[key]}"))
                titles.setdefault(key, n)
    words = {}
    for p in files:
        text, size = _read(p), p.stat().st_size
        if p.name not in linked and idx.is_file():
            out.append((p.name, 0, "orphan", "not linked from MEMORY.md, so an agent cannot find it"))
        if size > max_file_bytes:
            out.append((p.name, 0, "file-big", f"{size} B > {max_file_bytes}; one fact per file"))
        heads = _headings(text)
        if len(heads) >= 3:
            out.append((p.name, heads[2], "multi-topic", f"{len(heads)} headings; one fact per file"))
        dates = []
        for y, m, d in re.findall(r"\b(\d{4})-(\d{2})-(\d{2})\b", text):
            try:
                dates.append(datetime.date(int(y), int(m), int(d)))
            except ValueError:
                pass
        dates = [d for d in dates if d <= today]
        if stale_days and dates and (today - max(dates)).days > stale_days:
            out.append((p.name, 0, "stale-date", f"newest date {max(dates)} is {(today - max(dates)).days} days old (> {stale_days}); re-verify or drop"))
        out += _refs(p.name, text, root)
        words[p.name] = set(re.findall(r"[a-z0-9]{3,}", re.sub(r"\A---\n.*?\n---\n", "", text, flags=re.S).lower()))
    names = sorted(words)
    # ponytail: all pairs, O(n^2) set ops; fine to ~500 files, switch to shingled hashing if a memory dir outgrows that
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if len(words[a]) >= 12 and len(words[b]) >= 12:
                j = len(words[a] & words[b]) / len(words[a] | words[b])
                if j >= 0.8:
                    out.append((b, 0, "near-duplicate", f"{j:.2f} similar to {a}; merge or drop one"))
    return out


def auto_memory_dir(root):
    """The host's auto-memory dir for the git repo of `root` (worktrees map to the main repo):
    <config dir>/projects/<repo path with '/' and '.' as '-'>/memory, or None when it does not exist.
    The mapping is the layout observed on disk; a wrong guess ends in "pass DIR", never in a wrong lint."""
    root = Path(root)
    base = root
    try:
        r = subprocess.run(["git", "-C", str(root), "rev-parse", "--git-common-dir"], capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            common = Path(r.stdout.strip())
            base = (common if common.is_absolute() else root / common).resolve().parent
    except OSError:  # no git binary: fall back to the root itself
        pass
    cfg = Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")
    d = cfg / "projects" / re.sub(r"[/.]", "-", str(base)) / "memory"
    return d if d.is_dir() else None


# ---------------------------------------------------------------------------
# docs-index: docs/INDEX.md, the low-context lookup pattern of the skill index
# ---------------------------------------------------------------------------
def doc_files(root, docs: str = "docs", exclude=()):
    """Sorted Markdown files under <root>/<docs>, without INDEX.md, symlinks, `exclude`d paths (relative to the
    docs dir, a file or a directory prefix) and .git / node_modules."""
    base = Path(root) / docs
    drop = tuple(e.strip("/") for e in exclude)

    def skipped(rel: str) -> bool:
        return any(rel == e or rel.startswith(e + "/") for e in drop)

    out = []
    for dp, dns, fns in os.walk(base):
        rel_dir = "" if Path(dp) == base else Path(dp).relative_to(base).as_posix()
        dns[:] = sorted(d for d in dns if d not in (".git", "node_modules") and not Path(dp, d).is_symlink()
                        and not skipped(f"{rel_dir}/{d}".lstrip("/")))
        for fn in sorted(fns):
            rel = f"{rel_dir}/{fn}".lstrip("/")
            if fn.endswith(".md") and rel != "INDEX.md" and not Path(dp, fn).is_symlink() and not skipped(rel):
                out.append(Path(dp, fn))
    return sorted(out)


def _regen(docs: str, exclude) -> str:
    return f"{CMD} docs-index" + (f" --docs {docs}" if docs != "docs" else "") + "".join(f" --exclude {e}" for e in exclude)


def docs_index(root, docs: str = "docs", exclude=()) -> str:
    """The docs/INDEX.md text: one `| file | read this when | tokens |` row per doc, sorted, no timestamps, so the
    same tree always yields the same bytes (what --check relies on). The header records the regenerate command
    including `exclude`, so a reader sees what was left out."""
    root = Path(root)
    rows = [f"| `{p.relative_to(root).as_posix()}` | {_table_cell(parse_doc_md(p))} | {token_est(p)} |" for p in doc_files(root, docs, exclude)]
    note = " Excluded: " + ", ".join(f"`{e}`" for e in exclude) + "." if exclude else ""
    return "\n".join([
        "# Docs index", "",
        f"Generated by `{_regen(docs, exclude)}` (do not hand-edit; rerun it after adding, renaming or re-titling a doc; "
        f"`--check` is the CI gate). One row per doc: open a doc only when its row matches what you need. Not always-loaded.{note}",
        "", "| File | Read this when... | Tok |", "|---|---|---|", *rows, ""])


def measure(root, docs: str = "docs", exclude=()) -> dict:
    """Bytes an agent reads to recover state. baseline = CLAUDE.md + AGENTS.md + every doc (reading everything,
    an upper bound); kit = the handoff as handoff_inject.py would inject it (0 when absent) + the docs index.
    Pure arithmetic on current file sizes; CLAUDE.md and AGENTS.md stay auto-loaded either way."""
    root = Path(root)
    always = sum(p.stat().st_size for p in _always_loaded(root))
    has_docs = (root / docs).is_dir()
    files = doc_files(root, docs, exclude) if has_docs else []
    doc_bytes = sum(p.stat().st_size for p in files)
    ho = len(handoff_inject.render(root).encode("utf-8"))
    ix = len(docs_index(root, docs, exclude).encode("utf-8")) if has_docs else 0
    return {"always": always, "docs": doc_bytes, "n_docs": len(files), "baseline": always + doc_bytes,
            "handoff": ho, "index": ix, "kit": ho + ix}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _fmt(f) -> str:
    name, line, code, detail = f
    return f"{name}{':' + str(line) if line else ''} {code} {detail}"


def _cmd_handoff(a) -> int:
    path = Path(a.file) if a.file else _root(a.root) / HANDOFF
    if a.text and a.text != ["-"]:
        text = " ".join(a.text)
    elif sys.stdin.isatty():
        print("focus_kit handoff: TEXT is required (or pipe it on stdin)", file=sys.stderr)
        return 2
    else:
        text = sys.stdin.read()
    try:
        out = handoff_update(path, a.section, a.mode, text)
    except TooBig as e:
        print(f"focus_kit handoff: refused, {e}", file=sys.stderr)
        return 1
    except (ValueError, OSError) as e:
        print(f"focus_kit handoff: {e}", file=sys.stderr)
        return 2
    print(f"handoff: {a.section} updated ({len(out.encode('utf-8'))}/{HANDOFF_MAX} B) {path}")
    return 0


def _cmd_memory_lint(a) -> int:
    root = _root(a.root)
    mem = Path(a.dir).expanduser() if a.dir else auto_memory_dir(root)
    if mem is None or not mem.is_dir():
        print("focus_kit memory-lint: no memory dir found; pass DIR (auto memory lives in ~/.claude/projects/<project>/memory/)", file=sys.stderr)
        return 2
    found = lint_memory(mem, root, stale_days=a.stale_days, max_index_lines=a.max_index_lines,
                        max_line=a.max_line, max_file_bytes=a.max_file_bytes) + lint_always_loaded(root)
    for f in sorted(found, key=lambda f: (f[0], f[1], f[2])):
        print(_fmt(f))
    print(f"memory-lint: {len(found)} finding(s) in {mem} (report only; nothing was changed)")
    return 1 if found else 0


def _cmd_docs_index(a) -> int:
    root = _root(a.root)
    out = root / a.docs / "INDEX.md"
    if not (root / a.docs).is_dir():
        print(f"focus_kit docs-index: no {a.docs}/ under {root}", file=sys.stderr)
        return 2
    new = docs_index(root, a.docs, a.exclude)
    if a.check:
        if out.is_file() and not out.is_symlink() and out.read_text(encoding="utf-8") == new:
            print(f"docs-index --check: ok ({len(doc_files(root, a.docs, a.exclude))} docs, {out.relative_to(root)} current)")
            return 0
        print(f"STALE: {out.relative_to(root)} (run: {_regen(a.docs, a.exclude)})", file=sys.stderr)
        return 1
    if out.is_symlink():
        print(f"focus_kit docs-index: {out} is a symlink; refusing to write through it", file=sys.stderr)
        return 2
    out.write_text(new, encoding="utf-8")
    print(f"wrote {out.relative_to(root)}")
    return 0


def _cmd_measure(a) -> int:
    m = measure(_root(a.root), a.docs, a.exclude)
    print(f"baseline (read everything): CLAUDE.md+AGENTS.md {m['always']} B + {m['n_docs']} docs {m['docs']} B = {m['baseline']} B (~{m['baseline'] // 4} tok)")
    cut = f", {100 * (1 - m['kit'] / m['baseline']):.1f}% fewer bytes" if m["baseline"] else ""
    print(f"focus kit (injected handoff + docs index): {m['handoff']} B + {m['index']} B = {m['kit']} B (~{m['kit'] // 4} tok){cut}")
    return 0


def main(argv=None) -> int:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--root", help="project root (default: $CLAUDE_PROJECT_DIR, else the cwd)")
    docs = argparse.ArgumentParser(add_help=False)
    docs.add_argument("--docs", default="docs", help="docs dir relative to the root (default: docs)")
    docs.add_argument("--exclude", action="append", default=[], metavar="PATH", help="skip a file or directory under the docs dir (repeatable)")
    ap = argparse.ArgumentParser(prog="focus_kit.py", description=(__doc__ or "").split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    h = sub.add_parser("handoff", parents=[common], help="update one section of .claude/handoff.md in place")
    h.add_argument("mode", choices=("set", "add"), help="set: replace the section body; add: append one dated bullet")
    h.add_argument("section", help="heading, e.g. goal, stage, next, 'in flight', blockers, decisions (unique prefix, any case)")
    h.add_argument("text", nargs="*", help='the new text; "-" or nothing reads stdin')
    h.add_argument("--file", help=f"handoff file (default: <root>/{HANDOFF})")
    h.set_defaults(fn=_cmd_handoff)
    m = sub.add_parser("memory-lint", parents=[common], help="report-only hygiene lint of a memory dir and CLAUDE.md/AGENTS.md")
    m.add_argument("dir", nargs="?", help="memory dir holding MEMORY.md (default: the host's auto-memory dir for this repo)")
    m.add_argument("--stale-days", type=int, default=30, help="flag a file whose newest date is older (0 = off; default 30)")
    m.add_argument("--max-index-lines", type=int, default=150)
    m.add_argument("--max-line", type=int, default=150, help="max chars per index line (default 150)")
    m.add_argument("--max-file-bytes", type=int, default=3072, help="max bytes per memory file (default 3072)")
    m.set_defaults(fn=_cmd_memory_lint)
    d = sub.add_parser("docs-index", parents=[common, docs], help="write docs/INDEX.md (--check: fail when stale)")
    d.add_argument("--check", action="store_true", help="write nothing; exit 1 when INDEX.md is stale or missing")
    d.set_defaults(fn=_cmd_docs_index)
    s = sub.add_parser("measure", parents=[common, docs], help="bytes read to recover state: baseline vs handoff + docs index")
    s.set_defaults(fn=_cmd_measure)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
