#!/usr/bin/env python3
"""pipefail_sigpipe.py - lead-finder for `producer | grep -q ...` / `| head` in a shell condition under `set -o pipefail`.

Usage: python3 -I pipefail_sigpipe.py < paths   (shell file paths on stdin, one per line)

Under pipefail, grep -q/-m and head exit early; a producer that writes in several chunks (git log/ls-files/diff, find, cat FILE, curl, gh,
grep -r, ls ...) then dies of SIGPIPE (141), the pipeline reads false although the pattern matched, and the branch silently flips.
Only the FIRST pipeline stage is judged, and it must be a generator. Filters (grep/sed/cut/tr/sort/uniq/awk/jq/head/tail/wc) usually write
one small chunk, so they are not producers; grep/egrep/fgrep count only with -r/-R/--recursive, rg always (recursive by default); cat only with a file argument.
shellcheck does not flag it. Rows, TSV `file<TAB>line<TAB>rule<TAB>message`, report-only, stdlib only:
- pipefail-sigpipe: a line after a pipefail setting where a multi-write generator pipes into grep -q/-m/head in a condition (if/elif/while/until/!, or beside && / ||).
- not-checked: a file that could not be read.
Skipped: single-write producers (echo, printf, here-strings), pipelines inside $(...) or backticks, and lines ending `|| true` or reading PIPESTATUS.
Fix: `grep -q PAT <<<"$(producer)"`. Line-based: a lead, confirm it in the file.
"""
import re
import sys

PIPEFAIL = re.compile(r"^\s*set\s+(?:[-+]\w+\s+)*-\w*o\s+pipefail\b")
NOPIPEFAIL = re.compile(r"^\s*set\s+(?:[-+]\w+\s+)*\+\w*o\s+pipefail\b")
HEREDOC = re.compile(r"<<-?\s*['\"]?(\w+)['\"]?")
GIT_MULTI = {"log", "ls-files", "diff", "show", "branch", "tag", "status", "grep", "ls-tree", "for-each-ref", "rev-list",
             "diff-tree", "ls-remote", "blame", "shortlog", "cat-file", "ls-tree", "reflog", "stash"}
PRODUCERS = {"find", "curl", "ls", "gh", "tac", "xxd", "od", "seq", "ps", "zgrep", "tar", "unzip", "zcat", "npm", "pip", "docker",
             "python3", "python", "strings"}
RECURSIVE = re.compile(r"^(-[A-Za-z]*[rR][A-Za-z]*|--recursive)$")
SINK = re.compile(r"^(grep|egrep|fgrep|rg)\b(?=.*(\s-[A-Za-z]*q|\s--quiet|\s-m\s*\d|\s-[A-Za-z]*m\d|--max-count))|^head\b")
COND = re.compile(r"^\s*(if|elif|while|until|!)\b|&&|\|\||;\s*then\b")
SKIP = re.compile(r"\|\|\s*true\s*(;|$)|PIPESTATUS")
SUBST = re.compile(r"\$\([^()]*\)|`[^`]*`")
ARM = re.compile(r"^\s*(case\s.*\sin\s+)?[^\s()|]+(\|[^\s()|]+)*\)\s*")  # a case-arm label stays in front of the producer
QUOTE = re.compile(r"'[^']*'|\"[^\"]*\"")


def clean(t):
    """t with $(...)/backtick bodies and quoted strings emptied, so only top-level pipes remain."""
    prev = None
    while prev != t:
        prev, t = t, SUBST.sub("S", t)
    t = QUOTE.sub('""', t)
    return re.sub(r"\s#.*$", "", t)


def multi(stage):
    w = stage.split()
    while w:
        if w[0] in ("if", "elif", "while", "until", "!", "then", "do", "{", "(", "command", "env", "time") or "=" in w[0].split("/")[0]:
            w = w[1:]
        elif w[0] == "nice":
            w = w[3:] if w[1:2] == ["-n"] else w[1:]
        else:
            break
    if not w or "<<" in stage:
        return False
    if w[0] == "git":
        i = 1
        while i < len(w) and w[i].startswith("-"):
            i += 2 if w[i] in ("-C", "-c") else 1
        return i < len(w) and w[i] in GIT_MULTI
    if w[0] == "rg":  # recursive by default (-r means replace)
        return True
    if w[0] in ("grep", "egrep", "fgrep"):
        return any(RECURSIVE.match(a) for a in w[1:])
    if w[0] == "cat":
        return any(not a.startswith("-") and a not in ("<", "<<<") for a in w[1:])
    return w[0] in PRODUCERS


def scan(path, text):
    rows, on, lines, i, term = [], False, text.splitlines(), 0, None
    while i < len(lines):
        j, t = i, lines[i]
        if term:
            term = None if t.strip() == term else term
            i += 1
            continue
        while j + 1 < len(lines) and (t.rstrip().endswith("\\") or re.search(r"(^|[^|])\|$|&&$|\|\|$", t.rstrip())) and not t.lstrip().startswith("#"):
            j += 1
            t = t.rstrip()
            t = (t[:-1] if t.endswith("\\") else t) + " " + lines[j].strip()
        h = HEREDOC.search(re.sub(r"<<<", "", t))
        if h:
            term = h.group(1)
        if NOPIPEFAIL.match(t):
            on = False
        elif PIPEFAIL.match(t):
            on = True
        elif on and not t.lstrip().startswith("#") and "sigpipe-ok" not in t and not SKIP.search(t):
            c = clean(t)
            if COND.search(c):
                for seg in re.split(r"&&|\|\||;", c):
                    st = [s.strip() for s in re.split(r"(?<!\|)\|(?!\|)", ARM.sub("", seg, 1))]
                    if len(st) > 1 and multi(st[0]) and any(SINK.match(re.sub(r"^(if|elif|while|until|!|then)\s+", "", s)) for s in st[1:]):
                        rows.append((path, i + 1, "pipefail-sigpipe", "multi-write producer piped into grep -q/-m/head under pipefail: SIGPIPE (141) can read false; use grep -q PAT <<<\"$(producer)\""))
                        break
        i = j + 1
    return rows


def main():
    for path in (p.rstrip("\n") for p in sys.stdin if p.strip()):
        try:
            with open(path, encoding="utf-8", errors="replace") as f:
                rows = scan(path, f.read())
        except OSError as e:
            rows = [(path, 0, "not-checked", f"could not read: {e.strerror}")]
        for r in rows:
            print("\t".join(map(str, r)), flush=True)


if __name__ == "__main__":
    main()
