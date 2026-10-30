#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=deny a GitHub write whose title or body matches the repo banlist except into a sibling repo of the origin owner and deny a write into Perun that names the session repository, review=2027-01-30
"""privacy_guard.py — PreToolUse(Bash) hook: DENY a GitHub write whose title or body matches the repo's banlist (a write into a sibling
repository of the session origin's owner is not scanned), and a write into the public Perun repository (SELF_REPO) that names the
repository of the session it is filed from.

WHY: the privacy gate scans the files a repo ships, and nothing scanned the text an agent publishes through `gh` or the API, so a
public issue body that named a private repository stayed up for weeks. This hook runs the repo's own banlist over the title and
body of each GitHub write before it is sent. A project's banlist does not list the project's own name (it is all over its files), so a
field report filed from that project's session into the public Perun repository carried the name past the banlist; the own-repository
rule below closes that.

Covers what comms_guard.py covers, through its extraction (imported, not copied): Bash `gh pr|issue|release create|edit|comment`,
and `curl` or `gh api` calls to repos/<owner>/<repo>/pulls or /issues. Title: `--title`/`-t`, `-f title=...`, JSON `title`. Body:
`--body`/`-b`/`--notes`, a heredoc, `$(cat FILE)`, `--body-file`/`-F FILE`, `-d`/`--input` JSON, `-f body=...`, `-F body=@FILE`. `-f`
text is scanned as typed (`@jane` is a mention); `-F` reads `@FILE`, and a file it cannot read is scanned as typed. Every write in a
command is read. A body file the same command writes (`> F`, `>> F`, `tee F`) is read from the heredoc that feeds it, not from the
disk, which holds an old copy or none; what it writes any other way (`echo`, `printf`, `cp`) is not read. Not covered: `gh pr
merge|review`, `gh issue|pr close --comment`, `gh repo edit`, `--fill`, PATCH of `issues/comments/ID`, POST of `pulls/N/comments/M/replies`,
`repos/<o>/<r>/releases`, `gh api graphql`, `curl --data-urlencode` and `--json`; a body fed to stdin by a pipe or `<` (`-F -`,
`--body-file -`; a heredoc is read); text that a shell variable or a command substitution other than `cat FILE` produces at run time; a
single-quoted value with an escaped quote inside, a `$'...'` string, `-b"text"` with no space; a relative body file after `cd DIR &&`
(read from the payload `cwd`, not DIR).

Patterns: the actionable lines (non-blank, first non-space character not `#`) of `.banlist.txt`, then `.banlist.local.txt`, at the git
top-level of the payload `cwd`; a linked worktree lacks the gitignored local file, so the main checkout's is read instead. Each line
is an ERE run through `grep -E` over each line of the text, as `scripts/ci-gates.sh privacy` does: case-sensitive, and an invalid ERE
is skipped here (the gate fails closed on it).

Scope: the banlist is the session repo's and runs over every write except one whose explicit target is another repository of the
session origin's owner (a sibling): a private repository's name belongs in a write into that repository. The session's own repository
(named or implicit), SELF_REPO, every other owner's repository and a session with no usable `origin` stay scanned: a private target
cannot be told from a public one without a network call, and a wrong deny is cheaper than a leak. Residuals: a public sibling in the
origin's organisation is not scanned, and another owner's private repository is, so a legitimate name in it is denied. The target is
`-R`/`--repo OWNER/REPO` (quoted, or with a `github.com/` host), a github.com URL, or a `repos/OWNER/REPO/(issues|pulls)` path, read from
the write's own region only: from the write to the next gh or curl write or the end of its command line (`&&`, `||`, `;`, `|`, a
newline, a `#` comment), with each heredoc body, each quoted string that holds a space and a one-word title or body blanked first, so
text that only mentions a repository (a body quoting `-R acme/other`, a later `echo`) sets no target. A `.git` suffix is dropped. A
write that names several repositories is skipped only when every one is a sibling; a target set by `GH_REPO` is not seen.

Own-repository rule: a write that targets SELF_REPO (read as above) from a session whose `origin` remote names another repository is
denied when its title or a body line names that repository, as `owner/name` or as the bare name (case-insensitive, whole word; a short
plain name is skipped, see `_own_names`). No network: a missing `origin`, an unparsable URL or a session inside SELF_REPO has no such
rule, and a target set by `GH_REPO` is not seen.

Output: on a hit, exit 2 and a stderr reason that names each hit as `title` or `body line N`, a banlist hit adding the pattern's 1-based
number among the actionable lines above. The matched text and the repository's name are never printed. Otherwise exit 0 and print nothing.
FAIL OPEN: a non-Bash tool, no git repo, no banlist, no title or body, an unreadable body file (a readable title is still checked),
bad stdin, a missing `grep` or `git`, or any error allows. Register it WITHOUT `|| true`, which would turn the deny into an allow. Opt
out for a session or a project with `PERUN_PRIVACY_GUARD=off` (settings `env`; a `VAR=off` prefix on the command never reaches a hook).
Side effects: read-only `git rev-parse` and `git remote get-url`, `grep` and file reads; no network. Test: scripts/test_privacy_guard.py.
"""
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SHOWN = 5  # hits named in the deny reason
SELF_REPO = "protocol/perun"  # lower case; same constant as contribution/scripts/prefile_check.sh
# A repository a write names: `-R`/`--repo OWNER/REPO` (quoted, or with a github.com host), a github.com URL, or a REST path `repos/OWNER/REPO/issues`.
TARGETS = re.compile(r"(?:(?<![\w-])(?-i:--repo[ =]+|-R[ =]*)[\"']?(?:github\.com/)?|https?://github\.com/|git@github\.com:)([\w.-]+)/([\w.-]+)"
                     r"|\brepos/([\w.-]+)/([\w.-]+)/(?:pulls|issues)\b", re.I)
END = re.compile(r"&&|\|\||[;|]|(?<!\\)\n|(?<=\s)#")  # the end of a command line: a separator, a newline that is not escaped, a comment


def _git(cwd, *args):
    try:
        r = subprocess.run(["git", "-C", cwd or ".", *args], capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):  # no git, or too slow: nothing to read, so the caller allows
        return ""
    return r.stdout.strip() if r.returncode == 0 else ""


def patterns(cwd):
    """The actionable banlist lines (the rule of ci-gates.sh collect_patterns), .banlist.txt then .banlist.local.txt; [] outside a repo."""
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if not top:
        return []
    local, common = os.path.join(top, ".banlist.local.txt"), _git(cwd, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if common and not os.path.isfile(local):  # gitignored, so a linked worktree lacks it: use the main checkout's
        local = os.path.join(os.path.dirname(common), ".banlist.local.txt")
    out = []
    for f in (os.path.join(top, ".banlist.txt"), local):
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                out += [s for s in (ln.lstrip() for ln in fh.read().split("\n")) if s and not s.startswith("#")]
        except OSError:
            pass
    return out


def scan(text, pats):
    """[(line number, pattern number)] for each pattern that matches a line of `text`: one `grep -E` per pattern, as the privacy gate runs it."""
    if not text or not pats:
        return []
    data = text.encode("utf-8", "replace")

    def grep(*args):
        return subprocess.run(["grep", "-aE", *args], input=data, capture_output=True, timeout=10)

    if grep("-q", *[a for p in pats for a in ("-e", p)]).returncode == 1:  # 1: no pattern matches, so there is nothing to locate
        return []
    hits = []
    for i, p in enumerate(pats, 1):
        r = grep("-n", "-e", p)
        if r.returncode == 0:  # 1: no match; 2: an invalid ERE, skipped
            hits += [(int(n), i) for n in re.findall(rb"^(\d+):", r.stdout, re.M)]
    return hits


def _origin(cwd):
    """(owner, name), lower case, of the session's `origin` remote, or None when there is none, it is unparsable or it is SELF_REPO itself."""
    m = re.search(r"([^/:\s]+)/([^/:\s]+?)(?:\.git)?/?$", _git(cwd, "remote", "get-url", "origin"))
    return None if not m or "/".join(m.groups()).lower() == SELF_REPO else tuple(g.lower() for g in m.groups())


def _own_names(cwd, origin=None):
    """Regex for the names of the session's own repository, read from its `origin` remote (or given as `origin`), or None when there is
    no usable `origin` or the session is in SELF_REPO itself. Matches `owner/name`, and the bare name when it is distinctive;
    case-insensitive, whole word."""
    o = origin or _origin(cwd)
    if not o:
        return None
    # ponytail: the bare name counts only when distinctive (it holds - _ . or has 8+ characters). A short plain name (`app`, `api`) is an
    # ordinary word and would deny normal text, so it is caught only as owner/name. Upgrade: a list of the session's own words (org, package).
    names = ["/".join(o)] + ([o[1]] if re.search(r"[-_.]", o[1]) or len(o[1]) >= 8 else [])
    return re.compile(rf"(?<!\w)(?:{'|'.join(map(re.escape, names))})(?!\w)", re.I)


def _sibling(target, origin):
    """True when `target` ("owner/name") is another repository of the origin's owner; SELF_REPO never is."""
    return target.split("/")[0] == origin[0] and target not in ("/".join(origin), SELF_REPO)


def _try(fn, *args):
    try:
        v = fn(*args)
    except (OSError, ValueError, AttributeError):  # unreadable file, non-JSON data
        return ""
    return v if isinstance(v, str) else ""


def _targets(G, tail, after, end, texts):
    """The `owner/name` (lower case) of each repository a write names in its own region: `tail` (the command text from the write on)
    up to offset `end`, the next write, or to the end of its command line found after offset `after`, the end of the write's own match.
    A heredoc body, a quoted string that holds a space and a one-word title or body are blanked first: text only mentions a repository."""
    plain = G._plain(tail, lambda s: not re.search(r"\s", s))  # a quoted `-R "o/r"` or URL has no space and stays
    cut = END.search(plain, after)
    plain = plain[:max(after, min(end, cut.start() if cut else end))]
    for t in texts:
        if t and len(t) < 400 and len(t.split()) == 1:  # whole word only: a title `t` must not eat the `t` of `protocol/perun`
            plain = re.sub(rf"(?<![^\s\"'=]){re.escape(t)}(?![^\s\"'])", " ", plain)
    return [re.sub(r"\.git$", "", f"{a or c}/{b or d}".lower()) for a, b, c, d in TARGETS.findall(plain)]  # a clone URL ends in .git


def outgoing(cmd, cwd):
    """[(targets, title, body)] for each covered GitHub write in `cmd`, `targets` being the repositories it names (see `_targets`); ""
    stands for a part that is absent or unreadable, and [] for no write. A body file the command writes itself reads as the heredoc that
    feeds it."""
    sys.path.insert(0, HERE)
    import comms_guard as G
    disk, out = G._read, []

    def read(path, cwd):  # the command writes this file itself: the disk holds an old copy or none, so read the heredoc that feeds it
        lines = {cmd.rfind("\n", 0, w.start()) for w in re.finditer(rf"(?:>>?|\btee\s+(?:-\S+\s+)*)\s*[\"']?{re.escape(path)}[\"']?(?=[\s;&|)]|$)", cmd)}
        if not lines:
            return disk(path, cwd)
        return "\n".join(h.group(3) for h in G.HEREDOC.finditer(cmd) if cmd.rfind("\n", 0, h.start()) in lines)  # the heredoc opens on the line of the redirect: `cat > F <<'EOF'`

    G._read = read  # ponytail: patched around the extraction so it stays imported, not copied (one hook process, one command)
    try:
        writes = sorted([*G.GH.finditer(cmd), *G.REST.finditer(cmd)], key=lambda m: m.start())
        for i, m in enumerate(writes):
            tail = cmd[m.start():]
            if m.re is G.GH:
                title = _try(lambda: next((G._value(r, cwd) for r in G._flags(tail, r"--title|-t")), None))
                body = _try(G._gh_body, tail, m.group(1), cwd)
            else:
                title, body = _try(G._rest_field, tail, cwd, "title", True), _try(G._rest_field, tail, cwd, "body", True)
            end = writes[i + 1].start() - m.start() if i + 1 < len(writes) else len(tail)
            out.append((_targets(G, tail, m.end() - m.start(), end, (title, body)), title, body))
    finally:
        G._read = disk
    return out


def _named(hits):
    """The first SHOWN hits joined by `; `, then how many more there are."""
    return "; ".join(hits[:SHOWN]) + (f"; {len(hits) - SHOWN} more" if len(hits) > SHOWN else "")


def verdict(cmd, cwd):
    """(exit code, stderr text) for one Bash command: 2 and a reason without the matched text or the session repo's name when a title or
    body line matches the banlist (a write to a sibling repository of the origin's owner is not scanned) or, in a write to SELF_REPO,
    names the session's own repository."""
    if not re.search(r"\b(?:gh|curl)\b", cmd):
        return 0, ""
    writes = [w for w in outgoing(cmd, cwd) if w[1] or w[2]]
    if not writes:
        return 0, ""
    pats = patterns(cwd)
    origin = _origin(cwd) if any(w[0] for w in writes) else None  # no usable origin: every write is scanned and there is no own-repository rule
    names = _own_names(cwd, origin) if origin else None
    ban, own = [], []
    for targets, title, body in writes:
        if not (origin and targets and all(_sibling(t, origin) for t in targets)):
            ban += [("title", i) for _, i in scan(title, pats)] + [(f"body line {n}", i) for n, i in scan(body, pats)]
        if names and SELF_REPO in targets:
            own += (["title"] if names.search(title) else []) + [f"body line {n}" for n, ln in enumerate(body.split("\n"), 1) if names.search(ln)]
    msg = []
    if ban:
        msg.append("Blocked: the title or body of this GitHub write matches the repo banlist (matched text withheld): "
                   f"{_named([f'{where} (pattern {i})' for where, i in dict.fromkeys(ban)])}. Remove or reword that text and send it again. "
                   "Patterns are numbered over the actionable lines of .banlist.txt, then .banlist.local.txt.")
    if own:
        msg.append(f"Blocked: this write to {SELF_REPO} names the session's own repository (name withheld): {_named(list(dict.fromkeys(own)))}. "
                   "Reword that text without the repository's name and send it again.")
    return (2, " ".join(msg)) if msg else (0, "")


def main():
    if os.environ.get("PERUN_PRIVACY_GUARD", "").lower() in ("off", "0", "false"):
        return 0
    try:
        data = json.load(sys.stdin)
        if data.get("tool_name") != "Bash":
            return 0
        code, msg = verdict(str((data.get("tool_input") or {}).get("command") or ""), str(data.get("cwd") or ""))
    except Exception:  # fail open: a broken privacy hook must never block work
        return 0
    if msg:
        print(msg, file=sys.stderr)
    return code


if __name__ == "__main__":
    sys.exit(main())
