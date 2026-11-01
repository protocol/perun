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

Queue read: the hook counts the ready PRs on the newest 100 open ones (one `gh pr list --limit 100`). When that read holds 100 PRs and its
ready count is under the cap, older ready PRs may lie outside it, so the hook reads once more with `--limit 500` (the same fields, no
files; with PERUN_STOP_STARTING_LANES set it also asks `files` and `changedFiles`, see the per-lane cap), with what is left of the 15 s
budget below as its timeout, skipped when under 2 s is left. A successful second read gives the list and the count for the deny, the
throughput judgement and the denial record's `ready`; the per-lane path is entered on the wide count and, with lanes set, recounts on that
list, with no third list call. A failed or slow second read keeps the first read's list and count and prints `flow_alarm: queue read past
100 PRs failed; counted on the newest 100` to stderr: the same verdict as the first read alone (it fails open), at most the rest of the
budget later. Under 100 PRs, or at the cap already, there is no second read. The second read shares the 15 s budget with the per-lane
compare, so local git calls can start up to 15 s into the 20 s hook timeout (a 5 s margin). `symptom` counts on a `--limit 500` read.
Residual: a repo with more than 500 open PRs is counted on the newest 500.

Throughput exemption, only where the hook would deny (at the cap): one lone `gh pr create` passes when the pushed branch's diff against
`origin/<base>` holds only throughput paths, by name, and fewer than PERUN_THROUGHPUT_OPEN (default 2) exempt PRs are open, so test and CI
work is not stuck behind the queue it would shorten. Judged only when the command's words (`_tokens`, a backslash-newline joined) start
`gh pr create` (or `new`) and hold no operator (`;`, `&&`, `|`, `&`, `(`, newline, backtick, redirect, heredoc), no word with a `$`, `*`,
`?`, `[`, `{` or backtick (the shell may expand it into other words: a glob into a file named `--base=release`, a brace word into later
options; quotes are not seen, so a quoted title holding one keeps the deny too: put the text in `--body-file`), no word starting `#`, no
`-R`, `-H`, `--repo` or `--head`, and no bundle or joined value (a dash, a letter, more: `-dB`, `-Brelease`). Base: the last `--base V`,
`--base=V` or `-B V`, else origin/HEAD (a `gh-merge-base` branch config with any non-empty value keeps the deny). Files: `git diff
--name-only origin/<base>...HEAD` in the hook's `cwd` (else the process's), renames off, `diff.relative` off, submodules shown. HEAD must be
the one commit `refs/remotes/origin/<branch>` points at, with no other remote ref there, so the ledger name is the PR's head name. `git
remote` must list no name but `origin`, and every value of `remote.origin.gh-resolved` (what `gh repo set-default` writes) must be `base`,
or none set: gh opens the PR on its own base repo (it prefers a remote named `upstream`), so the diff against origin/<base> may not be the
PR's diff. Names and config values are compared whole, split only at a newline (a NUL for config): git allows U+0085, U+2028 and Unicode
spaces in a name, so `origin` plus one of them is another remote or ref. Paths:
PERUN_THROUGHPUT_PATHS (comma-separated fnmatch globs) replaces the default, THROUGHPUT (test dirs and files, CI config, test-runner
config); a glob without `/` matches the file name, one with `/` the path or any tail of it. The deny stands (class `work`) for anything
not judged, an empty diff, a path outside the list, a git call that fails or takes over 5 s, and any exception while judging (only reading
the queue fails open). A grant appends {"branch","at"} to `<git-common-dir>/perun-throughput.jsonl`; exempt PRs open = ledger branches
among the open PRs' head names, from the same `gh` call that counts the ready ones. A deny appends {"at","class","ready","cap"} to
`<git-common-dir>/perun-flow-denials.jsonl`: class `throughput-cap` when only the exempt cap blocked a judged branch, else `work`; no file
names or command text; a write error is ignored. Residuals: globs match names, not contents (a CI-config edit passes whatever it changes;
`spec/`, `*.spec.*` and `test_*.py` can name product files: narrow the list with PERUN_THROUGHPUT_PATHS); creation only (later pushes are
not re-judged); the ledger is local (another host's grants are not seen); two sessions can race for the last slot; a GH_REPO exported in
the shell is not seen; an exempt PR can fall outside the list when the first read is already at the cap (it is not read again) or the
repo holds over 500 open PRs, so grants can exceed the cap.

Per-lane cap, opt-in: with PERUN_STOP_STARTING_LANES unset or blank nothing below applies and the denial record keeps its four keys. Where
PRs ride separate merge trains, a full train would deny new work for an idle one, so `web=web/*,docs/*;api=` (lanes split by `;`, each
`name=glob,glob`) applies the cap per lane. Globs are fnmatch patterns matched against the whole repo-relative path (`*` also crosses `/`; no
tail matching, unlike PERUN_THROUGHPUT_PATHS). A PR's lane is the first lane, in the order written, with a glob that matches any of its
changed files; a lane with no globs (`api=`) is the fallback for a PR that matched no other lane (at most one). Blank entries and spaces
around names and globs are ignored; anything else malformed (no `=`, an empty or repeated name, a second fallback, no lane at all) is a parse
error. Only where the global count already denies, and before the throughput judgement (which still reads the local diff), the hook
recounts per lane. The new PR's files are the ones GitHub lists for it: `gh api repos/{owner}/{repo}/compare/<base>...<branch>?per_page=1`
run in the command's directory, the `filename` of each entry, base the `--base` value else the default branch `refs/remotes/origin/HEAD`
names, both URL-quoted. The local diff is not used: it reads the local `origin/<base>`, and when the branch holds base commits that ref
lacks it lists more files than the PR has, which can put the PR in a lane with room while its real lane is full. The other PRs' files come
from `gh pr list --state open --limit 500 --json isDraft,statusCheckRollup,headRefName,files,changedFiles`: the second queue read when made
(it asks for these fields with this variable set), else a call of its own; its count is used only when its own ready total is at least
PERUN_STOP_STARTING_READY (it must confirm the read that put the queue at the cap). A lane with fewer ready PRs than that passes (exit 0, no
ledger entry, no denial record); otherwise the throughput judgement and the deny go on as above, so a test-only branch of a full lane still
gets its grant. A ready PR counts in a lane when it is in it or its lane is unknown; an unknown PR counts in every lane: its
`files` list is missing, or shorter than `changedFiles` (GitHub returns at most 100), or `changedFiles` is missing or null, or its files
match no lane and there is no fallback. The command is judged (`_judged`, the git reads) once per hook call: the throughput judgement reuses
the result. Every failure of the recount keeps the deny (what fails open is unchanged: the hook input, the first queue read, the cap value):
a parse error, a command or branch not judged (an empty local diff too), a compare list that is empty or holds 300 files (GitHub lists at
most 300), files that match no lane, a failed or slow call, a recount whose ready total is under the cap, 500 PRs back (the list may be
cut), any other exception. The compare and the recount's own list call (made only when the second queue read did not list the files) each
get what is left of a 15 s budget counted from the start of the hook (the templates set a 20 s hook timeout, and a hook the harness kills
lets the command run) and are skipped when under 2 s is left; the compare's share is read after its base lookup, which a slow git may
have used up, and the second queue read above draws on the same budget. With the variable set
the denial record adds "lane" (the new PR's lane, null when unknown) and "lane_ready" (that lane's count, null when not counted), and the
message adds `Lane <name>: <k> ready (cap <cap> per lane).` when both are known. Residuals: a renamed file counts by its new path only, as
GitHub lists it on both sides; local git calls are not budgeted (5 s timeout each), so a slow git can still run the hook past its timeout,
with or without lanes.

Ready = open, not draft, at least one check and every check SUCCESS/NEUTRAL/SKIPPED. `PERUN_GH` overrides the gh binary (tests).
`--now EPOCH` pins the clock. Side effects: the stop-starting hook appends to the two files above, the ledger on a grant and the denial
log on a deny; everything else is read-only.
"""
import fnmatch
import json
import os
import re
import shlex
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone
from urllib.parse import quote

sys.dont_write_bytecode = True  # never litter __pycache__ into a checksummed skill tree
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

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
# fnmatch globs of the paths whose PRs shorten the queue: test dirs and files, CI config, test-runner config (a project adds its own)
THROUGHPUT = ("test/*,tests/*,__tests__/*,e2e/*,spec/*,*.test.*,*.spec.*,*_test.*,test_*.py,conftest.py,.github/workflows/*,"
              ".gitlab-ci.yml,.circleci/*,.buildkite/*,playwright.config.*,jest.config.*,vitest.config.*,pytest.ini")
# a word the hook will not judge: one that sends the PR elsewhere (`-R`, `-H`, `--repo*`, `--head*`), a short-option bundle or joined value
# (`-dB`, `-Brelease`), a comment start (the shell drops the rest of the line), or an expansion (DYN's characters and a backtick): `$(..)`
# runs before gh, even in quotes, a brace word (`{--base=main,}`) becomes later words and a glob (`--*`) may become a file named
# `--base=release`, none of them seen by the hook. Quotes are not seen either, so a quoted word holding one of them is not judged.
UNJUDGED = re.compile(r"^(?:-[RH]\Z|--(?:repo|head)|-[A-Za-z]\S|#)|[$*?[{`]").search


def ts(v):
    s = str(v)
    if re.fullmatch(r"\d+(\.\d+)?", s):
        return float(s)
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).timestamp()


def gh_json(*a, timeout=60, cwd=None):
    r = subprocess.run([os.environ.get("PERUN_GH", "gh"), *a], capture_output=True, text=True, timeout=timeout, cwd=cwd)
    if r.returncode:
        raise RuntimeError(r.stderr.strip() or "gh failed")
    return json.loads(r.stdout or "[]")


def ready(pr):
    """Not a draft, with at least one check, every one passed. The train's own progress marker is not a check (`landing_watchdog._stage`,
    the rule `green` uses): `merge_train.py stage` posts it pending on each PR it queued, so counting it would hide the very queue counted here."""
    from landing_watchdog import _stage  # lazy: only a gated `gh pr create` and `symptom` reach here
    ch = [c for c in pr.get("statusCheckRollup") or [] if not _stage(c)]
    return (not pr.get("isDraft") and bool(ch)
            and all((c.get("conclusion") or c.get("state") or "").upper() in OK for c in ch))


def open_prs(timeout=60, lanes=False, wide=False):
    """The open PRs, one `gh` call: `ready` counts them and the throughput ledger reads their head names (`headRefName`). The newest 100 by
    default, the hook's first read; when it holds 100 PRs and its ready count is under the cap, the hook reads again with `wide` (up to
    500, the same fields), so ready PRs beyond the first 100 are counted too. `lanes`: up to 500 as well, with their changed files
    (`files`, at most 100 each, and `changedFiles`, the true count) for the per-lane recount; with PERUN_STOP_STARTING_LANES set the hook's
    second read asks for both (`wide` and `lanes`) and the recount takes that list. A repo with more than 500 open PRs is counted on the
    newest 500."""
    return gh_json("pr", "list", "--state", "open", "--limit", "500" if lanes or wide else "100", "--json",
                   "isDraft,statusCheckRollup,headRefName" + (",files,changedFiles" if lanes else ""), timeout=timeout)


def open_ready(timeout=60):
    """How many open PRs are ready (the count `symptom` reports), on a read of up to 500: not a hook, so its 60 s timeout stands. The read
    has no fallback: a failed read or the timeout raises, and `symptom` exits 2 (fail closed, as documented)."""
    return sum(map(ready, open_prs(timeout, wide=True)))


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


def _git(cwd, *a):
    """stdout of `git a...` run in `cwd` (None: the process's); raises on a non-zero exit and after 5 s."""
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True, timeout=5, check=True).stdout


def _entries(cwd, *a, sep="\n"):
    """The entries of `git a...` stdout, each ended by `sep`, split there and nowhere else: str.split() and str.splitlines() also break at
    Unicode spaces and at U+0085, U+2028 and U+2029, which git allows in a ref or remote name, so a name could read as two or as another."""
    return _git(cwd, *a).split(sep)[:-1]


def _values(cwd, key):
    """Every value of the git config `key`, exact, in order; [] when it is unset (git exits 1). `-z` ends each value with a NUL, so a value
    may hold a newline. Raises on any other failure, so the caller keeps the deny. (`--default` does not combine with `--get-all`.)"""
    try:
        return _entries(cwd, "config", "-z", "--get-all", key, sep="\0")
    except subprocess.CalledProcessError as e:
        if e.returncode != 1:
            raise
        return []


def _common(cwd):
    """The repo's common git dir (shared by its worktrees), where the throughput ledger and the denial log live."""
    return os.path.join(cwd or ".", _git(cwd, "rev-parse", "--git-common-dir").rstrip("\n"))


def _base(toks):
    """The PR base: the value of the last `--base V`, `--base=V` or `-B V` (the flag parser keeps the last), else None. An option with
    no word after it gives "": the diff against `origin/` then fails and the deny stands."""
    base = None
    for i, t in enumerate(toks):
        if t in ("--base", "-B"):
            base = "".join(toks[i + 1:i + 2])
        elif t.startswith("--base="):
            base = t[7:]
    return base


def _open_cap():
    """PERUN_THROUGHPUT_OPEN (default 2) as an int: how many exempt PRs may be open. Raises ValueError when it is not a number."""
    return int(os.environ.get("PERUN_THROUGHPUT_OPEN", "2"))


def _is_throughput(path, globs):
    """True when `path` matches a glob: one without `/` is matched against the file name, one with `/` against the path or any tail
    of it (`tests/*` matches `src/tests/a.py`, `test_*.py` matches `a/test_b.py` but not `test_dir/b.py`)."""
    parts = path.split("/")
    return any(fnmatch.fnmatchcase(c, g) for g in globs
               for c in (["/".join(parts[i:]) for i in range(len(parts))] if "/" in g else parts[-1:]))


def _judged(cmd, cwd):
    """(branch, changed files, base) of the PR a gated `gh pr create` opens, for the throughput exemption and the lane recount (`base`: the
    `--base` value, None when the command has none): None unless `cmd` is one lone invocation (see the module docstring) of a branch
    pushed to origin as itself, whose diff against its base is not empty. Raises on a git failure or timeout: the caller keeps the deny."""
    toks = _tokens(cmd.replace("\\\n", ""))  # a backslash-newline continues the line: the shell joins it
    # one lone `gh pr create`: another word first, an operator, or a word that sends the PR elsewhere or may expand is not judged
    if (toks[:3] not in (["gh", "pr", "create"], ["gh", "pr", "new"]) or any(t and not t.strip(PUNCT) for t in toks)
            or any(map(UNJUDGED, toks))):
        return None
    # gh opens the PR on its own base repo, which the diff against origin/<base> read only if origin is it: another remote (gh prefers
    # `upstream`) or a `gh repo set-default` that names another repo is not judged
    if _entries(cwd, "remote") not in ([], ["origin"]) or set(_values(cwd, "remote.origin.gh-resolved")) - {"base"}:
        return None
    branch = _git(cwd, "symbolic-ref", "--short", "HEAD").rstrip("\n")
    base = _base(toks)
    # without --base gh reads the branch's `gh-merge-base` config, else the default branch
    if base is None and any(_values(cwd, f"branch.{branch}.gh-merge-base")):
        return None
    ref = "origin/HEAD" if base is None else f"origin/{base}"
    # diff.relative off: a user's setting would list only paths under cwd; --no-renames: a product file moved into tests/ lists both
    # paths; --ignore-submodules=none: a pointer bump counts; `--` ends the revisions (a file may not stand in for one)
    out = _git(cwd, "-c", "diff.relative=false", "diff", "--name-only", "-z", "--no-renames", "--ignore-submodules=none",
               f"{ref}...HEAD", "--")
    files = [f for f in out.split("\0") if f]
    # gh opens the PR from origin/<branch>: it must be the one remote ref at HEAD (a branch not pushed, a copy behind or ahead, or a
    # second remote at the same commit is not judged), so the ledger name is the PR's head name
    if not files or _entries(cwd, "for-each-ref", "--format=%(refname)", "--points-at", "HEAD", "refs/remotes/") != [f"refs/remotes/origin/{branch}"]:
        return None
    return branch, files, base


def _throughput(cmd, cwd, prs, now, judged=False):
    """Judge a gated `gh pr create` at the cap: "" when it is one lone invocation (see the module docstring) of a branch pushed to
    origin whose diff against its base holds only throughput paths and fewer than PERUN_THROUGHPUT_OPEN exempt PRs are open (the grant
    is appended to the ledger), else the denial class: `throughput-cap` (judged throughput-only, exempt cap reached) or `work` (not
    judged, or not throughput-only). `judged`: `_judged(cmd, cwd)` when the caller already ran it (None: not judged), so the git reads
    run once per hook call; False judges here. Raises on a git failure or timeout, an unreadable ledger or a bad env value: the caller
    keeps the deny."""
    if judged is False:
        judged = _judged(cmd, cwd)
    if judged is None:
        return "work"
    branch, files, _ = judged
    globs = [g.strip() for g in os.environ.get("PERUN_THROUGHPUT_PATHS", THROUGHPUT).split(",") if g.strip()]
    if not all(_is_throughput(f, globs) for f in files):
        return "work"
    ledger = os.path.join(_common(cwd), "perun-throughput.jsonl")
    try:
        with open(ledger) as f:
            seen = {json.loads(line)["branch"] for line in f}
    except FileNotFoundError:
        seen = set()
    if len(seen & {p.get("headRefName") for p in prs}) >= _open_cap():
        return "throughput-cap"
    # ponytail: read, then append, without a lock: two sessions racing can both take the last slot (flock the ledger if it matters)
    with open(ledger, "a") as f:
        f.write(json.dumps({"branch": branch, "at": int(now)}) + "\n")
    return ""


def _lanes(spec):
    """PERUN_STOP_STARTING_LANES as {lane name: globs}, in the order written; the lane with no globs is the fallback. Raises ValueError
    when it is malformed: an entry with no `=`, an empty or repeated name, a second fallback, no lane at all (blank entries are skipped)."""
    lanes = {}
    for entry in filter(None, (e.strip() for e in spec.split(";"))):
        name, eq, globs = entry.partition("=")
        name = name.strip()
        if not eq or not name or name in lanes:
            raise ValueError(f"malformed lane `{entry}`")
        lanes[name] = [g.strip() for g in globs.split(",") if g.strip()]
    if not lanes or sum(not g for g in lanes.values()) > 1:
        raise ValueError("no lane, or a second fallback lane")
    return lanes


def _lane_of(files, lanes):
    """The lane of a PR that changes `files`: the first lane, in order, with a glob that matches the whole path of one of them (`*` also
    crosses `/`), else the fallback lane (the one with no globs), else None."""
    hit = next((n for n, gs in lanes.items() if any(fnmatch.fnmatchcase(f, g) for f in files for g in gs)), None)
    return hit or next((n for n, gs in lanes.items() if not gs), None)


def _counts(pr, lane, lanes):
    """True when a ready PR counts toward `lane`: it is in it, or its lane is unknown, so it counts in every lane (`files` missing, or
    `changedFiles` missing or null, or `files` shorter than `changedFiles` because GitHub lists at most 100; or its files match no lane
    and there is no fallback)."""
    files, total = pr.get("files"), pr.get("changedFiles")
    return files is None or total is None or len(files) < total or _lane_of([f["path"] for f in files], lanes) in (lane, None)


def _compare(cwd, judged, t0):
    """The files GitHub lists for the PR `judged` (a `_judged` result) describes, as the new PR's own lane files: `gh api
    repos/{owner}/{repo}/compare/<base>...<branch>` run in `cwd`, base the `--base` value, else the default branch that
    `refs/remotes/origin/HEAD` names. The local diff is not used: it reads the local `origin/<base>` and lists more than the PR when the
    branch holds base commits that ref lacks. The call gets what is left of the budget (`_left(t0)`) after that lookup, which a slow git
    may have used up, and is skipped (None) when under 2 s is left. None too when the list is empty or holds 300 (GitHub lists at most
    300: it may be cut). Raises on a failed or slow call, an unexpected reply or a git failure."""
    branch, _, base = judged
    if base is None:
        base = _git(cwd, "symbolic-ref", "refs/remotes/origin/HEAD").rstrip("\n").removeprefix("refs/remotes/origin/")
    left = _left(t0)
    if left < 2:
        return None
    reply = gh_json("api", f"repos/{{owner}}/{{repo}}/compare/{quote(base)}...{quote(branch)}?per_page=1", timeout=left, cwd=cwd)
    names = [f["filename"] for f in reply.get("files") or []]
    return names if 0 < len(names) < 300 else None


def _left(t0):
    """Seconds left of the hook's 15 s budget for its optional `gh` calls, counted from `t0`, the hook's start: the second queue read
    (`open_prs` with `wide`) and the per-lane compare and recount. The templates set a 20 s hook timeout, and a hook the harness kills
    lets the command run."""
    return 15 - (time.monotonic() - t0)


def _lane_ready(cwd, spec, cap, t0, judged, listed=None):
    """(lane, k) for the per-lane cap (see the module docstring): the lane of the PR `judged` (a `_judged` result, None: not judged)
    describes, from GitHub's compare, and the ready open PRs in it, counted only when the recount's own ready total is at least `cap`,
    so that it confirms the read that put the queue at the cap; None for what could not be told. `listed`: the open PRs, with their
    files, that the hook's second queue read already listed (None: list them here), so no list call is made. Never raises: every
    failure, a timeout included, leaves the deny standing. The compare and a list call of its own each get what is left of the budget
    (`_left`) and are skipped when under 2 s is left; the compare reads it itself after its base lookup."""
    lane = k = None
    try:
        lanes, left = _lanes(spec), _left(t0)
        if judged and left >= 2:
            names = _compare(cwd, judged, t0)
            lane = _lane_of(names, lanes) if names else None
        left = _left(t0)
        if lane and (listed is not None or left >= 2):
            prs = open_prs(left, lanes=True) if listed is None else listed
            # ponytail: one page, and at the limit the list may be cut: page it if a repo holds that many open PRs
            if len(prs) < 500 and sum(map(ready, prs)) >= cap:
                k = sum(ready(p) and _counts(p, lane, lanes) for p in prs)
    except Exception:  # every failure keeps the deny
        pass
    return lane, k


def hook(now=None):
    """PreToolUse(Bash) stop-starting check. Exit 2 (reason on stderr) for a gated `gh pr create` at the cap unless it is throughput
    work or, with PERUN_STOP_STARTING_LANES set, its lane has room; 0 otherwise, and on a failed or slow `gh` or unparseable input. A
    first read of 100 PRs under the cap is read again, up to 500 (module docstring, "Queue read"). Side effects: the ledger append on a
    grant, the denial-log append on a deny. `now` (epoch) stamps both; default the clock."""
    t0 = time.monotonic()
    try:
        data = json.load(sys.stdin)
        cmd = (data.get("tool_input") or {}).get("command") or ""
        if data.get("tool_name", "Bash") != "Bash" or not gated(cmd) or "# priority:" in cmd:
            return 0
        prs, cap = open_prs(10), int(os.environ.get("PERUN_STOP_STARTING_READY", "5"))
        n = sum(map(ready, prs))
    except subprocess.TimeoutExpired:
        print("flow_alarm: gh timed out (10s); stop-starting check skipped this call", file=sys.stderr)
        return 0
    except Exception:
        return 0
    spec, listed = os.environ.get("PERUN_STOP_STARTING_LANES", "").strip(), None
    if len(prs) >= 100 and n < cap and (left := _left(t0)) >= 2:  # a full first page may hide ready PRs behind it: read up to 500
        try:  # replaces list and count together; with lanes the read also lists the files, and the per-lane recount takes that list
            wide = open_prs(left, lanes=bool(spec), wide=True)
            prs, n, listed = wide, sum(map(ready, wide)), wide if spec else None
        except Exception:  # any failure or timeout keeps the first read's list and count (its verdict), and says so
            print("flow_alarm: queue read past 100 PRs failed; counted on the newest 100", file=sys.stderr)
    if n < cap:
        return 0
    now, cwd = time.time() if now is None else now, data.get("cwd") or None
    lane, k, judged = None, None, False
    if spec:  # opt-in: the cap per lane, recounted before the throughput judgement; a lane with room touches no ledger or log
        try:  # judged here, once: the throughput judgement reuses it, and a raise is class `work` there too
            judged = _judged(cmd, cwd)
        except Exception:
            judged = None
        lane, k = _lane_ready(cwd, spec, cap, t0, judged, listed)
        if k is not None and k < cap:
            return 0
    try:
        why = _throughput(cmd, cwd, prs, now, judged)
    except Exception:  # an unread diff or ledger proves nothing: the deny stands (only reading the queue fails open)
        why = "work"
    if not why:
        return 0
    try:  # best effort: no file names or command text, and a log that cannot be written never changes the verdict
        rec = {"at": int(now), "class": why, "ready": n, "cap": cap, **({"lane": lane, "lane_ready": k} if spec else {})}
        with open(os.path.join(_common(cwd), "perun-flow-denials.jsonl"), "a") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
    try:
        hint = ("Queue-throughput work (only test or CI paths changed) passes as a lone `gh pr create` (body in `--body-file`) of a "
                f"branch already pushed to origin, while fewer than {_open_cap()} such PRs are open. ")
    except ValueError:  # a cap that is not a number: say nothing about it
        hint = ""
    where = f"Lane `{lane}`: {k} ready (cap {cap} per lane). " if lane and k is not None else ""
    print(f"Blocked `gh pr create`: {n} ready-but-unmerged PRs (cap {cap}). {where}Waiting work is queue; help it land "
          f"(review, merge, unblock) before starting more. {hint}Priority work: add `# priority: <reason>` to the command.",
          file=sys.stderr)
    return 2


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
        return hook(now)
    if argv[0] == "symptom":
        return symptom(argv, now)
    if argv[0] == "split" and len(argv) >= 2:
        return split(argv[1])
    print(__doc__.split("\n\n")[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
