#!/usr/bin/env python3
"""audit_skills: static supply-chain audit of an installed skills directory.

Usage: python3 scripts/audit_skills.py SKILLS_DIR [--json] [--honor-markers] [--allow-host HOST ...]

Scans every file under SKILLS_DIR (SKILL.md, references, scripts, hooks, dotfiles; only `.git/objects` is skipped)
line by line (a trailing backslash joins the next line) for:
  curl-pipe       network fetch run as code: piped to a shell/interpreter, eval/source of a fetch, fetch && sh
  net-host        a fetch/request line naming a host outside the allowlist (default hosts below + --allow-host)
  hidden-unicode  bidi controls, zero-width, soft-hyphen, tag and variation-selector characters in file content or file/directory names
  control-char    NUL and other C0 control characters (all but tab, LF, CR, FF) in a text file, reported with line, column and codepoint
  b64-exec        base64-decoded text executed, PowerShell encoded commands
  sensitive-write a write to agent settings, MCP config, CLAUDE.md/AGENTS.md, hooks, shell rc or credential files
  rm-broad        `rm -rf` on root, home, a system directory, a glob or a variable-prefixed path
  prompt-inject   instruction-override phrasing (any file: references and templates are read by the agent too)
  unscanned       a file the scanner could not read as text: binary (NUL byte), over 1 MB, or a symlink. Never skipped silently.

By default no line can suppress a finding, because the skill under audit is untrusted. With --honor-markers (for
skills you own), a line carrying `audit-skills: ignore <rule>` drops only that rule on that line; the number of
suppressed findings is still printed.
Exit 0 = clean, 2 = findings, 1 = error or usage error. Output `path:line: severity rule: message`, or a JSON list
with --json. Zero-width joiner/non-joiner and VS16 are flagged only beside ASCII, so emoji and Persian text stay clean. Heuristic and
line-based: it cannot see payloads built at runtime, so a clean run is evidence, not a guarantee. Read-only; stdlib only.
Limits: the host allowlist names well-known origins, not trusted content (anyone can publish on github.com or pypi.org),
so a fetch from them is judged by curl-pipe, and only when the fetch and the run share a line (fetch to a file on one line,
run it on the next, is not seen); phrase lists are heuristics; ZWJ/ZWNJ between two non-ASCII letters are not flagged.
"""
import argparse, json, os, re, sys
from urllib.parse import urlsplit

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "deep-code-review", "scripts"))
_wb, sys.dont_write_bytecode = sys.dont_write_bytecode, True  # the import must not drop a __pycache__ into the skills tree this tool audits
from invisible_chars import BINARY_EXT, HIDDEN, control_findings, decode, unflag  # noqa: E402  one home for the bidi/zero-width and NUL/C0 rules; review_checks.sh runs the same code
sys.dont_write_bytecode = _wb

ALLOW_HOSTS = ("github.com", "githubusercontent.com", "pypi.org", "pythonhosted.org", "npmjs.org", "anthropic.com",
               "claude.com", "example.com", "example.org", "example.net", "localhost", "127.0.0.1")
MAX_BYTES = 1_000_000
FETCH = r"(?:curl|wget|Invoke-WebRequest|iwr|Invoke-RestMethod|irm)\b"
INTERP = r"(?:python[0-9.]*|node|perl|ruby)"  # `| python3 -c 'parse json'` is routine; only bare or exec/eval-ing interpreters count
SH = r"(?:(?:sudo|env|nohup|exec)\s+(?:-\S+\s+)*)*(?:/(?:usr/)?(?:local/)?bin/)?(?:ba|z|da|k|a)?sh\b"
SHELL = SH + r"|pwsh\b|iex\b|" + INTERP + r"\b(?!\s+-[ce]\b)|" + INTERP + r"\s+-[ce]\s.*(?:exec|eval)"
CALL = re.compile(FETCH + r"|\bfetch\(|requests\.\w+\(|urlopen\(|httpx\.\w+\(|http\.client|axios\.|\bnc\s|\bsocket\.")
URL = re.compile(r"https?://[^\s\"'<>)\]`]+", re.I)
BARE = re.compile(r"(?<![\w./@:-])([a-z0-9-]+(?:\.[a-z0-9-]+)*\.[a-z]{2,})(?::\d+)?/\S*", re.I)  # `curl attacker.test/i.sh`
SENS = re.compile(r"settings(?:\.local)?\.json|\.mcp\.json|CLAUDE\.md|AGENTS\.md|\.claude/(?:hooks|commands|agents)|\.git/hooks|\.gitconfig|\.config/(?:git|gh)|\.kube/config|"
                  r"\.cursor/|\.codex/|\.ssh/|authorized_keys|\.aws/credentials|\.netrc|\.npmrc|\.pypirc|\.gnupg|"
                  r"\.docker/config\.json|Keychains|\.(?:bash|zsh)rc|\.profile|\.zprofile")
WRITE = re.compile(r"(?<![-=])>{1,2}(?=\s*[~/$\w.\"'])|\btee\b|\bsed\s+-i|\b(?:cp|mv)\s|\binstall\s+-|\bln\s+-|\bdd\s[^\n]*\bof=|\btruncate\b|write_text|\.write\(|json\.dump|shutil\.|"
                   r"open\([^)]*['\"][wa]\+?b?['\"]|appendFile|writeFile")
SKILLDROP = re.compile(r"\b(?:cp|mv|ln|install|rsync|tee|git\s+clone)\s[^\n]*\.claude/skills|(?:^|[\s\d&])>{1,2}\s*[\"']?[^\s\"']*\.claude/skills")  # installs a skill
INJECT = re.compile(  # strong: only an attacker writes this to an agent
    r"(?:ignore|disregard|forget)\s+(?:all\s+|any\s+|and\s+|your\s+|the\s+|every\s+)*(?:previous|prior|above|earlier|preceding)\s+"
    r"(?:instructions?|directions?|directives?|guidance|prompts?|rules?|context|messages?|guardrails?|constraints?|polic(?:y|ies))|"
    r"(?:without|never|don'?t|do not)\s+(?:telling|tell|informing|inform|notifying|notify|alerting|alert)\s+the\s+user|"
    r"(?:keep|hide|conceal)\s+(?:this|it|that)\s+from\s+the\s+user|you\s+are\s+now\s+(?:in\s+)?(?:DAN|developer mode|unrestricted)", re.I)
INJECT_WEAK = re.compile(  # also routine prompt-engineering prose, so medium
    r"override\s+(?:all\s+|your\s+|the\s+)*(?:system|safety)\s+(?:instructions?|prompts?|rules?|guardrails?)|"
    r"(?:reveal|print|output|leak)\s+(?:your\s+|the\s+)?system\s+prompt", re.I)
RMV = r"\$(?:\{(?!TMPDIR)[A-Za-z_]\w*\}|(?!TMPDIR)[A-Za-z_]\w*)[\"']?[/*]"  # var then / or *: unset var becomes /*
RM = r"\brm\s+(?=(?:\S+\s+)*?(?:-[a-zA-Z]*[rR][a-zA-Z]*|--recursive)(?:\s|$))(?:(?:-[a-zA-Z]+|--[\w-]+)\s+)+[\"']?"
PROCSUB = r"(?:\b(?:ba|z|da|k|a)?sh|source|eval|exec|\.)\s+(?:-\w+\s+)*"
CHAIN = r"(?:&&|;|\|\|)\s*(?:" + SH + r"\s|source\s|\.\s|eval\s)"
CHAIN_WEAK = r"(?:&&|;|\|\|)\s*(?:chmod\s+\+x|\./\S)"  # `curl -LO x.tgz && ./configure` is routine install prose
RULES = [  # (rule, severity, regex, message)
    ("curl-pipe", "high", re.compile(
        FETCH + r"[^\n|]*\|\s*(?:" + SHELL + r")|" + PROCSUB + r"[\"']?<\(\s*" + FETCH + r"|" + PROCSUB + r"[\"']?\$\(\s*" + FETCH
        + r"|(?:eval|source|exec)\s.*`\s*" + FETCH + r"|\biex\b.*" + FETCH + r"|" + FETCH + r"[^\n]*" + CHAIN, re.I),
     "network fetch executed as code"),
    ("curl-pipe", "medium", re.compile(FETCH + r"[^\n]*" + CHAIN_WEAK, re.I), "network fetch followed by running a local file (often an installer)"),
    ("b64-exec", "high", re.compile(
        r"base64\s+(?:-d|-D|--decode)[^\n]*\|\s*(?:" + SHELL + r")|(?:exec|eval)\s*\(.*(?:b64decode|atob|base64|fromhex|zlib|decompress|marshal|codecs\.decode)|"
        r"(?:powershell|pwsh)(?:\.exe)?\s(?:[^\n]*\s)?-e(?:c|nc|ncodedcommand)?\s+\S|-EncodedCommand|FromBase64String.*iex", re.I),
     "base64-decoded or encoded command executed"),
    ("rm-broad", "high", re.compile(RM + r"(?:/|~|\$HOME|\$\{HOME\}|\*)(?:[\"'\s/*]|$)"), "rm -rf on root, home or glob"),
    ("rm-broad", "medium", re.compile(RM + r"/(?:usr|etc|var|bin|sbin|lib|lib64|opt|boot|root|home|Users|System|Library)(?:[/\"'\s]|$)"),
     "rm -rf on a system directory"),
    ("rm-broad", "medium", re.compile(RM + RMV), "rm -rf on a variable-prefixed path (use ${VAR:?})"),
]
SOFTHY = "\u00ad"  # invisible but common in pasted prose, so medium
MARKER = re.compile(r"audit-skills:\s*ignore\s+([a-z0-9,\- ]+)")
ALLOW = ALLOW_HOSTS


def host_ok(url):
    try:
        h = (urlsplit(url).hostname or "").lower().rstrip(".")  # hostname drops userinfo (`github.com@evil.test`) and port
    except ValueError:
        return None
    return h, any(h == a or h.endswith("." + a) for a in ALLOW)


def scan_line(n, line):
    """Apply every rule to one logical line; return [(line_no, severity, rule, message)]. Pure; no I/O."""
    out = [(n, sev, rule, msg) for rule, sev, rx, msg in RULES if rx.search(line)]
    line_h = unflag(line)  # flag emoji carry tag characters by design
    if HIDDEN.search(line_h):
        cps = ",".join(sorted({"U+%04X" % ord(c) for c in HIDDEN.findall(line_h)}))
        out.append((n, "high", "hidden-unicode", "bidi/zero-width/tag character " + cps))
    if SOFTHY in line:
        out.append((n, "medium", "hidden-unicode", "soft hyphen U+00AD"))
    if (SENS.search(line) and WRITE.search(line)) or SKILLDROP.search(line):
        out.append((n, "high", "sensitive-write", "write to agent settings, hooks, rc or credential path"))
    if INJECT.search(line):
        out.append((n, "high", "prompt-inject", "instruction-override phrasing"))
    elif INJECT_WEAK.search(line):
        out.append((n, "medium", "prompt-inject", "system-prompt override/disclosure phrasing (often benign prose)"))
    if CALL.search(line):
        urls = URL.findall(line)
        if re.search(FETCH, line, re.I):
            urls += ["//" + m.group(0) for m in BARE.finditer(URL.sub(" ", line))]
        for u in urls:
            r = host_ok(u)
            if r is None or (not r[1]):
                out.append((n, "medium", "net-host", "outbound call to non-allowlisted host " + (r[0] if r else "unparseable URL")))
    return out


def logical_lines(text):
    """(start line number, text) with backslash-continued lines joined; splits on \\n only so numbers match editors."""
    buf, start = "", 0
    for n, l in enumerate(text.replace("\r\n", "\n").replace("\r", "\n").split("\n"), 1):
        if not buf:
            start = n
        if l.endswith("\\"):
            buf += l[:-1] + " "
            continue
        yield start, buf + l
        buf = ""
    if buf:
        yield start, buf


def scan(root, honor_markers=False):
    """Walk `root` and return (findings, suppressed_count); findings are dicts with file/line/severity/rule/message.

    Scans every file except `.git/objects`. Fails closed: binary, oversize and symlinked files and symlinked
    directories become `unscanned` findings, hidden characters in file or directory names are findings, and an
    unreadable directory raises OSError (main turns it into exit 1). Read-only. `suppressed_count` counts
    findings dropped by `audit-skills: ignore <rule>` markers, which only apply when honor_markers is true."""
    found, suppressed = [], 0

    def add(rel, n, sev, rule, msg):
        found.append({"file": rel, "line": n, "severity": sev, "rule": rule, "message": msg})

    def fail(e):
        raise e

    for d, dirs, files in os.walk(root, onerror=fail):
        dirs.sort()
        if os.path.basename(d) == ".git":
            dirs[:] = [x for x in dirs if x != "objects"]  # packed zlib objects: unreadable by design, not code
        for x in list(dirs):
            if HIDDEN.search(x):
                add(os.path.relpath(os.path.join(d, x), root), 0, "high", "hidden-unicode", "bidi/zero-width/tag character in directory name")
            if os.path.islink(os.path.join(d, x)):
                add(os.path.relpath(os.path.join(d, x), root), 0, "medium", "unscanned", "symlinked directory not followed")
                dirs.remove(x)
        for f in sorted(files):
            p = os.path.join(d, f)
            rel = os.path.relpath(p, root)
            if HIDDEN.search(rel):
                add(rel, 0, "high", "hidden-unicode", "bidi/zero-width/tag character in file name")
            if os.path.islink(p):
                add(rel, 0, "medium", "unscanned", "symlink not followed (target is not audited)")
                continue
            if os.path.splitext(f)[1].lower() in BINARY_EXT:
                add(rel, 0, "medium", "unscanned", "binary file (known binary extension) not scanned")
                continue
            if os.path.getsize(p) > MAX_BYTES:
                add(rel, 0, "medium", "unscanned", "file over 1 MB not scanned")
                continue
            with open(p, "rb") as fh:
                raw = fh.read()
            text, binary = decode(raw)
            for n, msg in control_findings(rel, text, binary):
                add(rel, n, "high", "control-char", msg)
            if binary:
                add(rel, 0, "medium", "unscanned", "binary file (NUL byte) not scanned")
                continue
            for n, line in logical_lines(text):
                skip = set()
                if honor_markers:
                    m = MARKER.search(line)
                    skip = set(re.split(r"[ ,]+", m.group(1).strip())) if m else set()
                for n2, sev, rule, msg in scan_line(n, line):
                    if rule in skip:
                        suppressed += 1
                    else:
                        add(rel, n2, sev, rule, msg)
    return found, suppressed


def main(argv=None):
    """CLI entry: return 0 clean, 2 findings, 1 error (bad directory, unreadable path, usage error). Prints to stdout/stderr only."""
    global ALLOW
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--honor-markers", action="store_true", help="honor `audit-skills: ignore <rule>` lines (own skills only)")
    ap.add_argument("--allow-host", action="append", default=[], metavar="HOST")
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:  # argparse exits 2 on a usage error, which here would read as "findings"
        return 0 if e.code in (0, None) else 1
    if not os.path.isdir(a.dir):
        print("audit_skills: not a directory: " + a.dir, file=sys.stderr)
        return 1
    ALLOW = ALLOW_HOSTS + tuple(h.lower() for h in a.allow_host)
    try:
        found, suppressed = scan(a.dir, a.honor_markers)
    except OSError as e:
        print("audit_skills: " + str(e), file=sys.stderr)
        return 1
    if a.json:
        print(json.dumps(found, indent=2))
    else:
        for x in found:
            print("%s:%d: %s %s: %s" % (x["file"], x["line"], x["severity"], x["rule"], x["message"]))
    print("audit_skills: %d finding(s), %d suppressed by markers, in %s" % (len(found), suppressed, a.dir), file=sys.stderr)
    return 2 if found else 0


if __name__ == "__main__":
    sys.exit(main())
