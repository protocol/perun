#!/usr/bin/env python3
"""lint_ui_slop.py — zero-token, deterministic lint for common UI defects in HTML, CSS, JSX and TSX.

WHY THIS EXISTS
---------------
A UI review spends model tokens re-finding defects a regex and a contrast formula find for free: text that
fails contrast, a skipped heading level, an image with no alt text. Run this first; spend review effort on
what a script cannot see (layout, flow, states, copy). It never calls a model or the network.

USAGE
-----
  lint_ui_slop.py [--json] [--tokens FILE] PATH...
  lint_ui_slop.py --hook < hook-event.json

PATH is a file or a directory (walked, skipping node_modules and dot-directories); only .html .htm .css .jsx
.tsx are read. Exit 0 = clean, 2 = findings, 1 = error (unreadable path or bad arguments). Text output is
`path:line: rule: message`; `--json` prints a list of {path, line, rule, message}.

RULES (own set; each is a heuristic over source text, not a rendered-page check)
-----
  gradient-text      background-clip:text on a gradient (or Tailwind bg-clip-text + bg-gradient on one line)
  low-contrast       color and background hex in the same rule/style are under WCAG 4.5:1 (3:1 for large text)
  small-body-font    font-size under 14px (0.875rem) on body, html, :root, p or li
  tight-line-height  unitless line-height under 1.2 on body, html, :root, p or li
  heading-skip       a heading jumps more than one level down (h1 then h3)
  img-alt            <img> with no alt attribute (alt="" is fine for decoration)
  off-token-hex      a hex colour absent from the project tokens file (only when one exists)
  positive-tabindex  tabindex above 0 breaks the natural focus order
  outline-removed    outline:none/0 with no box-shadow or border, and no :focus-visible rule that draws a ring
  click-non-semantic  onClick/onclick on div, span, li, p or section with no role (use a button or link)
  zoom-blocked       viewport meta with user-scalable=no or maximum-scale=1
  html-lang          <html> with no lang attribute
  input-label        form control with no id, aria-label, aria-labelledby, title or wrapping label
  no-reduced-motion  @keyframes/animation with no prefers-reduced-motion query in the file
  dead-link          <a href="#"> or javascript:void(0)

TOKENS. `--tokens FILE` (any text file; every hex in it is allowed), else the nearest tokens.css,
tokens.json or design-tokens.json found walking up from each linted file (stops at the nearest .git; with
no .git, at the cwd, or the file's own directory when it is outside the cwd). With no
tokens file, off-token-hex is silent.

OPTIONAL POST-EDIT HOOK. Not installed by anything here; to opt in, add under "hooks" in your own
.claude/settings.json (exit 2 feeds the findings back to the agent right after the edit):
  "PostToolUse": [{"matcher": "Edit|Write|MultiEdit", "hooks": [{"type": "command", "timeout": 5,
    "command": "python3 \\"$CLAUDE_PROJECT_DIR/.claude/skills/deep-code-review/scripts/lint_ui_slop.py\\" --hook"}]}]
`--hook` reads the hook event from stdin, lints tool_input.file_path, and writes findings to stderr.

Edge cases: comments are blanked first; a JSX prop spread ({...props}) suppresses img-alt and input-label;
colours other than 3/6/8-digit hex are ignored by low-contrast; unreadable files are errors, not findings.
Side effects: none (read-only).
"""
import json
import re
import sys
from bisect import bisect_left
from pathlib import Path

EXTS = {".html", ".htm", ".css", ".jsx", ".tsx"}
TOKEN_NAMES = ("tokens.css", "tokens.json", "design-tokens.json")
TEXT_SEL = {"body", "html", ":root", "p", "li"}
HEX = re.compile(r"#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b")
TAG = re.compile(r"<(/?)([a-zA-Z][\w:.-]*)((?:[^<>\"'{}]|\"[^\"]*\"|'[^']*'|\{(?:[^{}]|\{[^{}]*\})*\})*)>")
STYLE_BLOCK = re.compile(r"<style\b[^>]*>(.*?)</style>", re.S | re.I)
CSS_RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
INLINE = re.compile(r"""\bstyle\s*=\s*(?:"([^"]*)"|'([^']*)'|\{\{(.*?)\}\})""", re.S)
MOTION = re.compile(r"@keyframes|animation\s*:\s*([^;}]*)")


def first_motion(text):
    """Match of the first @keyframes or animation declaration naming something other than none, else None."""
    for m in MOTION.finditer(text):
        if m.group(1) is None or any(i.strip().lower() not in ("", "none") for i in re.sub(r"!\s*important", "", m.group(1)).split(",")):
            return m
    return None


def blank(text):
    """Replace comments with spaces, keeping newlines so line numbers survive."""
    return re.sub(r"<!--.*?-->|/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.S)


def line_finder(text):
    """pos -> 1-based line number in O(log n) (offsets of every newline, bisected)."""
    nl = [m.start() for m in re.finditer("\n", text)]
    return lambda pos: bisect_left(nl, pos) + 1


def split_top(s, seps):
    """Split on seps outside parentheses and quotes."""
    out, cur, depth, q = [], "", 0, ""
    for ch in s:
        if q:
            q = "" if ch == q else q
        elif ch in "\"'":
            q = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch in seps and depth == 0:
            out.append(cur)
            cur = ""
            continue
        cur += ch
    return out + [cur]


def decls(body, jsx=False):
    d = {}
    for part in split_top(body, ",;" if jsx else ";"):
        if ":" not in part:
            continue
        k, v = part.split(":", 1)
        k = k.strip().strip("'\"")
        if jsx:
            k = re.sub(r"([a-z])([A-Z])", r"\1-\2", k)
            v = v.strip().strip("'\"")
        d[k.lower()] = v.strip().lower()
    return d


def units(text, ext, line_of):
    """(line, selector, decls) for every CSS rule, <style> body and inline style (selector = its tag name)."""
    out, ranges = [], []
    if ext == ".css":
        ranges = [(0, text)]
    elif ext in (".html", ".htm"):
        ranges = [(m.start(1), m.group(1)) for m in STYLE_BLOCK.finditer(text)]
    for off, css in ranges:
        for m in CSS_RULE.finditer(css):
            out.append((line_of(off + m.start(2)), m.group(1).strip().lower(), decls(m.group(2))))
    for m in INLINE.finditer(text):
        body = m.group(1) or m.group(2) or m.group(3) or ""
        tag = re.compile(r"<([\w:.-]+)").match(text, max(text.rfind("<", 0, m.start()), 0))
        out.append((line_of(m.start()), tag.group(1).lower() if tag else "", decls(body, jsx=m.group(3) is not None)))
    return out


def norm(h):
    h = h.lower()[:6] if len(h) == 8 else h.lower()
    return "".join(c * 2 for c in h) if len(h) == 3 else h


def lum(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def ratio(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def px(v):
    m = re.fullmatch(r"([\d.]+)(px|rem|em)", v)
    return None if not m else float(m.group(1)) * (1 if m.group(2) == "px" else 16)


def find_tokens(path):
    """Nearest tokens file walking up from the file to the nearest .git (the repo root). With no .git above
    the file the bound is the cwd, or the file's own directory when it is outside the cwd."""
    cwd = Path.cwd().resolve()
    dirs = [path.parent, *path.parent.parents]
    root = next((d for d in dirs if (d / ".git").exists()), cwd if cwd in dirs else dirs[0])
    for d in dirs[:dirs.index(root) + 1]:
        for n in TOKEN_NAMES:
            if (d / n).is_file():
                return d / n
    return None


def hexset(tok):
    return {norm(m.group(1)) for m in HEX.finditer(tok.read_text(errors="replace"))}


def base(sel):
    """Selector with its :focus / :focus-visible pseudo-class removed."""
    return sel.replace(":focus-visible", "").replace(":focus", "").strip()


def ring_bases(text):
    """Selector bases (see base) whose :focus-visible rule draws a real ring: an outline or box-shadow that is not none."""
    out, seen = set(), set()
    braces = [m.start() for m in re.finditer(r"[{}]", text)]  # bisect these: scanning back per hit is quadratic
    for hit in re.finditer(r":focus-visible", text):
        k = bisect_left(braces, hit.start())  # braces[k - 1] opens the selector, braces[k] should be its "{"
        if k in seen or k + 1 >= len(braces) or text[braces[k]] != "{" or text[braces[k + 1]] != "}":
            continue
        seen.add(k)  # one rule is evaluated once, however many :focus-visible mentions its selector holds
        start, end = (braces[k - 1] + 1 if k else 0), braces[k]
        if re.search(r"box-shadow\s*:\s*(?!\s)(?!none\b)|outline\s*:\s*(?!\s)(?!(?:none|0)\b)", text[end:braces[k + 1]]):
            out |= {base(s) for s in text[start:end].split(",")}
    return out


def lint_text(text, ext, tokens=None):
    """Findings [(line, rule, message)] for one file's text; tokens is a set of normalised hexes or None."""
    text = blank(text)
    line_of = line_finder(text)
    f = []
    jsx = ext in (".jsx", ".tsx")
    rings = ring_bases(text)
    for line, sel, d in units(text, ext, line_of):
        sels = {s.strip() for s in sel.split(",")}
        bg = d.get("background-color", d.get("background", ""))
        clip = d.get("background-clip", d.get("-webkit-background-clip"))
        if clip == "text" and "gradient" in bg + d.get("background-image", ""):
            f.append((line, "gradient-text", "gradient fill clipped to text hurts legibility; use a solid colour"))
        fg, back = HEX.search(d.get("color", "")), HEX.search(bg)
        if fg and back and "gradient" not in bg:  # a gradient has no single background colour to measure
            r = ratio(norm(fg.group(1)), norm(back.group(1)))
            size, wt = px(d.get("font-size", "")) or 0, d.get("font-weight", "")
            bold = wt in ("bold", "bolder") or (wt.isdigit() and int(wt) >= 700)
            need = 3.0 if size >= 24 or (bold and size >= 18.66) else 4.5  # WCAG large text
            if r < need:
                f.append((line, "low-contrast", f"contrast {r:.2f}:1 is under {need:g}:1"))
        if sels & TEXT_SEL:
            s = px(d.get("font-size", ""))
            if s is not None and s < 14:
                f.append((line, "small-body-font", f"body text at {s:g}px is under 14px"))
            lh = d.get("line-height", "")
            if re.fullmatch(r"[\d.]+", lh) and float(lh) < 1.2:
                f.append((line, "tight-line-height", f"line-height {lh} is under 1.2"))
        replaced = any(k in d for k in ("box-shadow", "border", "border-bottom", "text-decoration"))
        legit = all(base(s) in rings for s in sels) or "not(:focus-visible)" in sel or ":focus:not" in sel
        if d.get("outline", d.get("outline-style", "")) in ("none", "0", "0px") and not replaced and not legit:
            f.append((line, "outline-removed", "focus ring removed with no replacement indicator"))
        for v in d.values() if tokens is not None else ():
            for m in HEX.finditer(v):
                if norm(m.group(1)) not in tokens:
                    f.append((line, "off-token-hex", f"#{m.group(1)} is not in the tokens file"))
    for i, l in enumerate(text.split("\n"), 1):
        if "bg-clip-text" in l and "bg-gradient" in l:
            f.append((i, "gradient-text", "gradient fill clipped to text hurts legibility; use a solid colour"))
    m = first_motion(text) if ext in (".css", ".html", ".htm") else None
    if m and "prefers-reduced-motion" not in text:
        f.append((line_of(m.start()), "no-reduced-motion", "animation with no prefers-reduced-motion fallback"))
    prev = labels = 0
    for m in TAG.finditer(text):
        closing, name, a = m.group(1), m.group(2), m.group(3)
        if jsx and name != name.lower():
            continue
        name, line = name.lower(), line_of(m.start())
        if name == "label":
            labels += -1 if closing else 1
        if closing:
            continue
        has = lambda attr: re.search(r"(?<![\w-])" + attr + r"(?![\w-])", a, re.I)
        spread = re.search(r"\{\s*\.\.\.", a)
        if re.fullmatch(r"h[1-6]", name):
            lvl = int(name[1])
            if prev and lvl > prev + 1:
                f.append((line, "heading-skip", f"<h{lvl}> follows <h{prev}>"))
            prev = lvl
        if name == "img" and not has("alt") and not spread:
            f.append((line, "img-alt", "<img> has no alt attribute"))
        t = re.search(r"tabindex\s*=\s*[{\"']+\s*(\d+)", a, re.I)
        if t and int(t.group(1)) > 0:
            f.append((line, "positive-tabindex", f"tabindex={t.group(1)} overrides natural focus order"))
        if name in ("div", "span", "li", "p", "section") and has("onclick") and not has("role"):
            f.append((line, "click-non-semantic", f"<{name}> with a click handler and no role; use a button or link"))
        if name == "meta" and has("viewport") and re.search(r"user-scalable\s*=\s*(no|0)|maximum-scale\s*=\s*1(\.0)?\b", a, re.I):
            f.append((line, "zoom-blocked", "viewport meta blocks pinch zoom"))
        if name == "html" and not has("lang"):
            f.append((line, "html-lang", "<html> has no lang attribute"))
        hidden = re.search(r"type\s*=\s*[\"']?(hidden|submit|button|image|reset)", a, re.I)
        named = any(has(x) for x in ("id", "aria-label", "aria-labelledby", "title"))
        if name in ("input", "select", "textarea") and not (spread or hidden or named or labels > 0):
            f.append((line, "input-label", f"<{name}> has no accessible label"))
        if name == "a" and re.search(r"href\s*=\s*[\"']?(#|javascript:(void\(0\)|;))[\"']", a, re.I):
            f.append((line, "dead-link", "link goes nowhere"))
    return f


def files(paths):
    for p in map(Path, paths):
        if p.is_dir():
            yield from (q for q in sorted(p.rglob("*")) if q.suffix in EXTS and q.is_file()
                        and not any(x == "node_modules" or x.startswith(".") for x in q.relative_to(p).parts))
        elif p.is_file():
            if p.suffix in EXTS:
                yield p
        else:
            raise FileNotFoundError(p)


def lint_paths(paths, tokens_file=None):
    out, cache = [], {}
    for p in files(paths):
        tf = Path(tokens_file) if tokens_file else find_tokens(p.resolve())
        if tf is not None and tf.resolve() == p.resolve():
            continue
        if tf is not None and tf not in cache:
            cache[tf] = hexset(tf)
        for line, rule, msg in lint_text(p.read_text(errors="replace"), p.suffix, cache.get(tf)):
            out.append({"path": str(p), "line": line, "rule": rule, "message": msg})
    return out


def main(argv):
    as_json = hook = False
    tokens, paths, it = None, [], iter(argv)
    for a in it:
        if a == "--json":
            as_json = True
        elif a == "--hook":
            hook = True
        elif a == "--tokens":
            tokens = next(it, None)
            if tokens is None:
                print("lint_ui_slop: --tokens needs a file", file=sys.stderr)
                return 1
        elif a.startswith("-"):
            print(f"lint_ui_slop: unknown option {a}", file=sys.stderr)
            return 1
        else:
            paths.append(a)
    try:
        if hook:
            fp = (json.load(sys.stdin).get("tool_input") or {}).get("file_path")
            paths = [fp] if fp and Path(fp).is_file() else []
        elif not paths:
            print("usage: lint_ui_slop.py [--json] [--tokens FILE] PATH... | --hook", file=sys.stderr)
            return 1
        found = lint_paths(paths, tokens)
    except (OSError, ValueError) as e:
        print(f"lint_ui_slop: {e}", file=sys.stderr)
        return 1
    if as_json:
        print(json.dumps(found, indent=1))
    else:
        for x in found:
            print(f"{x['path']}:{x['line']}: {x['rule']}: {x['message']}", file=sys.stderr if hook else sys.stdout)
    return 2 if found else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
