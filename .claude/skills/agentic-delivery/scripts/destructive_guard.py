#!/usr/bin/env python3
"""PreToolUse(Bash) hook: deny a destructive host command before it runs. Never executes the command.

BEST-EFFORT and STRING-LEVEL: it catches common honest mistakes and common wrappers. It is NOT a security
boundary. The OS sandbox (`sandbox.enabled`, set by `install.sh --apply-operating-layer`) is the boundary:
operating-discipline item 8 (`references/operating-discipline.md`, "Safety rules": never run a delete or kill
on a host, never `rm -rf` a variable-built path). Known-uncovered: interpreter APIs (`subprocess`, `exec`,
`system` on built strings), IFS and brace-expansion tricks, variables holding a command, aliases, scripts,
`g=git; $g ...` and exotic wrappers.

Parsing (pure stdlib, text only): backslash-newline joined, heredoc bodies and here-strings set aside, shlex
tokens, split into segments on newline, `;`, `&&`, `||`, `|`, parens. Redirections (`>f`, `2>/dev/null`, `<x`)
do not split a command and are skipped when finding argv0. Per segment: leading VAR=val, shell keywords
(`{ } if then else elif fi while until do done !`) and wrappers (`env sudo doas command nohup time nice timeout
setsid stdbuf ionice chronic caffeinate flock exec builtin busybox xargs`) are skipped, consuming option values
only for the flags that really take one (`sudo -u/-g/-C/-D/-h/-p/-r/-t/-U`, `env -u/-C/-S`, ...); `env -S STR`,
`flock -c STR`, `eval STR`, `su -c STR` and `bash|sh|zsh|dash|ash|ksh|fish` with a flag bundle containing `c`
(`-c`, `-lc`) recurse into STR. argv0 becomes its basename (`/bin/rm` -> `rm`). Every `$(...)` and backtick
body is scanned recursively. Quoted text is one token, so `grep "rm -rf" docs/` is not a hit. Text fed to a
shell or interpreter (`echo|printf ... | sh`, `<<<`, heredoc) is scanned as a command or interpreter body.
A pipeline whose LAST command is a shell/interpreter with no script argument (`| sh`, `| (bash)`, `| python3 -`)
is denied outright when an earlier stage is echo/printf/cat/tee/`base64 -d` or a heredoc, as is `bash <(...)`,
`source <(...)` and `source|bash /dev/stdin` (the relayed text cannot be vetted).

Denies (exit 2, one-line reason with the safe alternative on stderr; the host blocks the call):
- `rm -r` (also `--rec*`) on a `$VAR`/backtick path, any glob or brace list/range, `.`, `..`, `/`, `//`, `~`,
  `$HOME`, any `..` target, an absolute path within 2 components of `/` or under `/Users/*`, `/home/*`, `/usr`,
  `/etc`, `/var`, `/opt` at any depth (after normalizing), or (under `xargs`, incl. custom `-I/-J/-i/--replace`
  placeholders, carried into nested `sh -c` bodies) a placeholder or no explicit target;
- `git reset --hard`, `git clean -f*` (not with -n), `git push` force/delete/mirror/`+ref`/`:ref`/glob refspec
  (not `--force-with-lease`), `git checkout|switch -f|--discard-changes`, `git checkout|restore` of the whole
  tree (`.`, `./`, `*`, `:/`, `:(top)`; not `restore --staged` only), `git branch -D`, `git stash clear|drop`:
  judged by command text only, so denied even on a clean tree; global options with values and unique-prefix
  long options (`--ha`, `--mir`, `--forc`) are normalized first;
- `find ... -delete`, `-exec|-execdir|-ok rm|shred`, or an exec'd command (`sh -c ...`) that is itself denied;
- `dd of=/dev/*` (not null|zero|stdout|stderr), `mkfs*`, `chmod|chown -R` on root/home/near-root paths;
- `curl|wget ... | sh|bash|...|python|perl|ruby|node|php`, `sh|bash|source|. <(curl ...)`, `eval` or a shell
  fed by curl/wget;
- `pkill`, `killall`, `kill` with a substituted/pattern argument;
- `python -c`, `perl -e`, `node -e`, `awk` bodies that delete (`rmtree`, `os.remove`, `unlink`, `rm_rf`, ...)
  anything but a literal relative path, contain `rm -r` on a variable/root, or call `system()` on a
  non-literal command.
- `${IFS}`/brace-expanded and variable-built command words with `-rf`/`--hard`, `ssh host CMD` (CMD is checked),
  `docker volume rm|prune`, `docker system prune --volumes|-a`, `docker rm|rmi|kill $(...)` (global options like `-H x` are skipped), `kill ... -1|0`, `shutdown|reboot|halt|poweroff`, `shred`, `truncate -s 0`,
  `rsync --delete` (not with `-n`/`--dry-run`), SQL DROP/TRUNCATE/DELETE-all via psql/mysql/sqlite3, fork bombs,
  `git push --force-with-lease` to main/master, `git worktree remove --force`, a secret variable in a curl/wget
  URL query, `aws s3 rm --recursive|s3 rb --force|ec2 terminate-instances|rds delete-db-*`, `gcloud projects delete`,
  `az group delete`, `terraform|tofu destroy|apply -destroy`, `kubectl delete namespace|all --all`,
  `redis-cli FLUSHALL|FLUSHDB`, mongo `dropDatabase`, `wipefs` (not `-n`), `diskutil eraseDisk|eraseVolume|...`,
  and `eval`/`sh` of a `$(... base64 -d|xxd -r|printf hex-escape ...)` payload; also package `unpublish|yank|purge`, any
  `aws <svc> delete-*|terminate-*|purge-*`, `gcloud ... delete`, `gsutil rm -r`, `az ... delete|purge`, `kubectl delete --all|drain`,
  `docker|podman|nerdctl exec|run IMG CMD` and `kubectl exec -- CMD` (CMD is checked), `>>`/`tee` onto a system file, `gh <noun> delete`, `curl -X DELETE`,
  `helm uninstall`, `pulumi destroy`, `terraform state rm`, `parted mklabel`, `cqlsh` DROP, `git filter-branch`, `> /etc/...`, an
  alias to a destructive command and one-step `x=rm; $x -rf` indirection. Allowed: `--help`/`-help`, `--dry-run`/`--dryrun`
  (not `=none`; aws/kubectl/helm only), and `rm`/`find -delete` inside a named child of `$TMPDIR` or `/tmp`. A `--help` after
  other arguments of rm/chmod/chown/dd/shred/mkfs/diskutil (only a lone one is usage) still gets the full check.
  Residuals: a `/tmp/<name>` symlink to elsewhere, or an unset `$TMPDIR` (`$TMPDIR/x` becomes `/x`), is trusted; `> file` over
  a system path is caught but `cp`/`mv` onto one are out of scope; `pip uninstall` is blocked only for xargs or `-r`.
Everything else is allowed.

No in-repo grant or allow list: anything an agent can write, an agent can forge. When the owner really wants a
denied command, the owner runs it themselves with the `!` prefix in Claude Code (the block message says so).

Never crashes. Unparseable stdin, a non-string command, a shlex failure or any internal error falls back to
a regex scan of the raw text for the same destructive classes: block on a hit, otherwise allow (a guard that
errors closed would wedge every session; one that errors open on a hit would be trivial to evade).
Side effects: none. `--selftest` runs assertions.
"""
import json
import os
import posixpath
import re
import shlex
import sys

KW = ("{", "}", "if", "then", "else", "elif", "fi", "while", "until", "do", "done", "!", "coproc")
# wrapper -> short flags that take a value (only these consume the next token)
VAL = {"env": "uCS", "sudo": "ugCDhprtU", "doas": "uC", "nice": "n", "timeout": "sk", "xargs": "adEILnPsIJSR",
       "stdbuf": "ioe", "ionice": "cnpPu", "time": "fo", "exec": "a", "caffeinate": "tw", "flock": "wEc",
       "command": "", "builtin": "", "watch": "n", "nohup": "", "setsid": "", "chronic": "", "busybox": ""}
LONGVAL = ("--user", "--group", "--chdir", "--host", "--prompt", "--role", "--type", "--other-user", "--unset",
           "--split-string", "--signal", "--kill-after", "--arg-file", "--delimiter", "--max-args",
           "--max-procs", "--max-lines", "--max-chars", "--interval")
SHELLS = ("bash", "sh", "zsh", "dash", "ash", "ksh", "fish")
AWK = ("awk", "gawk", "mawk", "nawk")
INTERP = re.compile(r"^(python[\d.]*|perl|ruby|node|nodejs|bun|deno|php|lua)$")
EVALFLAG = re.compile(r"-[A-Za-z]*[ceErp][A-Za-z]*")
SAFE_DEV = ("/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr")
GIT_OPT_VAL = ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env")
LIT = r"""['"][^'"/$@][^'"$@]*['"]"""  # a literal relative path
DELAPI = re.compile(r"(rmtree|os\.(?:remove|unlink|rmdir|removedirs)|rmSync|rmdirSync|unlinkSync|\bfs\.rm|rm_rf"
                    r"|File\.delete|\bunlink|\brmdir)(?:\(|\s)(?!\s*(?:" + LIT + r"\s*(?:[,);]|$)|(?:tempfile\.)?mkdtemp\(\s*\)\s*[,);]))")
BODYRM = re.compile(r"\brm\s+-\w*[rR]\w*\s*(?:\S*[$/~*]|['\"]\s*\+|%s|\{)")  # variable/root path or string concatenation
PRINTCALL = re.compile(r"""\b(?:print|puts|echo|console\.(?:log|error)|sys\.std(?:out|err)\.write)\s*\(((?:[^()'"]|'[^']*'|"[^"]*")*)\)""")
SQLCLI = ("psql", "mysql", "mariadb", "sqlite3", "mongosh", "sqlcmd", "cqlsh")
SQLCOMMENT = re.compile(r"/\*.*?\*/", re.S)
SQLDROP = re.compile(r"\b(?:drop\s+(?:database|schema|keyspace|table)|truncate\s+\w|delete\s+from\s+\w+\s*(?:;|$))", re.I)
DYNCMD = re.compile(r"(?:^|[;&|\n({]|\bthen\b|\bdo\b)\s*\"?(?:\$\([^()]{0,200}\)|`[^`]{0,200}`|\$\{?\w{1,64}\}?)\"?(?:\s+\S+){0,8}?\s+(?:-\w*(?:rf|fr)\w*|--hard)\b")
FORKBOMB = re.compile(r"(\S{1,32})\(\)\s*\{\s*\1\s*\|\s*\1\s*&")
SSH_VAL = "bcDEeFIiJLlmOopQRSWw"
# eval/shell fed a substitution that decodes base64, hex (`xxd -r`) or printf escapes; scanned in bounded windows after at most 64
# shell words and 8 substitutions each (more than that alongside a decoder fails closed), so the cost is linear in the input, never quadratic
DECSTART = re.compile(r"\b(?:eval|source|(?:ba|z|da|k|a)?sh)\b")
SUBST = re.compile(r"\$\(|`")
DECODE = re.compile(r"\bbase64\b.{0,300}(?:\s-\w*[dD]|--decode)|\bxxd\b.{0,100}\s-\w*r|\bprintf\b.{0,300}\\(?:x[0-9a-fA-F]|[0-7]{3})|\bopenssl\s+enc\b.{0,100}\s-(?:d\b|base64\b|a\b)"
                    r"|\bpython[\d.]*\b.{0,200}(?:b64decode|b32decode|decodebytes|a2b_base64|unhexlify|fromhex)", re.S)
DRY = ("--dry-run", "--dryrun", "--dry-run=client", "--dry-run=server")  # `--dry-run=none` really runs, so it is not listed
SCOPED = re.compile(r"(?:\$TMPDIR|\$\{TMPDIR\}|/tmp)/\w[^/$`{}]*(?:/[^$`{}]*)?")  # under the temp dir, inside a named child
SYSFILE = re.compile(r"/(?:etc|boot|bin|sbin|lib|lib64|usr|System|Library|root|private/etc|(?:private/)?var(?=/(?!tmp(?:/|$)|folders(?:/|$)))|(?:private/)?var$)(?:/|$)", re.I)
KUBE_VAL = ("-n", "--namespace", "-l", "--selector", "-f", "--filename", "--context", "--cluster", "--kubeconfig", "--user", "-o", "--output", "--field-selector")
DISKUTIL = ("erasedisk", "erasevolume", "secureerase", "zerodisk", "randomdisk", "partitiondisk")
CTR_VAL = ("--name", "--network", "--net", "--entrypoint", "--env", "--volume", "--workdir", "--user", "--publish", "--label",
           "--hostname", "--memory", "--mount", "--cpus", "--env-file", "--restart", "--platform", "--cap-add", "--cap-drop", "--device",
           "--add-host", "--dns", "--pid", "--ipc", "--group-add", "--tmpfs", "--shm-size", "--log-driver", "--security-opt", "--ulimit")
KUBE_LONG = ("--namespace", "--container", "--context", "--cluster", "--kubeconfig", "--user", "--filename", "--pod-running-timeout", "--server", "--token")
DOCKER_VAL = ("-H", "--host", "--context", "-c", "--config", "-l", "--log-level", "--tlscacert", "--tlscert", "--tlskey")
HEREDOC = re.compile(r"<<-?[ \t]*(['\"]?)([A-Za-z_]\w*)\1[^\n]*\n(.*?)\n[ \t]*\2[ \t]*(?=\n|$)", re.S)
MAXDEPTH = 6
PROBE_PID = re.compile(r"\d+|\$\w+|\$\{\w+\}|\$\([^()]*\)")
FALLBACK = [re.compile(p) for p in (
    r"\brm\s+(?:-\S+\s+)*-\w*[rR]\w*\s+(?:\S*[$`*~{]|/|\.\.?(?:\s|$))",
    r"\bgit\b.*\b(?:reset\s+--ha|clean\s+-\w*f|checkout\s+(?:-f|--\s+\.|\.)|switch\s+-f|restore\s+\.|branch\s+-D|stash\s+(?:clear|drop))",
    r"\bgit\b.*\bpush\b.*(?:--for|\s-\w*f\w*\b|--del|--mir|\s[+:]\S)",
    r"\bfind\b.*(?:-delete|-exec\s+rm)", r"\bdd\b.*\bof=/dev/(?!null|zero|std)", r"\bmkfs",
    r"\b(?:terraform|tofu)\b.*\bdestroy\b", r"\bkubectl\b.*\bdelete\s+(?:ns|namespaces?)\b",
    r"\baws\b.*\b(?:terminate-instances|delete-db-|s3\s+rb)", r"\b(?:wipefs|redis-cli\s.*flush(?:all|db))\b",
    r"\b(?:chmod|chown)\s+(?:-\S+\s+)*-\w*R\w*\s+(?:\S+\s+)?[/~]", r"\b(?:pkill|killall)\b",
    r"(?i)\b(?:rd|rmdir|del|erase)\s+(?:/\w\s+)*/s\b", r"(?i)\bremove-item\b.*\s-r(?:e(?:c(?:u(?:r(?:s(?:e)?)?)?)?)?)?\b", r"(?i)\b(?:format-volume|clear-disk|diskpart)\b", r"(?i)\bformat(?:\.com)?\s+[a-z]:", r"(?i)\breg\s+(?:delete|import|restore)\b",
    r"\bkill\s+(?!(?:-0|-s\s+0)(?:\s+--)?\s+(?:\d+|\"?\$\{?\w+\}?\"?|\"\$\([^\"()]*\)\")\s*(?:[;&|\n]|$)).*[$`]", r"\b(?:curl|wget)\b.*\|\s*(?:sudo\s+)?(?:ba|z|da|k|fi)?sh\b",
)]


BUNDLE = re.compile(r"-[A-Za-z]+")
PUNCT = re.compile(r"[;&|()<>\n]+")
B64D = re.compile(r"-[A-Za-z]*[dD][A-Za-z]*|--decode")


def _bundle(t, ch):
    return ch in t and bool(BUNDLE.fullmatch(t))


def _sysw(t, app=False):
    """A write target on a system path (case-insensitive for macOS; 2+ leading `..` count as suspect; `/var/log` is exempt for appends)."""
    parts = t.split("/")
    v = next((i for i, x in enumerate(parts) if "$" in x or "`" in x or x.startswith("~")), None)
    if v is not None:  # an unexpanded base followed by `..` may land anywhere: judge what remains after the `..` run
        up, st = 0, []
        for x in parts[v + 1:]:
            if x == "..":
                up, _ = (up, st.pop()) if st else (up + 1, 0)
            elif x not in ("", "."):
                st.append(x)
        if not up:
            return False
        t = "/" + "/".join(st)
    p = posixpath.normpath(re.sub("/+", "/", t) or ".")
    if p.startswith("../.."):
        p = re.sub(r"^(?:\.\./)+", "/", p + "/")
    return bool(SYSFILE.match(p)) and not (app and re.match(r"/(?:private/)?var/log(?:/|$)", p, re.I))


def _mkfs_dry(name, a):
    """`mkfs.ext* -n` / `mkfs.xfs -N` as a flag, not as the value of an option that takes one (`-L -n`)."""
    flag, val = ("-n", "bdeEgGiIjJlLmMNoOrtTUC") if name.startswith("mkfs.ext") else ("-N", "bdilmnrsLp") if name == "mkfs.xfs" else (None, "")
    i = 0
    while i < len(a):
        if a[i] == flag:
            return True
        i += 2 if len(a[i]) == 2 and a[i][0] == "-" and a[i][1] in val else 1
    return False


SQLSH = re.compile(r"(?:^|\n)[ \t]*\.(?:shell|system|sh)[ \t]+([^\n]+)|(?:^|\n)[ \t]*\.(?:read|import|once|output)\b[^\n|]*?['\"]?\|[ \t]*([^\n]+)", re.I)
SQLATT = re.compile(r"\battach\b(?:[ \t]+database)?[ \t]*(.+?)[ \t\n]+as\b", re.I | re.S)
SQLOPEN = re.compile(r"(?:^|\n)[ \t]*\.(?:open|save|backup|output|once|import|read)[ \t]+(?:--?\w+[ \t]+)*['\"]?([^\s'\"|]+)", re.I)


def _unq(c):
    """One shell word's worth of text, quotes removed (`'rm -rf /'` -> `rm -rf /`)."""
    try:
        w = shlex.split(c)
    except ValueError:
        return c
    return w[0] if len(w) == 1 else c


def _sqlite(texts, depth):
    """sqlite3 dot-commands run shell (`.shell|.system|.sh CMD`, `.read|.import|.once|.output |CMD`: CMD is checked); ATTACH/`.open`/`.output`
    of a system path (also parenthesised, concatenated or `file:`) is refused."""
    for t in texts:
        for m in SQLSH.finditer(t):
            r = check(_unq((m[1] or m[2]).strip()), depth + 1)
            if r:
                return r
        cands = [m[1] for m in SQLOPEN.finditer(t)]
        for m in SQLATT.finditer(t[:20000]):
            e = re.sub(r"""['"][ \t]*\|\|[ \t]*['"]""", "", m[1])
            cands += re.split(r"""[\s'"()]+""", e)
        for c in cands:
            c = re.sub(r"^file:(?://)?", "", c).split("?")[0]
            if c and _sysw(c):
                return "sqlite3 ATTACH/.open/.output on a system path. Use a copy and ask the owner"
    return ""


WINABS = re.compile(r"[A-Za-z]:|\\\\|%\w+%|\$env:", re.I)


def _wintarget(t):
    """A Windows recursive-delete target that is not a plain relative project path (drive, UNC, variable, glob, `.`, `..`, root)."""
    u = t.replace("\\", "/")
    n = posixpath.normpath(u or ".")
    if re.fullmatch(r"(?:\$env:(?:TEMP|TMP)|%(?:TEMP|TMP)%)[\\/][\w.-]+(?:[\\/][^$%]*)?", t, re.I) and ".." not in n.split("/"):
        return False  # a named child of the temp dir
    glob = re.search(r"[*?]", u) and "/" in n and not re.search(r"[*?]", n.rsplit("/", 1)[0])  # glob only in the last part of a named relative dir
    return bool(WINABS.match(t)) or bool(re.search(r"[$%]", u)) or (bool(re.search(r"[*?]", u)) and not glob) or n in (".", "..") or n.startswith(("/", "../", "~"))


def _wildsys(t):
    """`del` target that wipes a system dir: drive/%SystemRoot%/bare `Windows` + `*` or `*.*` (shlex ate the backslashes); `*.ext` is scoped."""
    return bool(re.match(r"(?i)(?:[A-Za-z]:[\\/]*|[\\/]*)(?:windows|users|program|system32|boot|recovery)|(?:%|\$env:)(?:systemroot|windir|systemdrive|programfiles\w*)%?", t)
                and re.search(r"[*?]+(?:\.[*?]+)?$", t))


def _win(name, a, depth):
    """Windows shells: powershell/pwsh -Command and cmd /c recurse; Remove-Item -Recurse, del/rd /s, format X:, Format-Volume are refused."""
    n = name.lower()
    n = n[:-4] if n.endswith(".exe") else n
    if n in ("powershell", "pwsh"):
        for j, t in enumerate(a):
            tl = t.lower()
            if tl in ("-e", "-ec") or tl.startswith("-enc"):
                return "powershell -EncodedCommand cannot be vetted. Decode it, read it, then run it"
            if tl in ("-command", "-c") or tl == "/c":
                rest = a[j + 1:]
                return check(rest[0] if len(rest) == 1 else " ".join(shlex.quote(x) for x in rest), depth + 1) if rest else ""
    if n == "cmd":
        for j, t in enumerate(a):
            if t.lower() in ("/c", "/k"):
                rest = a[j + 1:]
                return check(rest[0] if len(rest) == 1 else " ".join(shlex.quote(x) for x in rest), depth + 1) if rest else ""
    tg = [t for t in a if not t.startswith("-") and not re.fullmatch(r"/[A-Za-z]", t)]
    rec = any(t.lower().startswith("-r") and "-recurse".startswith(t.lower()) for t in a)  # -r, -rec, -Recurse (also `del -Recurse`)
    if n in ("remove-item", "ri", "rm", "del", "erase", "rd", "rmdir") and rec and not any(t.lower().startswith("-wh") and "-whatif".startswith(t.lower()) for t in a) \
            and (n in ("remove-item", "ri", "del", "erase") or any(re.fullmatch(r"[A-Za-z]:[\\/]?.*", t) for t in tg)) and any(_wintarget(t) for t in tg):
        return "Remove-Item -Recurse on a drive, variable, glob or system path. Delete an exact in-project path"
    if n in ("remove-item", "ri") and not tg and rec and not any(t.lower().startswith("-wh") and "-whatif".startswith(t.lower()) for t in a):
        return "Remove-Item -Recurse fed from a pipeline cannot be vetted. Delete an exact in-project path"
    if n in ("del", "erase", "rd", "rmdir") and (any(t.lower() == "/s" for t in a) or any(re.fullmatch(r"[A-Za-z]:[\\/]*[*?.]*", t) or _wildsys(t) for t in tg)) and any(_wintarget(t) for t in tg):
        return f"{name} /s on a drive, variable, glob or system path. Delete an exact in-project path"
    if n in ("format", "format.com") and any(re.match(r"[A-Za-z]:(?:[\\/]|\s|$)", t) for t in a) or n == "diskpart":
        return f"{name} wipes a volume or disk. Do it in a VM, never on the host"
    if n == "bcdedit" and any(t.lower() in ("/delete", "/deletevalue", "/set") for t in a):
        return "bcdedit changes boot configuration. Ask the owner"
    if n == "reg" and a[:1] and a[0].lower() in ("delete", "import", "restore"):
        return "reg delete/import/restore changes the registry. Ask the owner"
    if n == "wmic" and ("delete" in map(str.lower, a) or {"call", "format"} <= set(map(str.lower, a))):
        return "wmic delete removes system objects. Ask the owner"
    if (n == "format" and any(re.fullmatch(r"[A-Za-z]:", t) for t in a)) or n in ("format-volume", "clear-disk", "remove-partition", "initialize-disk"):
        return f"{name} wipes a volume or disk. Do it in a VM, never on the host"
    return ""


def _inner(cmd, depth):
    """Check a container/pod command; past MAXDEPTH it is refused (fail closed)."""
    if depth + 1 > MAXDEPTH:
        return "container/pod command nested too deep to vet. Run one step at a time"
    return check(" ".join(shlex.quote(x) for x in cmd), depth + 1)


def _ctr(a, depth, sv, lv):
    """`a` = tokens after exec/run. Image/pod is the first positional; unknown `--opt` may or may not take a value, so every
    positional within (unknown options + 1) is a candidate image and what follows it a command. `--entrypoint X` heads the command."""
    pos, unk, ep, i = [], 0, None, 0
    while i < len(a):
        t = a[i]
        if t == "--":
            pos += range(i + 1, len(a))
            break
        if t.startswith("--"):
            n = t.split("=")[0]
            if n == "--entrypoint":
                ep = t.split("=", 1)[1] if "=" in t else (a[i + 1] if i + 1 < len(a) else "")
                i += 1 if "=" in t else 2
                continue
            if "=" in t:
                i += 1
            elif n in lv:
                i += 2
            else:
                unk += 1
                i += 1
        elif t.startswith("-") and t != "-":
            i += 2 if len(t) == 2 and t[1] in sv else 1
        else:
            pos.append(i)
            i += 1
    if unk > 16:
        return "container command behind too many unrecognised options cannot be vetted. Spell the options out"
    for m in pos[:unk + 1]:
        cmd = ([ep] if ep else []) + a[m + 1:]
        r = _inner(cmd, depth) if cmd else ""
        if r:
            return r
    return ""


def _far(t):
    """Root, home, `..` escapes or an absolute path within 2 components of `/`, after normalizing."""
    if t.startswith(("~", "$HOME", "${HOME")):
        return True
    if "$" in t or "`" in t:
        return False
    p = posixpath.normpath(re.sub("/+", "/", t)) if t else ""
    return p in ("/", "..") or p.startswith("../..") or (p.startswith("/") and p.count("/") <= 2)


def _scoped(t):
    """A path inside a named child of `$TMPDIR` or `/tmp` (no `..`, no variable below it): scratch space, not a host path."""
    return bool(SCOPED.fullmatch(t)) and ".." not in t.split("/")


def _tree(t):
    """A git pathspec naming the whole work tree (or its parent)."""
    if t in ("*", ":/", ":(top)", ":(top)*"):
        return True
    return not t.startswith(":") and "$" not in t and bool(t) and posixpath.normpath(re.sub("/+", "/", t)) in (".", "..")


def _rm(args, ph):
    rec, tg = False, []
    for i, t in enumerate(args):
        if t == "--":
            tg += args[i + 1:]
            break
        if (t.startswith("--") and len(t) >= 5 and "--recursive".startswith(t.split("=")[0])) \
                or _bundle(t, "r") or _bundle(t, "R"):
            rec = True
        elif not t.startswith("-"):
            tg.append(t)
    if not rec:
        return ""
    if not tg and ph:
        return "rm -r with targets from xargs. List them first (`ls`), then `rm` the exact paths"
    for t in tg:
        n = posixpath.normpath(re.sub("/+", "/", t) or ".")
        if _scoped(t) and not (ph and any(p in t for p in ph if p)):
            continue
        if re.search(r"[$`*?\[]|\{[^}]*(?:,|\.\.)", t) or (ph and any(p in t for p in ph if p)) or n == "." or _far(t) \
                or n.startswith("..") or re.match(r"/(Users|home|usr|etc|var|opt|root|srv|mnt|media|Volumes|private/etc)/", n) or (
                    re.match(r"/private/(?:etc|var|root|usr|opt|home|Users)/", n) and not re.match(r"/private/var/(?:folders|tmp)/", n)):
            return f"rm -r on `{t}` (variable, glob, placeholder, `.`, `..`, root, home or system path). Delete an exact, quoted in-project path, or use a container/VM"
    return ""


def _git(a):
    i = 0
    while i < len(a) and a[i].startswith("-"):
        m = re.match(r"alias\.[^=]+=(!?)(.*)", a[i + 1]) if a[i] == "-c" and i + 1 < len(a) else None
        if m:  # an alias definition carrying a destructive command
            r = check(m.group(2) if m.group(1) else "git " + m.group(2), 1)
            if r:
                return r
        i += 2 if a[i] in GIT_OPT_VAL else 1
    if i >= len(a):
        return ""
    sub, r = a[i], a[i + 1:]
    longs = [t.split("=")[0] for t in r if t.startswith("--") and len(t) > 2]

    def has(full):  # unique-prefix long option (>= 4 chars, e.g. --ha, --mir, --forc)
        return any(len(x) >= 4 and full.startswith(x) for x in longs)
    flags = [t for t in r if re.fullmatch(r"-[A-Za-z]+", t)]
    force = has("--force") or any("f" in t for t in flags)
    dele = has("--delete") or any("d" in t for t in flags)
    if sub in ("filter-branch", "filter-repo"):
        return "git filter-branch/filter-repo rewrites the whole history. Work on a fresh clone and ask the owner"
    if sub == "push" and has("--dry-run"):
        return ""
    if sub == "reset" and has("--hard"):
        return "git reset --hard discards work. Use `git stash` or `git reset --soft`/`--mixed`"
    if sub == "clean" and (force or any(x.startswith("--f") for x in longs)) and not (has("--dry-run") or any("n" in t for t in flags)):
        return "git clean -f deletes untracked files. Preview with `git clean -n`, delete exact paths"
    leased = [t.split("=", 1)[1].split(":")[0] for t in r if t.startswith("--force-with-lease=")]
    if sub == "push" and has("--force-with-lease") and any(re.search(r"(?:^|[:/])(?:main|master)$", t) for t in leased + [t for t in r if not t.startswith("-")]):
        return "force push to main/master rewrites shared history. Ask the owner first"
    if sub == "worktree" and "remove" in r and force:
        return "git worktree remove --force deletes uncommitted work. Check `git -C <path> status` and remove without --force"
    if sub == "push" and (force or dele or has("--mirror") or any(
            not t.startswith("-") and (t.startswith(("+", ":")) or ":+" in t or "*" in t) for t in r)):
        return "force/delete/mirror push rewrites shared history. Use `--force-with-lease` after the owner approves"
    if sub in ("checkout", "switch") and (force or has("--discard-changes")):
        return "git checkout/switch -f discards uncommitted changes. Use `git stash` or name the exact file"
    if sub in ("checkout", "restore") and any(_tree(t) for t in r if not t.startswith("-")) \
            and not (sub == "restore" and (has("--staged") or any("S" in t for t in flags))
                     and not (has("--worktree") or any("W" in t for t in flags))):
        return "whole-tree git checkout/restore discards uncommitted changes. Use `git stash` or name the exact file"
    if sub == "branch" and (any(_bundle(t, "D") for t in r) or (force and dele)):
        return "git branch -D deletes an unmerged branch. Use `git branch -d` (refuses if unmerged)"
    if (sub == "reflog" and "expire" in r and any(re.fullmatch(r"--expire(?:-unreachable)?=(?:now|all|0|-?\d+\.?\w*)", t) for t in r)) \
            or (sub == "gc" and any(t in ("--prune=now", "--prune=all") for t in r)) or (sub == "prune" and "now" in r):
        return "git reflog expire/gc --prune=now makes lost commits unrecoverable. Ask the owner"
    if sub == "stash" and any(t in ("clear", "drop") for t in r):
        return "git stash clear/drop loses stashed work. Use `git stash list`/`apply` and keep it"
    return ""


def _body(t):
    """Interpreter/awk one-liner or fed text: deletes a non-literal path, or system() on a non-literal command."""
    t = PRINTCALL.sub(" ", t)  # print("...") of plain literals runs nothing; calls nested inside stay visible
    if DELAPI.search(t) or BODYRM.search(t):
        return "interpreter one-liner deleting a variable/root path. Delete an exact literal in-project path"
    calls = re.findall(r"\bsystem\s*\(", t)
    lits = re.findall(r"""\bsystem\s*\(\s*(?:"([^"]*)"|'([^']*)')\s*\)""", t)
    if len(calls) > len(lits):
        return "system() on a non-literal command. Run an exact literal command"
    for d, s in lits:
        r = check(d or s, 1)
        if r:
            return r
    return ""


def _cmd(name, a, ph, depth=0):
    strict = name in ("rm", "chmod", "chown", "dd", "shred", "diskutil") or name.startswith("mkfs")  # a lone --help only
    if (a in (["--help"], ["-help"]) or (not strict and any(t in ("--help", "-help") for t in a))) \
            and not (name in SHELLS + AWK + ("ssh", "eval", "su", "git") or INTERP.match(name)):
        return ""  # prints usage and exits
    r = _win(name, a, depth)
    if r:
        return r
    dr = [t for t in a if re.match(r"--(?:no-)?dry-?run", t)]
    if name in ("aws", "kubectl", "helm") and dr and all(t in DRY for t in dr) and dr[-1] in DRY:
        return ""  # any `--no-dry-run` or `--dry-run=none` among them means the command really runs
    if name == "rm":
        return _rm(a, ph)
    if name == "git":
        return _git(a)
    if name == "find":
        k = 0
        while k < len(a) and a[k] in ("-H", "-L", "-P"):
            k += 1
        st = []
        while k < len(a) and not a[k].startswith(("-", "(", "!")):
            st.append(a[k])
            k += 1
        sc = bool(st) and all(_scoped(x) for x in st)  # scratch space: deleting there is fine, other -exec bodies still run through check
        ext = a[k:][:1] in (["-name"], ["-iname"]) and len(a) - k == 3 and a[-1] == "-delete" \
            and re.fullmatch(r"\*\.(?:pyc|o|tmp|log|orig|class)", a[k + 1])  # sole predicate: a known build-artifact glob
        if "-delete" in a and not sc and not (ext and st and all(x in ("$TMPDIR", "${TMPDIR}", "/tmp") or not (_far(x) or ".." in x.split("/") or "$" in x or x.startswith("/")) for x in st)):
            return "find -delete. List with `find ... -print` first, then remove exact paths"
        for j, t in enumerate(a[:-1]):
            if t in ("-exec", "-execdir", "-ok"):
                k = next((m for m in range(j + 1, len(a)) if a[m] in (";", "+")), len(a))
                sub = a[j + 1:k]
                u = _unwrap(sub)[0]  # sudo/env/nice rm
                if u < len(sub) and os.path.basename(sub[u]) in ("rm", "shred") and not sc:
                    return "find -exec rm. List with `find ... -print` first, then remove exact paths"
                r = check(" ".join(shlex.quote(x) for x in sub), depth + 1)
                if r:
                    return r
    if name == "tee" and any(not t.startswith("-") and _sysw(t, any(x == "--append" or _bundle(x, "a") for x in a)) for t in a):
        return "tee writes a system file. Edit a copy and ask the owner"
    if name == "mv" and a[-1:] == ["/dev/null"]:
        return "mv to /dev/null destroys the source. Use `rm` on an exact path if you mean it"
    if name in ("curl", "wget") and any(re.fullmatch(r"-X\s*DELETE|--request[= ]DELETE|--method=DELETE", t, re.I) or (
            t.upper() == "DELETE" and k and a[k - 1] in ("-X", "--request", "--method")) for k, t in enumerate(a)):
        return "HTTP DELETE to a remote API is hard to undo. Ask the owner"
    if name == "dd" and any(t.startswith("of=") and (lambda p: p.startswith("/dev/") and p not in SAFE_DEV)(
            posixpath.normpath(re.sub("/+", "/", t[3:]) or ".")) for t in a):
        return "dd to a device. Write to a file image, or do it in a VM"
    if name.startswith("mkfs") and not _mkfs_dry(name, a):
        return "mkfs formats a device. Do it in a VM, never on the host"
    if name in ("chmod", "chown") and any(t == "--recursive" or _bundle(t, "R") for t in a) \
            and any(_far(t) for t in a if not t.startswith("-")):
        return f"{name} -R on root/home. Target an exact in-project path"
    if name in ("pkill", "killall"):
        return f"{name} kills by pattern. `kill` the exact PID you started"
    sig0 = a[1:] if a[:1] == ["-0"] else a[2:] if a[:2] == ["-s", "0"] else None  # signal 0 probes, sends nothing
    tgt = sig0[1:] if sig0 and sig0[0] == "--" else sig0
    # ponytail: exempt one non-option target only; `kill -0 $S` with S="-9 1" still word-splits into a signal
    # whitelist one PID-shaped target (digits, $VAR, ${VAR}, a quoted "$(...)"); braces, globs, an unquoted `$(`
    # (the segment ends at `(`, token "$") or a second word could expand into an option, so they stay denied
    probe = tgt is not None and len(tgt) == 1 and bool(PROBE_PID.fullmatch(tgt[0]))
    if name == "kill" and not probe \
            and any(re.search(r"[$`]|pgrep|pidof", t) for t in a):
        return "kill by pattern/substitution. `kill` the exact PID you started"
    if name in ("curl", "wget") and any(re.match(r"https?://\S*\?\S*\$\{?\w*(?:SECRET|TOKEN|PASSW|API_?KEY|PRIVATE)", t, re.I) for t in a):
        return "secret variable in a URL query string leaves the host. Send it in an Authorization header to a host you trust"
    w = [t for t in a if not t.startswith("-")]  # positional words; option values may leak in, which only widens a match
    pair = lambda *x: any(w[k:k + len(x)] == list(x) for k in range(len(w)))
    if name in ("gh", "glab") and (w[1:2] == ["delete"] or (w[:1] == ["api"] and any(
            re.fullmatch(r"(?:-X|--method)?=?DELETE", t, re.I) or (t.upper() == "DELETE" and k and a[k - 1] in ("-X", "--method"))
            for k, t in enumerate(a)))):
        return f"{name} delete is irreversible on the remote. Ask the owner"
    if name == "vault" and (w[:2] in (["kv", "destroy"], ["kv", "delete"], ["secrets", "disable"], ["auth", "disable"]) or w[:1] == ["delete"]
                            or w[:3] == ["kv", "metadata", "delete"]):
        return "vault kv destroy/metadata delete removes secret versions for good. Ask the owner"
    if name in ("dropdb", "dropuser", "pg_dropcluster") or (name == "mysqladmin" and "drop" in w):
        return f"{name} drops a database or role. Ask the owner"
    if name in ("mongo", "mongosh") and any(re.search(r"\.drop\s*\(|deleteMany\s*\(", t) for t in a):
        return "mongo drop/deleteMany removes documents or collections. Ask the owner"
    if name in ("cp", "mv", "install") and any(not t.startswith("-") and _sysw(t) for t in a[-1:] + [x for j, x in enumerate(a) if j and a[j - 1] in ("-t", "--target-directory")]):
        return f"{name} onto a system path. Edit a copy and ask the owner"
    if name == "chroot":
        k = 0
        while k < len(a) and a[k].startswith("-"):
            k += 2 if a[k] in ("--userspec", "--groups") else 1
        r = _inner(a[k + 1:], depth) if k + 1 < len(a) else ""
        if r:
            return r
    if name == "parallel":
        k = 0
        while k < len(a) and a[k].startswith("-") and a[k] != "--":
            k += 2 if a[k] in ("-j", "-n", "-N", "-a", "-S", "-L", "-P", "--jobs", "--max-args", "--arg-file", "--sshlogin") else 1
        tp = a[k + (a[k:k + 1] == ["--"]):]
        src = next((q for q, t in enumerate(tp) if t in (":::", "::::")), None)
        args, tp = (tp[src + 1:] if tp[src] == ":::" else [], tp[:src]) if src is not None else ([], tp)
        if len(tp) == 1 and re.search(r"\s", tp[0]):  # parallel 'rm -rf {}': one quoted command string
            try:
                tp = shlex.split(tp[0])
            except ValueError:
                pass
        for x in args[:16] or [None]:
            c = [x if t == "{}" else t for t in tp] + ([x] if x is not None and "{}" not in tp else []) if x is not None else tp
            r = check(" ".join(shlex.quote(t) for t in c), depth + 1, ["{}"] if x is None else None)
            if r:
                return r
    if name in ("kubectl", "oc"):  # `--overrides` JSON can carry a container command
        for t in a:
            for m in re.finditer(r'"(?:command|args)"\s*:\s*\[([^\]]*)\]', t):
                r = _inner([x.encode().decode("unicode_escape") for x in re.findall(r'"((?:[^"\\]|\\.)*)"', m[1])], depth)
                if r:
                    return r
    if name == "brew" and w[:1] in (["uninstall"], ["remove"], ["rm"]) and "--ignore-dependencies" in a:
        return "brew uninstall --ignore-dependencies breaks dependants. Ask the owner"
    if (name == "aws" and ((pair("s3", "rm") and "--recursive" in a) or (pair("s3", "rb") and "--force" in a)
                           or pair("ec2", "terminate-instances") or any(t.startswith("delete-db-") for t in w) and "rds" in w)) \
            or (name == "gcloud" and pair("projects", "delete")) or (name == "az" and pair("group", "delete")):
        return f"{name} bulk or whole-resource delete. Name the exact resource and ask the owner"
    if name in ("terraform", "tofu", "terragrunt") and (w[:1] == ["destroy"] or w[:2] == ["state", "rm"] or (
            w[:1] == ["apply"] and any(t in ("-destroy", "--destroy") for t in a)) or (name == "terragrunt" and "destroy" in w)):
        return f"{name} destroy/state rm removes real infrastructure or its record. Run `plan -destroy` and ask the owner"
    recur = any(t == "--recursive" or _bundle(t, "r") or _bundle(t, "R") for t in a)
    if (name == "aws" and len(w) > 1 and re.match(r"(?:delete|terminate|purge)-", w[1])) \
            or (name == "gcloud" and ("delete" in w or ("rm" in w and recur))) \
            or (name == "gsutil" and "rm" in w and recur) \
            or (name == "az" and any(t in ("delete", "purge") for t in w)) \
            or (name == "pulumi" and (w[:1] == ["destroy"] or w[:2] == ["stack", "rm"])) \
            or (name == "helm" and w[:1] in (["uninstall"], ["delete"], ["un"], ["del"])) \
            or (name == "kubectl" and (w[:1] == ["drain"] or ("delete" in w and any(
                t in ("--all", "--all-namespaces") or _bundle(t, "A") for t in a)))):
        return f"{name} deletes cloud/cluster resources. Name the exact resource and ask the owner"
    if (name in ("npm", "pnpm", "yarn") and "unpublish" in w) or (name in ("cargo", "gem") and "yank" in w and "--undo" not in a) \
            or (name in ("apt", "apt-get", "aptitude") and ("--allow-remove-essential" in a or (
                    ("purge" in w or "remove" in w) and any(re.search(r"[*?\[]", t) for t in w)))
                and not any(t in ("-s", "--simulate", "--just-print", "--dry-run", "--no-act") for t in a)) \
            or (name in ("pip", "pip3") and "uninstall" in w and (ph is not None or any(
                t in ("-r", "--requirement") or t.startswith("--requirement=") for t in a))):
        return f"{name} unpublish/yank/purge/bulk uninstall is hard to undo. Name the exact package and ask the owner"
    if name == "parted" and any(t in ("mklabel", "mktable", "rm") for t in w):
        return "parted rewrites a partition table. Do it in a VM, never on the host"
    if name == "alias" and any(  # `alias ls='rm -rf'`: probe the value with a dangerous target appended
            check(t.split("=", 1)[1] + " $X", 1) or check(t.split("=", 1)[1] + " /", 1) for t in a if "=" in t):
        return "alias to a destructive command. Spell the command out"
    if name == "kubectl" and "delete" in w:
        r, k = [], a.index("delete") + 1 if "delete" in a else len(a)  # first positional after delete, skipping option values (`-n foo ns bar`)
        while k < len(a) and not r:
            if a[k] in KUBE_VAL:
                k += 1
            elif not a[k].startswith("-"):
                r = [a[k]]
            k += 1
        r = r[0].split("/")[0].lower() if r else ""
        if r in ("ns", "namespace", "namespaces") or (r == "all" and ("--all" in a or "-A" in a or "--all-namespaces" in a)):
            return "kubectl delete namespace/all removes a whole workload. Delete exact named objects and ask the owner"
    if name == "redis-cli" and any(t.upper() in ("FLUSHALL", "FLUSHDB") for t in a):
        return "redis FLUSHALL/FLUSHDB wipes the keyspace. Ask the owner"
    if name in ("mongo", "mongosh") and any(re.search(r"dropDatabase\s*\(", t) for t in a):
        return "mongo dropDatabase. Ask the owner"
    if name == "wipefs" and not any(t in ("-n", "--no-act") for t in a):
        return "wipefs erases filesystem signatures on a device. Do it in a VM, never on the host"
    if name == "diskutil" and w[:1] and w[0].lower() in DISKUTIL:
        return "diskutil erase/partition wipes a disk. Do it in a VM, never on the host"
    if name == "ssh":  # the remote command is everything after the host
        k = 0
        while k < len(a) and a[k].startswith("-"):
            k += 2 if a[k][-1] in SSH_VAL and len(a[k]) == 2 else 1
        r = check(" ".join(a[k + 1:]), depth + 1) if k + 1 < len(a) else ""
        if r:
            return r
    kv = next((x for x in w if x in ("exec", "run", "debug", "rsh")), "") if name in ("kubectl", "oc") else ""
    if kv:  # the pod command is everything after `--`, else (exec, rsh) after the pod name
        r = _inner(a[a.index("--") + 1:], depth) if "--" in a else _ctr(a[a.index(kv) + 1:], depth, "ncf", KUBE_LONG) if kv in ("exec", "rsh") else ""
        if r:
            return r
    if name in ("docker", "podman", "nerdctl", "docker-compose"):  # only genuinely destructive forms: volume rm/prune, system prune --volumes/-a, bulk rm via substitution
        k = 0
        while k < len(a) and a[k].startswith("-"):
            k += 2 if a[k] in DOCKER_VAL else 1
        d = a[k:]
        if d[:1] in (["compose"], ["container"]):
            d = d[1:]
        if name == "docker-compose" or a[k:k + 1] == ["compose"]:  # compose options (-f FILE, -p NAME) precede the verb
            v = next((m for m, t in enumerate(d[:16]) if t in ("exec", "run")), None)
            d = d[v:] if v is not None else d
        if d[:1] in (["exec"], ["run"]):  # `docker run [opts] IMG CMD...`: the container command is checked
            r = _ctr(d[1:], depth, "euwvplhmac", CTR_VAL)
            if r:
                return r
        if d[:2] == ["system", "reset"] and name != "docker":
            return f"{name} system reset removes all images, containers and volumes. Ask the owner"
        # `$(` tokenizes to a bare `$`, so bulk rm shows as t == "$"
        if d[:2] in (["volume", "rm"], ["volume", "prune"]) or (d[:2] == ["system", "prune"] and any(
                t in ("--volumes", "--all") or _bundle(t, "a") for t in d)) or (
                d[:1] in (["rm"], ["rmi"], ["kill"]) and any(t == "$" or "`" in t or "$(" in t for t in d)):
            return "docker volume rm/prune, system prune --volumes/-a or bulk rm removes data. Name the exact container and ask the owner"
    if name == "kill" and a and a[-1] in ("-1", "0") and a[-2:-1] not in (["-s"], ["-n"], ["--signal"]):
        return "kill -1/0 signals every process or the whole process group. `kill` the exact PID"
    if name in ("shutdown", "reboot", "halt", "poweroff") or (name == "systemctl" and any(t in ("poweroff", "reboot", "halt") for t in a)):
        return f"{name} takes the host down. Never run it from an agent"
    tg = [t for t in a if not t.startswith("-") and t != "0"]
    if name == "shred" or (name == "truncate" and re.search(r"(?:^|\s)(?:-s\s*0|--size[= ]0)(?:\s|$)", " ".join(a))
                           and not (tg and all(not t.startswith(("/", "~", "$")) and ".." not in t.split("/") and re.search(r"\.(?:log|out|err|tmp|txt)$", t) and not re.search(r"[*?\[`$]", t) for t in tg))):
        return f"{name} irrecoverably destroys file contents. Write to a new file or ask the owner"
    if name == "rsync" and any(t.startswith("--delete") for t in a) and not any(t == "--dry-run" or _bundle(t, "n") for t in a):
        return "rsync --delete removes files at the destination. Preview with `--dry-run` and name an exact destination"
    if name == "sqlite3":
        r = _sqlite(a, depth)
        if r:
            return r
    if name in SQLCLI and not (name == "sqlite3" and ":memory:" in a and not re.search(r"attach|\.shell|\.system|\.read", " ".join(a), re.I)) and any(SQLDROP.search(SQLCOMMENT.sub(' ', t)) for t in a):
        return "SQL DROP/TRUNCATE/DELETE-all through a database client. Ask the owner"
    if name in SHELLS + ("eval",) and any(re.search(r"\b(curl|wget)\b", t) for t in a):
        return "remote script run through a shell. Download, read it, then run it"
    if INTERP.match(name):
        for j, t in enumerate(a[:-1]):
            if (EVALFLAG.fullmatch(t) or t in ("--eval", "--print")) and _body(a[j + 1]):
                return _body(a[j + 1])
    if name in AWK:
        for t in a:
            if _body(t):
                return _body(t)
    return ""


def _unwrap(seg):
    """(index of argv0, xargs placeholders or None, nested command string or None) for one segment."""
    i, ph, nested = 0, None, None
    while i < len(seg):
        b = os.path.basename(seg[i])
        if re.match(r"\w+=", seg[i]) or b in KW:
            i += 1
        elif b in VAL:
            vals = VAL[b]
            if b == "xargs":
                ph = ["{}", "%"]
            i += 1
            while i < len(seg) and seg[i].startswith("-"):
                t = seg[i]
                i += 1
                if t == "--":
                    break
                if t.startswith("--"):
                    if b == "xargs" and t.startswith("--replace"):
                        ph.append(t.split("=", 1)[1] if "=" in t else "{}")
                    elif b == "env" and t.startswith("--split-string="):
                        nested = t.split("=", 1)[1]
                    elif "=" not in t and t in LONGVAL:
                        if b == "env" and t == "--split-string" and i < len(seg):
                            nested = seg[i]
                        i += 1
                    continue
                for k, ch in enumerate(t[1:], 1):
                    if b == "xargs" and ch == "i":  # -i[REPL], optional joined value, default {}
                        ph.append(t[k + 1:] or "{}")
                        break
                    if ch in vals:
                        val = t[k + 1:] or (seg[i] if i < len(seg) else "")
                        i += 0 if t[k + 1:] else 1
                        if (b == "env" and ch == "S") or (b == "flock" and ch == "c"):
                            nested = val
                        if b == "xargs" and ch in "IJ":
                            ph.append(val)
                        break
            if b in ("timeout", "flock") and i < len(seg):
                i += 1  # the duration / lock file
                if b == "flock" and seg[i:i + 1] == ["-c"]:
                    nested, i = seg[i + 1] if i + 1 < len(seg) else "", i + 2
        else:
            break
    return i, ph, nested


def _head(prefix):
    """argv0 of the last command in `prefix` (text before a heredoc marker)."""
    try:
        toks = shlex.split(re.split(r"[;&|\n(]", prefix)[-1])
    except ValueError:
        return ""
    i = _unwrap(toks)[0]
    return os.path.basename(toks[i]) if i < len(toks) else ""


def _feed(name, text):
    """Reason when `text` is fed to shell/interpreter `name` and is destructive."""
    if name in SHELLS:
        return check(text, 1)
    if INTERP.match(name) or name in AWK:
        return _body(text)
    if name == "sqlite3" and _sqlite([text], 1):
        return _sqlite([text], 1)
    if name in SQLCLI and SQLDROP.search(SQLCOMMENT.sub(' ', text)):
        return "SQL DROP/TRUNCATE/DELETE-all through a database client. Ask the owner"
    return ""


def _bodies(cmd):
    """Backtick and `$(...)` bodies of the raw text (balanced parens), scanned recursively by the caller."""
    out = re.findall(r"`([^`]*)`", cmd)
    end = 0
    for m in re.finditer(r"\$\(", cmd):
        if m.start() < end:
            continue  # nested: the outer body already holds it and check() recurses into it (no fan-out blowup)
        depth, j = 1, m.end()
        while j < len(cmd) and depth:
            depth += (cmd[j] == "(") - (cmd[j] == ")")
            j += 1
        if depth == 0:  # an unclosed `$(` never runs, and its text is already tokenized by the caller
            out.append(cmd[m.end():j - 1])
        end = j
    return out


def _subbody(t, tick):
    """Text of a substitution up to its matching `)` (nested `$(...)` counted) or closing backtick; whole `t` when unclosed."""
    if tick:
        return t.split("`", 1)[0]
    depth = 1
    for j, c in enumerate(t):
        depth += (c == "(") - (c == ")")
        if not depth:
            return t[:j]
    return t


def _decexec(cmd):
    """True when a shell word is followed (no `|;&` or newline between, within 300 chars) by a decoding substitution."""
    if not re.search(r"base64|b64|xxd|printf|openssl", cmd):
        return False
    for n, m in enumerate(DECSTART.finditer(cmd)):
        if n >= 64:
            return bool(DECODE.search(cmd))  # the cap fails closed only when a decoder is somewhere in the text
        w = cmd[m.end():m.end() + 600]
        g = re.search(r"[|;&\n]", w[:300])
        for k, sub in enumerate(SUBST.finditer(w[:g.start() if g else 300])):
            if k >= 8:
                return bool(DECODE.search(cmd))  # fail closed on a pile of substitutions after one shell word
            if DECODE.search(_subbody(w[sub.end():sub.end() + 400], w[sub.start()] == "`")):
                return True
    return False


def _fallback(cmd):
    """Regex scan of raw text for the destructive classes; used when parsing fails."""
    cmd = cmd.replace("\\\n", "")
    return "destructive pattern in unparseable command (regex fallback)" if any(p.search(cmd) for p in FALLBACK) else ""


def check(cmd, _depth=0, _ph=None):
    """Return a one-line reason `cmd` is destructive, or '' (parse errors use the regex fallback).

    `_ph`: xargs placeholders inherited by a nested `sh -c` body."""
    cmd = cmd.replace("\\\n", "")
    if _depth > MAXDEPTH:
        return _fallback(cmd)
    for m in HEREDOC.finditer(cmd):  # a heredoc into a shell/interpreter is code; any other body is data
        r = _feed(_head(cmd[cmd.rfind("\n", 0, m.start()) + 1:m.start()]), m.group(3))
        if r:
            return r
    cmd = HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)
    cmd = re.sub(r"\$\{IFS\}|\$IFS\b", " ", cmd)  # rm${IFS}-rf is rm -rf
    if "()" in cmd and FORKBOMB.search(cmd):
        return "fork bomb. Never run it"
    if _decexec(cmd):
        return "eval/shell of a decoded base64/hex payload cannot be vetted. Decode to a file, read it, then run it"
    if not _depth and "=" in cmd and "$" in cmd:  # `x=rm; $x -rf /`: expand simple assignments once and re-check
        env = {m[1]: m[2][1:-1] if re.fullmatch(r"'[^']*'|\"[^\"]*\"", m[2]) else m[2]
               for m in re.finditer(r"(?:^|[;&|\n]\s*)(\w{1,32})=('[^']{0,200}'|\"[^\"]{0,200}\"|[^\s;&|'\"]{0,200})", cmd)}
        ex = re.sub(r"\$(?:\{(\w+)\}|(\w+))", lambda m: env.get(m[1] or m[2], m[0]), cmd)
        if env and ex != cmd:
            r = check(ex, 1)
            if r:
                return r
    if DYNCMD.search(cmd):
        return "command word built from a variable or substitution with -rf/--hard. Spell the command out"
    try:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=";&|()<>\n")
        lex.whitespace, lex.whitespace_split = " \t\r", True
        lex.commenters = ""  # shlex's `#` comment swallows the newline and hides every later line
        toks = list(lex)
    except ValueError:
        return _fallback(cmd)
    for b in _bodies(cmd):
        r = check(b, _depth + 1)
        if r:
            return r
    segs, ops, hs, hd, skip = [[]], [""], [None], [False], None
    for t in toks:
        if PUNCT.fullmatch(t):
            if t == "(" and not segs[-1] and ops[-1] == "|":
                continue  # `| (sh)`: stay in the pipeline
            if (re.search(r"[;|()\n]", t) and t != ">|") or not re.search(r"[<>]", t):
                segs.append([])
                hs.append(None)
                hd.append(False)
                ops.append("|" if t in ("|", "|&") else "<(" if "<(" in t else "")
                skip = None
            else:  # redirection: the next token is its target; the command continues
                if segs[-1] and segs[-1][-1].isdigit():
                    segs[-1].pop()
                skip = "hs" if t.endswith("<<<") else "t>" if t in (">", ">|", "&>") else "ta" if t in (">>", "&>>") else "t"
                hd[-1] = hd[-1] or "<<" in t
        elif skip:
            if skip in ("t>", "ta") and _sysw(t, skip == "ta"):
                return "redirect writes a system file. Edit a copy and ask the owner"
            if skip == "hs":
                hs[-1] = t
            skip = None
        elif not segs[-1] and re.fullmatch(r"\{[^{}\s,]*(?:,[^{}\s,]*)+\}", t):
            segs[-1].extend(t[1:-1].split(","))  # `{rm,-rf,$X}` brace-expands to a command
        else:
            segs[-1].append(t)
    # fetch: curl/wget earlier in the pipeline; feed: echo/printf text; src: an earlier stage relays text
    fetch, prev, feed, src, up = False, "", None, False, []
    for n, (seg, op, here) in enumerate(zip(segs, ops, hs)):
        if not seg:
            continue
        if op != "|":
            fetch, feed, src, up = False, None, False, []
        i, ph, nested = _unwrap(seg)
        ph = ph or _ph
        if i and i == len(seg) - 1 and re.search(r"\s", seg[i]) and any(os.path.basename(t) == "watch" for t in seg[:i]):
            nested = seg[i]  # watch 'rm -rf /x': one quoted command string
        if nested:
            r = check(nested, _depth + 1, ph)
            if r:
                return r
        if i >= len(seg):
            continue
        name, a = os.path.basename(seg[i]), seg[i + 1:]
        r = _cmd(name, a, ph, _depth)
        if not r and name == "rm" and ph and op == "|" and any(t.startswith(("/", "~", "$")) and not _scoped(t) for t in up):
            r = "rm of paths piped from a list outside scratch space. List them first, then `rm` exact paths"
        if not r and name == "eval":
            r = check(" ".join(a), _depth + 1, ph)
            for b in _bodies(" ".join(a)):  # eval "$(echo 'rm -rf /')": the echoed text is the command
                try:
                    e = shlex.split(b)
                except ValueError:
                    e = []
                if not r and e[:1] in (["echo"], ["printf"]):
                    r = check(" ".join(e[1:]), _depth + 1, ph)
        if not r and name in SHELLS + ("su",):
            for j, t in enumerate(a[:-1]):
                if re.fullmatch(r"-[A-Za-z]*c[A-Za-z]*", t):
                    r = check(a[j + 1], _depth + 1, ph)
                    break
        last = n + 1 >= len(segs) or ops[n + 1] != "|"
        if not r and op == "|" and src and last and (name in SHELLS or INTERP.match(name)) \
                and all(t.startswith("-") for t in a):
            r = "text relayed into a shell/interpreter cannot be vetted. Write it to a file, read it, then run it"
        if not r and name in SHELLS + ("source", ".") and "/dev/stdin" in a:
            r = "shell reading /dev/stdin cannot be vetted. Write it to a file, read it, then run it"
        if not r and op == "<(" and prev in SHELLS + ("source", "."):
            r = "shell/source fed by process substitution cannot be vetted. Write it to a file, read it, then run it"
        if not r and here is not None:
            r = _feed(name, here)
        if not r and op == "|" and feed:
            r = next((x for x in (_feed(name, f) for f in feed) if x), "")
        if not r and op == "|" and fetch and (name in SHELLS or INTERP.match(name)):
            r = "curl/wget piped to a shell/interpreter. Download, read it, then run it"
        if r:
            return r
        up = (up + seg[:20])[-200:]
        src = src or hd[n] or name in ("echo", "printf", "cat", "tee") or (name == "openssl" and a[:1] == ["enc"] and any(
            t in ("-d", "-base64", "-a") for t in a)) or (name == "xxd" and any(_bundle(t, "r") for t in a)) or (
            name == "base64" and any(B64D.fullmatch(t) for t in a))
        fetch = fetch or name in ("curl", "wget")
        feed = ([" ".join(a)] + a) if name in ("echo", "printf") else None  # joined, and each arg (printf FORMAT ARG)
        prev = name
    return ""


def selftest():
    bad = ["rm -rf $X", "/bin/rm -fr /", "bash -c 'rm -rf $DIR'", "env rm -rf ~/", "git reset --hard HEAD~1",
           "git -C x clean -fdx", "git push origin +main", "find . -delete", "find . -exec rm {} \\;",
           "dd if=/dev/zero of=/dev/disk2", "mkfs.ext4 /dev/sda1", "chmod -R 777 /", "curl x | sudo bash",
           "pkill -9 -f node", "kill -9 $(pgrep -f x)", "ls | xargs rm -rf", "echo ok; rm -rf $X",
           "{ rm -rf $X; }", "bash -lc 'rm -rf $X'", "timeout 5 rm -rf $X", "echo $(rm -rf $X)", "bash <(curl x)",
           "echo \"rm -rf $X", "sudo -n rm -rf $X", ">o rm -rf $X", "echo 'rm -rf $X' | sh", "git reset --ha"]
    good = ["rm -rf node_modules", "rm -rf ./build", "rm /tmp/x", "git push --force-with-lease origin f", "git clean -n",
            "git restore --staged .", "git branch -d old", "dd if=/dev/zero of=./i bs=1", "kill -TERM 4242",
            "kill -0 $PID", "kill -s 0 $PID",
            "curl -o o.sh https://example.com/i.sh", 'grep -rn "rm -rf" docs/', "echo 'git reset --hard'",
            "find . -name x", "sudo -n ls"]
    for c in bad:
        assert check(c), f"missed: {c}"
    for c in good:
        assert not check(c), f"false positive: {c}"
    print("destructive_guard selftest ok")


def main():
    if "--selftest" in sys.argv:
        return selftest() or 0
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
        cmd = (data.get("tool_input") or {}).get("command")
        if data.get("tool_name", "Bash") != "Bash":
            return 0
        if not isinstance(cmd, str):
            cmd = " ".join(map(str, cmd)) if isinstance(cmd, (list, tuple)) else None if cmd is None else json.dumps(cmd)
    except Exception:
        cmd = raw  # not JSON / wrong shape: scan the raw text
    if not cmd:
        return 0
    try:
        why = check(cmd)
    except Exception:
        why = _fallback(cmd)
    if why:
        print(f"Blocked destructive command ({why}). Best-effort guard. Owner: to run it anyway, type the "
              "command yourself with the `!` prefix in Claude Code.", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
