#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=stop starting PRs while ready ones wait unmerged; alarm on a stalled flow, review=2027-01-30
"""flow_alarm.py — three flow checks that read the delivery queue, not the code.

  flow_alarm.py                      PreToolUse(Bash) hook (stdin JSON): STOP STARTING. Denies (exit 2) `gh pr create` while
                                     ready-but-unmerged PRs >= PERUN_STOP_STARTING_READY (default 5): waiting work is queue, and
                                     a new PR only lengthens it. Override for priority work: `# priority: <reason>` in the command.
                                     Gated by the command's text: one without `gh pr create` in it (any case; also read with its
                                     quotes and backslashes removed) passes. One with it, in code, in a comment or in a heredoc
                                     body, is denied unless every command in it is a known text tool (echo, grep, git log, cat ...;
                                     see `gated`), so a grep, an echo, a commit message or an issue body that only names it is
                                     allowed. Anything not known to be text-only keeps the deny: an unknown program or wrapper
                                     (timeout, env, sudo, `bash -c`, `| sh`, `tee`, a path such as `./echo`: the command word must
                                     be a listed name exactly), a variable set before a command unless its name is inert
                                     (GIT_AUTHOR_*, GIT_COMMITTER_*, LANG, LC_*, TZ, NO_COLOR: an editor, a pager, a config entry
                                     or an external diff may run a command), a git subcommand outside log, show, diff, grep,
                                     status, blame, commit and add (`rebase --exec`, `bisect run`, `apply`, `-p`, `--config-env`,
                                     ...), an option that runs or stores a command or writes a file (`git -c`, `git grep -O`, `git
                                     log --output`, `gh alias`, `gh config`, `rg --pre`, `rg --hostname-bin`), `gh api` and `gh
                                     extension`, a `gh pr` followed anywhere, flags or not, by `create`, `new` (its alias) or an
                                     expansion, a `$` or `{` in a git word (an expansion may build such an option: `git log $o`; a
                                     `commit -m` message may expand), a command that writes a file, a `$(...)` that runs it, an
                                     unquoted backtick, `$'..'` quoting, `printf -v`, `${NAME:=..}`, a quote that does not close, a
                                     `#` or `<<` that is not provably a comment or a heredoc, and a heredoc beside a comment. A
                                     failed `gh`, a timeout or unparseable hook JSON allows (fail open). A flow alarm, not a
                                     security boundary. Still passing: `$(which gh) pr create`, `${GH} pr create`, `gh${IFS}pr
                                     create`, `gh $'pr' create` and `gh pr cre{a,}te` (the text is not in the command), a script
                                     written by an editor tool and run later, a `gh` alias or extension that is already installed,
                                     and another allowed tool's own exec flag that `gated` does not list. Over-denied (the safe
                                     direction): a `#` that cannot be proven to start a comment, a single-quoted backtick or `$(`,
                                     a `(`, backtick or open quote after a heredoc marker, a backslash in a delimiter word, a `)`
                                     in a heredoc body inside `$(`, a `$`, `*`, `?`, `[` or `{` in the first two words of `gh` (its
                                     own `{owner}` placeholder) or after `gh pr`, a `$` or `{` in a git word (a `commit -m` message
                                     may) or an rg option, a mention-only pipeline through a command outside SAFE, a non-read git
                                     subcommand (`push`) beside a mention, even one only in a comment, a heredoc written to a file
                                     beside a mention, an assignment of another variable, `printf -v`, `${x:=..}`.
  flow_alarm.py symptom [--hours H] [--red-since TS]
                                     ONE alarm instead of a monitor per invariant. Prints `ALARM flow: N ready PR(s) and nothing
                                     merged in Xh` when ready PRs exist and the last merge is older than H (default 2), and
                                     `ALARM flow: trunk red for Xh` when --red-since (ISO-8601 or epoch) is older than 1h. Exit 1
                                     on any ALARM, 0 healthy, 2 when `gh` fails (fail closed: an unread queue is not healthy).
  flow_alarm.py split FILE.json      value-stream split BEFORE optimizing agents. FILE is a list of {"queuedAt","startedAt",
                                     "readyAt","mergedAt"} (ISO-8601, from the tracker/PR export). Prints median hours for
                                     `waiting-to-start`, `coding`, `ready-to-merged` (queued->started, started->ready, ready->
                                     merged) and the largest stage; rows missing a timestamp are skipped. Exit 2 on bad input.

Ready = open, not draft, at least one check and every check SUCCESS/NEUTRAL/SKIPPED. `PERUN_GH` overrides the gh binary (tests).
`--now EPOCH` pins the clock. Side effects: none (read-only).
"""
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

OK = {"SUCCESS", "NEUTRAL", "SKIPPED"}
MENTION = re.compile(r"\bgh\s+pr\s+create\b", re.I)  # the command's text, in any case; a command without it is never gated
PUNCT = ";()<>|&\n`"  # characters shlex splits at in gated(); a run of them is one operator token
REDIR = {"<", ">", ">>", "<<", "<<-", "<<<", ">&", "<&", "&>", "&>>", ">|", "<>"}  # redirects: skipped with their target word
# splits a run of operator characters: `;>` is `;` then `>`
OPS = re.compile(r"&>>|<<<|;;&|&&|\|\||\|&|;;|;&|>>|<<|>&|<&|&>|>\||<>|.", re.S)
DYN = re.compile(r"[$*?[{]").search  # a character a shell may expand into other words
# a git option that runs a command: -c, -O (also bundled: -nOcmd), --open-files-in-pager, a `!` alias
GIT_EXEC = re.compile(r"-(c|[^-]*O)|--op|!").match
# <<WORD or <<-WORD: one plain or fully quoted word; a backslash in it is left unmatched (the shell removes it)
HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*(?:'([^']*)'|\"([^\"\\]*)\"|([^\s;&|<>()'\"\\]+))(?=[\s;&|<>()]|$)")
COMMENT = re.compile(r"(?<![^ \t])(?<!\\[ \t])#")  # a `#` that starts a word: after a blank, and not an escaped one
SUBST = re.compile(r"\$\(([^()]*)\)")  # an innermost $(...)
KEYWORD = {"if", "then", "else", "elif", "fi", "while", "until", "do", "done", "!", "{", "}"}  # may precede a command word
ASSIGN = re.compile(r"[A-Za-z_]\w*=")  # a leading NAME=value word
INERT = re.compile(r"(?:GIT_(?:AUTHOR|COMMITTER)_(?:NAME|EMAIL|DATE)|LANG|LC_\w+|TZ|NO_COLOR)=").match  # no tool runs these
SAFE = {"echo", "printf", "cat", "grep", "egrep", "fgrep", "rg", "head", "tail", "wc", "cut", "tr", "diff", "ls", "cd",
        "test", "[", "true", "false", "date", "jq", "column", "fold", "nl", "git", "gh"}  # text tools: none runs its arguments
GIT_READ = {"log", "show", "diff", "grep", "status", "blame", "commit", "add"}  # read or record only: the rest may run or write
ASSIGN_EXP = re.compile(r"\$\{[^}]*=").search  # `${NAME:=value}` expands and assigns NAME, which may be an exported EDITOR


def ts(v):
    s = str(v)
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def gh_json(*a, timeout=60):
    r = subprocess.run([os.environ.get("PERUN_GH", "gh"), *a], capture_output=True, text=True, timeout=timeout)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "gh failed")
    return json.loads(r.stdout or "[]")


def ready(pr):
    ch = pr.get("statusCheckRollup") or []
    return (not pr.get("isDraft") and bool(ch)
            and all((c.get("conclusion") or c.get("state") or "").upper() in OK for c in ch))


def open_ready(timeout=60):
    return sum(ready(p) for p in gh_json("pr", "list", "--state", "open", "--limit", "100", "--json", "isDraft,statusCheckRollup",
                                         timeout=timeout))


def _holds(text):
    """True when `text` holds `gh pr create`, also read the way a shell would: backslash-newline joined, quotes and backslashes
    removed."""
    joined = text.replace("\\\n", "")
    return any(MENTION.search(t) for t in (text, joined, re.sub(r"[\"'\\]", "", joined)))


def _tokens(text):
    """`text` split into shell words: quotes removed, each run of operator characters one token, `#` not a comment.
    Raises ValueError on a quote that does not close."""
    lx = shlex.shlex(text, posix=True, punctuation_chars=PUNCT)
    lx.whitespace, lx.whitespace_split, lx.commenters = " \t\r", True, ""
    return list(lx)


def _code(pre):
    """True when text placed right after `pre` is provably shell code: not inside a quote, a comment, `$'..'`, `${..}`, `$[..]`,
    `((..))` or backticks. The only open quote it accepts is the `"$(` that wraps most heredoc commit messages."""
    if any(x in pre for x in ("$'", "${", "$[", "((")) or pre.count("`") % 2:
        return False
    while True:
        try:
            return not any(t.startswith("#") for t in _tokens(pre))
        except ValueError:  # an open quote: accept only a `"$(` and test the text before it
            pre, sep, tail = pre.rpartition('"$(')
            if not sep or re.search(r"[\"'`()#\\]", tail):
                return False


def _cmd_fails(s):
    """True when the words `s` of one command are not known to be text-only (step 7 of `gated`)."""
    while s and (s[0] in KEYWORD or ASSIGN.match(s[0])):
        # any variable but an inert one may be an editor, a pager, a config entry or an external diff that a tool runs
        if s[0] not in KEYWORD and not INERT(s[0]):
            return True
        s = s[1:]
    if not s:
        return False
    cmd, args = s[0], s[1:]
    if cmd not in SAFE:  # exactly a listed name: `./echo` and `/bin/echo` are other programs
        return True
    opt = any(a[:1] == "-" and ("$" in a or "{" in a) for a in args)  # an option an expansion may build (`-n${o}cmd`, `--op{e,}n`)
    if cmd == "printf":  # `printf -v NAME` assigns a variable, which a tool may then run (an exported EDITOR)
        return bool(args) and (args[0][:1] == "-" or any(c in args[0] for c in "${`"))
    # `create` or its alias `new` may follow `pr` after any flags, or be spelled by an expansion (`create$x`, `pr$x`); alias,
    # config and extension store a command; api may open a pull request
    if cmd == "gh":
        return (any(a in ("alias", "config", "extension", "api") for a in args) or any(DYN(a) for a in args[:2])
                or any(a == "pr" and any(b in ("create", "new") or DYN(b) for b in args[i + 1:]) for i, a in enumerate(args)))
    if cmd == "git":
        sub = list(args)
        while sub[:1] == ["-C"]:  # `-C DIR` may come before the subcommand; any other option there leaves it unknown
            del sub[:2]
        # an expansion may build an option (`$o` for `--output=gc`): only the message after `commit -m` (or `-am`) may expand
        msg = sub[:1] == ["commit"]
        xp = any(("$" in a or "{" in a) and not (msg and re.fullmatch(r"-[a-z]*m", p)) for p, a in zip(["", *args], args))
        # only a read or record subcommand: another may run a command, or write the config that another then runs
        return xp or any(GIT_EXEC(a) or a.startswith("--output") for a in args) or not (sub and sub[0] in GIT_READ)
    return cmd == "rg" and (opt or any(a.startswith(("--pre", "--hostname")) for a in args))


def _subst_fails(word):
    """True when a `$(...)` or backtick body inside `word` fails like a command, or cannot be told apart (step 6 of `gated`)."""
    rest = SUBST.sub("", word)
    if "$(" in rest or rest.count("`") % 2:  # nesting, or a lone backtick
        return True
    return any(_fails(b) for b in SUBST.findall(word) + rest.split("`")[1::2])


def _fails(text):
    """True when some command in `text` is not known to be text-only, a file is written, or `text` cannot be split (steps 4-8 of
    `gated`)."""
    # ANSI-C quoting (shlex and the shell may disagree on where a quote ends); an expansion that assigns a variable a tool may run
    if "$'" in text or ASSIGN_EXP(text):
        return True
    try:
        toks = _tokens(text)
    except ValueError:
        return True
    # finished commands, the command being read, the pending redirect operator, a file is written
    segs, seg, op, wr = [], [], "", False
    for t in toks:
        if t and not t.strip(PUNCT):
            if "`" in t:  # an unquoted backtick runs its body, and its output may run as a command: keep it
                return True
            for o in OPS.findall(t):  # a run such as `;>` or `\n>` is several operators: each redirects or ends the command
                op = o if o in REDIR else ""
                if not op:
                    segs.append(seg)
                    seg = []
        elif ("$(" in t or "`" in t) and _subst_fails(t):
            return True
        elif op:
            wr = wr or (">" in op and t != "/dev/null" and not (op == ">&" and not t.strip("0123456789-")))
            op = ""
        else:
            seg.append(t)
    return wr or any(_cmd_fails(s) for s in segs + [seg])


def gated(cmd, strip=True):
    """True when the Bash command `cmd` is held at the stop-starting cap: it holds the text `gh pr create` (any case) and is not
    known to be text-only. Fail closed: a step that drops text before parsing keeps it when the input is ambiguous (keep = deny).
    The text counts wherever it sits, in code, in a comment or in a heredoc body. In order:
      1. without the text -> False; the text is also looked for with quotes and backslashes removed and backslash-newline joined,
         so a quoted, escaped or continued form reaches the parser;
      2. line by line: a newline after an odd run of backslashes is joined, except after a line holding a `#` that follows a blank
         (bash ends a comment at the newline); a `#` that follows a blank and is provably a comment (`_code`) drops the rest of the
         line;
      3. heredoc bodies (`<<WORD`, `<<-WORD`, quoted or not, never `<<<`) and their delimiter lines are dropped when the `<<` is
         provably shell code (`_code`) and the delimiter is one plain or fully quoted word without a backslash (the shell removes
         it); a heredoc with no delimiter line -> True, and so is a body holding `$(` or a backtick under an unquoted delimiter
         (the shell expands it), an operator line that opens a `(`, a backtick or a quote after the marker (the shell reads it
         across the body lines, so the body starts later), and a `)` in the body or on the operator line after a `(` (it may close
         a `$(` before the delimiter line in older shells). Any other `<<` keeps its body in place, where it is read as commands.
         A heredoc found beside a comment dropped in step 2 (a `#` outside every body; a `#` in a body is data) is not stripped:
         the command is read again with `strip=False`, every body in place, so each body line and its delimiter line must pass as
         commands;
      4. text holding `$'` -> True (ANSI-C quoting: shlex and a shell may disagree where the quote ends), and so is an expansion
         that assigns (`${NAME:=..}`: a tool may run the variable as an editor or a pager). The rest is split with shlex
         (`_tokens`): `;`, `&&`, `|`, `&`, parentheses, backticks, redirections and newlines separate commands, `#` is not a
         comment; a quote that does not close -> True;
      5. a run of operator characters is split into operators (`;>` is `;` then `>`). A redirect operator (`<`, `>`, `>>`, `<<`,
         `<<<`, `>&`, `<&`, `&>`, `&>>`, `>|`, `<>`) and its target word are skipped; any other operator (`;`, `(`, `&&`) ends the
         command, so the word after it is a command word. An output redirect to anything but /dev/null or a file descriptor is a
         file write;
      6. every `$(...)` and backtick body inside a quoted word must pass 4-8 itself; a nested `$(` or a lone backtick -> True, and
         so is an unquoted backtick (it runs its body, and its output may run as the command);
      7. a command passes when, after shell keywords and leading `NAME=value` words, it is empty or its first word is exactly a
         name in SAFE (text tools that run none of their arguments; `./echo` and `/bin/echo` are other programs). An assignment
         passes only for an inert name (INERT: GIT_AUTHOR_*, GIT_COMMITTER_*, LANG, LC_*, TZ, NO_COLOR); any other variable, bare
         or before a command, fails: an editor, a pager, a config entry or an external diff may run it. Still failing: `gh` with
         an `alias`, `config`, `extension` or `api` word, a `$`, `*`, `?`, `[` or `{` in its first two words, or a `pr` followed,
         at any position (flags may come between), by `create`, its alias `new` or a word that holds such a character; `git` with
         a word that starts `-c`, `--op`, `--output` or `!`, is a short-option bundle holding `O` (`-nOcmd`: a pager that runs a
         command) or holds `$` or `{` (an expansion may build an option: `git log $o` for `--output=gc`; only the word after
         `commit -m` or `-am` may expand), or a subcommand outside GIT_READ (after any `-C DIR`): `rebase --exec`, `bisect run`,
         `submodule foreach`, `apply`, `-p`, `--config-env` and the rest fail, in every `git` segment, because one may write a
         config that a later git runs, even from a segment without the text; `printf` whose first word is an option (`printf -v
         NAME` assigns a variable that a tool may run) or holds `$`, `{` or a backtick; `rg` with a word starting `--pre` or
         `--hostname`, or an option holding `$` or `{`. Not in SAFE: sed, awk, find, xargs, sort, tee, uniq (it writes its second
         argument), env, timeout, nice, sudo, exec, command, time, nohup, eval, source, `.`, watch, ssh, shells and interpreters;
      8. any output redirect to a file (the whole command holds the text, also when only a comment or a heredoc body does), or any
         failing command -> True.
    Passing though it may run the command: `$(which gh) pr create`, `${GH} pr create`, `gh${IFS}pr create`, `gh $'pr' create`,
    `gh pr cre{a,}te` (no `gh pr create` text), a script written first by an editor tool, or by a command without the text, and
    run later, a `gh` alias or extension that is already installed (it runs under its own name), another allowed tool's own exec
    flag that is not listed. `$GH pr create` holds the text, and `$GH` is not in SAFE.
    Denied though it only names it: a `#` or `<<` that cannot be proven to be a comment or a heredoc, a comment beside a heredoc,
    a backtick, `$'`, a non-read git subcommand beside the text (`git push && echo ...`), also when the text is only in a comment,
    a file written beside the text, also when the text is only in a heredoc body (`cat > notes.md <<'EOF'`), an assignment of a
    variable that is not inert, `printf -v`, `${x:=..}`, a `$` or `{` in a git word (`git log "$base"..HEAD`, `-C "$dir"`), a `)`
    in a heredoc body inside `$(`, a `(` after a heredoc marker, a `{owner}`-style word in `gh`, an expansion or the word `create`
    or `new` after `gh pr`, `gh api`, a path as the command word (`/bin/echo`), a pipeline through a command outside SAFE. Pure: no
    I/O."""
    if not _holds(cmd):
        return False
    lines, kept, hd, cmt, i = cmd.split("\n"), [], False, False, 0
    while i < len(lines):
        line, i = lines[i], i + 1
        # an odd run of backslashes ends the line: a continuation
        while (len(line) - len(line.rstrip("\\"))) % 2 and i < len(lines):
            if COMMENT.search(line):  # bash ends a comment at the newline, so this may be no continuation: keep the newline
                line = line[:-1]
                break
            line, i = line[:-1] + lines[i], i + 1
        for m in COMMENT.finditer(line):  # the first `#` that provably starts a comment ends the line
            if _code("\n".join(kept + [line[:m.start()]])):
                line, cmt = line[:m.start()], True
                break
        kept.append(line)
        for m in HEREDOC.finditer(line) if strip else ():
            pre = "\n".join(kept[:-1] + [line[:m.start()]])
            if not _code(pre):
                continue  # may sit in a quote or a comment: not a heredoc, its body stays and is read as commands
            dash, sq, dq, bare = m.groups()
            word = sq or dq or bare
            end = next((j for j in range(i, len(lines)) if (lines[j].lstrip("\t") if dash else lines[j]) == word), None)
            body, rest = lines[i:end], line[m.end():]
            # no delimiter line; an expanded body; an operator line that opens a `(`, a backtick or a quote the shell may close
            # on a later line (so the body starts later); or a `)` after a `(` that may close a `$(` before the delimiter line
            # (older shells)
            if (end is None or (not (sq or dq) and any("$(" in b or "`" in b for b in body)) or "(" in rest or not _code(rest)
                    or ("(" in pre and ")" in "".join(body + [rest]))):
                return True
            hd, i = True, end + 1
    # a heredoc beside a comment: read it again with every body in place, as commands
    return gated(cmd, False) if hd and cmt else _fails("\n".join(kept))


def hook():
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if data.get("tool_name", "Bash") != "Bash" or not gated(cmd) or "# priority:" in cmd:
            return 0
        n, cap = open_ready(10), int(os.environ.get("PERUN_STOP_STARTING_READY", "5"))
    except subprocess.TimeoutExpired:
        print("flow_alarm: gh timed out (10s); stop-starting check skipped this call", file=sys.stderr)
        return 0
    except Exception:
        return 0
    if n >= cap:
        print(f"Blocked `gh pr create`: {n} ready-but-unmerged PRs (cap {cap}). Waiting work is queue; help it land "
              "(review, merge, unblock) before starting more. Priority work: add `# priority: <reason>` to the command.",
              file=sys.stderr)
        return 2
    return 0


def symptom(argv, now):
    hrs = float(argv[argv.index("--hours") + 1]) if "--hours" in argv else 2.0
    try:
        n = open_ready()
        last = gh_json("pr", "list", "--state", "merged", "--limit", "1", "--json", "mergedAt")
        red = ts(argv[argv.index("--red-since") + 1]) if "--red-since" in argv else None
    except (RuntimeError, OSError, ValueError, IndexError, subprocess.TimeoutExpired) as e:
        print(f"flow_alarm: could not read the queue: {e}", file=sys.stderr)
        return 2
    age = (now - ts(last[0]["mergedAt"])) / 3600 if last else float("inf")
    bad = 0
    if n and age > hrs:
        print(f"ALARM flow: {n} ready PR(s) and nothing merged in {'ever' if age == float('inf') else f'{age:.1f}h'}")
        bad = 1
    if red is not None and now - red > 3600:
        print(f"ALARM flow: trunk red for {(now - red) / 3600:.1f}h")
        bad = 1
    return bad


def split(path):
    try:
        rows = json.load(open(path))
        names = (("waiting-to-start", "queuedAt", "startedAt"), ("coding", "startedAt", "readyAt"),
                 ("ready-to-merged", "readyAt", "mergedAt"))
        med = {n: [] for n, _, _ in names}
        for r in rows:
            if all(r.get(k) for k in ("queuedAt", "startedAt", "readyAt", "mergedAt")):
                for n, a, b in names:
                    med[n].append((ts(r[b]) - ts(r[a])) / 3600)
        if not med["coding"]:
            raise ValueError("no row has all four timestamps")
    except (OSError, ValueError, TypeError, AttributeError) as e:
        print(f"flow_alarm: {e}", file=sys.stderr)
        return 2
    m = {n: statistics.median(v) for n, v in med.items()}
    for n, v in m.items():
        print(f"{n}\tmedian_h={v:.1f}")
    print(f"largest\t{max(m, key=m.get)}\trows={len(med['coding'])}")
    return 0


def main(argv):
    now = float(argv[argv.index("--now") + 1]) if "--now" in argv else time.time()
    if not argv or argv[0] == "--now":
        return hook()
    if argv[0] == "symptom":
        return symptom(argv, now)
    if argv[0] == "split" and len(argv) >= 2:
        return split(argv[1])
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
