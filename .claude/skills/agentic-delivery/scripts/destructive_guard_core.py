#!/usr/bin/env python3
"""PreToolUse(Bash) hook: deny a destructive host command before it runs. Never executes the command.

BEST-EFFORT and STRING-LEVEL: it catches common honest mistakes and common wrappers. It is NOT a security
boundary. The OS sandbox (`sandbox.enabled`, set by `install.sh --apply-operating-layer`) is the boundary:
operating-discipline item 8 (`references/operating-discipline.md`, "Safety rules": never run a delete or kill
on a host, never `rm -rf` a variable-built path). Known-uncovered: interpreter APIs (`subprocess`, `exec`,
`system` on built strings), IFS and brace-expansion tricks, variables holding a command, aliases, scripts,
`g=git; $g ...` and exotic wrappers.

Reviewed false positives are allowed, each pinned beside the true block it must not loosen
(`scripts/test_destructive_fp.py`): `kill $(cat X.pid)` only when X.pid is a relative path or under a temp dir, `$TMPDIR`,
`$PWD` or `$CLAUDE_PROJECT_DIR` (no `..`), owned by the current user, and holds a pid under this session's `claude` process;
`pkill -P <pid>` only for such a pid (read-only `ps`, denied when unknown), and a bare `pkill -V`;
`curl | python3 -c CODE` only by ALLOWLIST: CODE is json-only (`json.load(sys.stdin)` / `json.loads(sys.stdin.read())`,
printed or indexed with literals); every other interpreter, flag, script or code keeps the deny;
triple-quoted strings in an interpreter heredoc that never execs them (edit-script replacement text; spans are found by
parsing the heredoc as Python, and unparsable text keeps the deny);
`git worktree remove --force` of ONE literal path whose `git status --porcelain` is empty; and `git branch -D` of at
most 3 literal branches already on a remote-tracking ref or merged into HEAD. The last two run read-only `git` queries
(2s timeout each, 5s total budget, hook timeout 20s) and fail closed (stay denied) on any error, `-C`/`GIT_DIR`, variable, glob or odd shape. Like git
itself, the clean check does not look at ignored files (`.env`, build output): they go with the worktree.

Parsing (pure stdlib, text only apart from those two git queries): backslash-newline joined, heredoc bodies and here-strings set aside, shlex
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
  `crontab -r|-ir|/dev/null`, a `$(...)` substitution as the command word (decoder or printf/echo escapes), `$'\\x72\\x6d'` words decoded first,
  `git push --force-with-lease` to main/master, `git worktree remove --force`, a secret variable in a curl/wget
  URL query, `aws s3 rm --recursive|s3 rb --force|ec2 terminate-instances|rds delete-db-*`, `gcloud projects delete`,
  `az group delete`, `terraform|tofu destroy|apply -destroy`, `kubectl delete namespace|all --all`,
  `redis-cli FLUSHALL|FLUSHDB`, mongo `dropDatabase`, `wipefs -a|-o` (not `-n`; a bare listing is fine), `diskutil eraseDisk|eraseVolume|...`,
  and `eval`/`sh` of a `$(... base64 -d|xxd -r|printf hex-escape ...)` payload; also package `unpublish|yank|purge`, any
  `aws <svc> delete-*|terminate-*|purge-*`, `gcloud ... delete`, `gsutil rm -r`, `az ... delete|purge`, `kubectl delete --all|drain`,
  `docker|podman|nerdctl exec|run IMG CMD` and `kubectl exec -- CMD` (CMD is checked), `>>`/`tee` onto a system file, `gh <noun> delete`, `curl -X DELETE`,
  `helm uninstall`, `pulumi destroy`, `terraform state rm`, `parted mklabel`, `cqlsh` DROP, `git filter-branch`, `> /etc/...`, an
  alias to a destructive command and one-step `x=rm; $x -rf` indirection; wave 6: `tmutil delete`, `cdk|cdktf|sst destroy`, `doctl ... delete`,
  `flyctl|heroku` destroy, `hg strip|purge`, `make clean VAR=/`, `gem uninstall` of everything, `diskutil apfs delete*`, `set -- rm ...; "$@"`,
  `kubectl run` with hostPID/privileged/hostPath, `ln|rsync` onto a system path, vault revoke/policy delete, `git reflog delete`, `reg add|save HKLM`,
  `wmic ... call create|uninstall`, and Windows `del` of a system file, a `..` path or a bare `*`/`*.*`; wave 7: `rclone purge|delete|sync`, `restic forget|prune`,
  `zfs|zpool destroy`, `lvremove|vgremove|pvremove`, `firebase|supabase|vercel|netlify|wrangler ... delete|remove|rm`, `supabase db reset --linked`, a relative `rm -r` after
  `cd /abs`, `bash -c 'f=-rf; rm $f X'`, `ln` onto `~/.ssh|.bashrc|.zshrc`, `rsync|scp` to `host:/etc/`, `vault operator seal|rekey`, `reg add` under HKCU|HKU Software Classes,
  `wmic ... call reboot`, ClickHouse `ALTER TABLE ... DELETE|DROP PARTITION`, a SQL client fed `< file.sql` that drops, `make nuke|uninstall DESTDIR=/`, mongo `bulkWrite` deletes. Wave 8: `sgdisk` zap/clear/delete/new/load, truncating a private key or credential file (`> f`, `: > f`, `truncate`, `cp /dev/null`), `npm deprecate|owner rm`, `restic key remove|unlock --remove-all`, `lvresize` unless growing, `pvcreate|vgcreate -f`, `zfs receive -F`, `zpool create -f`, and a padded 20 KB+ body using a variable (fail closed); `git clean -f` of named relative paths (no `.git`, no -C/GIT_DIR) and `git stash drop stash@{N}` are allowed. Wave 9: `rm` of a credential file (cloud and registry CLI configs, `.netrc`, `.envrc`, `.git-credentials`, service-account JSON), `gpg --delete-*keys`, `security delete-*`; the quoted payload of gh/glab `--body|--title|-b|-t|--notes|--message` and `git commit -m` is text, not a command, and `gh ... --remove-label` is allowed; every block reason ends with a rewrite hint (`scripts/test_security_gates_guard_w9.py`). Wave 10: `ssh-add -D`, `git update-ref -d`, `rm -r` of `.git`, `compose down -v|--rmi`, `Remove-Item` with no target, `cipher /w`; a payload a shell runs later (a pipeline ending in a bare shell, text written to a file the same command runs, `tee >(sh)`, `eval "$(cat)"` with a heredoc, a heredoc read by `ssh` or a container shell); `gh alias set` bodies and git config values git runs (alias, `core.sshCommand`, pager, editor); more credential files (`.npmrc`, `.ssh/*` but `known_hosts`, `*.pem`, `*.key`); `git <verb> --help|-h` is allowed and a bare `credentials` is not a credential (`scripts/test_security_gates_guard_w10.py`). Wave 11: `blkdiscard`, truncating a database file or server data dir (`: > x.sqlite`, `cp /dev/null`, `dd of=`, `tee`, `exec >`; temp, build and cache dirs exempt), `git push --force-with-lease|--force-if-includes` when it targets a shared branch (`main|master|develop|trunk|prod|stable|staging|release*|hotfix*|HEAD`) or names no branch, PowerShell `iex`/`Invoke-Expression` of downloaded content, `docker|podman container|image|volume|network prune -f` (a `--filter` scopes it; `system prune -f` stays allowed without `-a|--volumes`), `kubectl delete node` ; the output of `$(printf|echo ...)` that a shell runs is checked as a command, `$PWD/<child>` and a variable assigned once (statement level, before use) a relative path are in-tree (`scripts/test_security_gates_guard_w11.py`). Allowed: `--help`/`-help`, `--dry-run`/`--dryrun`
  (not `=none`; aws/kubectl/helm only), `rm`/`find -delete|-exec rm`/`shred` inside a named child of `$TMPDIR` or `/tmp`, a single `find ./dir ... -delete|-exec rm {}` under a
  named relative dir (no `-L`, no second action, no earlier `cd` out), `echo ./a | xargs -I{} rm -rf {}` of literal relative paths (same cd rule). A `--help` after
  other arguments of rm/chmod/chown/dd/shred/mkfs/diskutil (only a lone one is usage) still gets the full check.
  Residuals: a `/tmp/<name>` symlink to elsewhere, or an unset `$TMPDIR` (`$TMPDIR/x` becomes `/x`), is trusted; `> file` over
  a system path is caught (so is `cp`/`mv`/`ln`/`rsync`/`scp` onto one, `.bak` copies included); `pip uninstall` is blocked only for xargs or `-r`.
Wave 16 (`scripts/test_security_gates_heldout21_blind.py`): `mdadm --zero-superblock|--create`, `cryptsetup erase|luksErase|luksFormat|luksKillSlot|luksRemoveKey`,
`docker swarm leave --force`, a delete verb fed by `xargs` (redis-cli, kubectl, docker, ...), `aws s3 sync --delete`, `gsutil rsync -d`, writes to `/proc/sysrq-trigger` or
`/proc/self/mem`, `crontab` fed empty input, rsync `--del`/`--remove-source-files` (an option value such as `--exclude -n` is not a flag). Allowed: `${TMPDIR:?}/child`, removing the
dir of a bare `mktemp -d`, a named child of `~/.cache`, `find . -type f -name '*.orig' -exec rm -f`, rsync into a named child of `/var/www`.
Wave 17 (`scripts/test_security_gates_heldout22_blind.py`): `kubectl replace --force`, `kubectl scale --all --replicas=0`, `etcdctl del --from-key|--prefix`, `bq rm -r|-f`, an `ansible`
ad-hoc `-m shell|command|raw -a CMD` (CMD is judged as a command; no `-m` means `command`) and `-m file -a "path=P state=absent"` (judged as `rm -rf P`; `--check` is a dry run). Allowed:
`pulumi destroy --preview-only`, `aws dynamodb delete-item` with one literal `--key`, `npm unpublish` of one exact prerelease version, `cargo yank` of one exact prerelease version (`--undo` restores it; a stable version stays blocked).
Everything else is allowed.

No in-repo grant or allow list: anything an agent can write, an agent can forge. When the owner really wants a
denied command, the owner runs it themselves with the `!` prefix in Claude Code (the block message says so).

Never crashes. Unparseable stdin, a non-string command, a shlex failure or any internal error falls back to
a regex scan of the raw text for the same destructive classes: block on a hit, otherwise allow (a guard that
errors closed would wedge every session; one that errors open on a hit would be trivial to evade).
Side effects: none. `--selftest` runs assertions.
Wave 19 (`scripts/test_security_gates_heldout24_blind.py`): removal of a core package (libc, glibc, systemd, kernel, dpkg, sudo, ...) through `apt|dnf|yum|zypper|apk|rpm|dpkg|pacman`
(`rpm -e --nodeps` of anything; `--simulate|--test|--dry-run` is a preview), `influx delete` without `--predicate` and `influx bucket|org delete`, a `cockroach sql` DROP, `cypher-shell`
`MATCH (n) DETACH DELETE n`, `oc delete project`, `eksctl|skopeo|crane|regctl|oras delete`, `borg delete|prune` and `velero ... delete --all|-l` (no `--dry-run`), `setfacl|chgrp|chattr -R` on
root or home, `chmod 000` of a critical binary, `passwd -l|-d` of root (or no user), `usermod -L root`, and `find /home -exec chown|chgrp|setfacl`.
"""
import ast
import codecs
import fnmatch
import json
import os
import pathlib
import itertools
import posixpath
import re
import shlex
import signal
import subprocess
import sys
import time

_T0, _BUDGET = time.monotonic(), 5  # seconds the read-only `ps`/`git` helpers may use in total before they give up (deny)
KW =("{", "}", "if", "then", "else", "elif", "fi", "while", "until", "do", "done", "!", "coproc")
# wrapper -> short flags that take a value (only these consume the next token)
VAL = {"env": "uCS", "sudo": "ugCDhprtU", "doas": "uC", "nice": "n", "timeout": "sk", "xargs": "adEILnPsIJSR",
       "stdbuf": "ioe", "ionice": "cnpPu", "time": "fo", "exec": "a", "caffeinate": "tw", "flock": "wEc",
       "command": "", "builtin": "", "watch": "n", "nohup": "", "setsid": "", "chronic": "", "busybox": ""}
LONGVAL = ("--user", "--group", "--chdir", "--host", "--prompt", "--role", "--type", "--other-user", "--unset",
           "--split-string", "--signal", "--kill-after", "--arg-file", "--delimiter", "--max-args",
           "--max-procs", "--max-lines", "--max-chars", "--interval")
SHELLS = ("bash", "sh", "zsh", "dash", "ash", "ksh", "mksh", "csh", "tcsh", "fish", "nu", "pwsh", "powershell")
AWK = ("awk", "gawk", "mawk", "nawk")
INTERP = re.compile(r"^(python[\d.]*|perl|ruby|node|nodejs|bun|deno|php|lua)$")
EVALFLAG = re.compile(r"-[A-Za-z]*[ceErp][A-Za-z]*")
SAFE_DEV = ("/dev/null", "/dev/zero", "/dev/stdout", "/dev/stderr")
GIT_OPT_VAL = ("-c", "-C", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--super-prefix", "--config-env")
LIT = r"""['"][^'"/$@][^'"$@]*['"]"""  # a literal relative path
DELAPI = re.compile(r"(rmtree|remove_tree|os\.(?:remove|unlink|rmdir|removedirs)|rmSync|rmdirSync|unlinkSync|\bfs\.rm|rm_rf"
                    r"|File\.delete|\bunlink|\brmdir)(?:\(|\s)(?!\s*(?:" + LIT + r"\s*(?:[,);]|$)|(?:tempfile\.)?mkdtemp\(\s*\)\s*[,);]))")
BODYRM = re.compile(r"\brm\s+-\w*[rR]\w*\s*(?:\S*[$/~*]|['\"]\s*\+|%s|\{)")  # variable/root path or string concatenation
TRIPLEQ = re.compile(r"'''.*?'''|\"\"\".*?\"\"\"", re.S)  # a triple-quoted block is data (an edit script's replacement text) unless the body also executes strings
RUNSTR = re.compile(r"\b(?:exec\w*|eval|compile|system|popen|Popen|check_output|check_call|spawn\w*|import_module|__import__|loadstring|passthru|shell_exec|runpy|Function)\b|subprocess|child_process|\.(?:run|call)\s*\(")
PIDFILE = re.compile(r"(\bkill(?:[ \t]+-\w+)*[ \t]+)\"?\$\([ \t]*(?:cat|head[ \t]+-n?[ \t]*1)[ \t]+\"?([^\s()`;|&<>\"]*pid)\"?[ \t]*\)\"?")  # `kill $(cat dev.pid)`
PIDDIR = re.compile(r"(?:/tmp/|/private/tmp/|/var/folders/|\$\{?(?:TMPDIR|PWD|CLAUDE_PROJECT_DIR)\}?/|(?![/~$.])[\w.-])")  # a lane-owned dir: temp, cwd, project, or a relative path


def _pidfile(m):
    """Neutralize `kill $(cat X.pid)` only when X is in a lane-owned dir (no `..`), is a file this user owns, and holds a pid `_own_pid` accepts; anything else (`/var/run/sshd.pid`, missing file) stays a denied substitution."""
    p = m.group(2)
    if PIDDIR.match(p) and ".." not in p:
        try:
            f = os.path.expandvars(p)
            if os.stat(f).st_uid == os.getuid() and _own_pid(int(pathlib.Path(f).read_text()[:32].split()[0])):
                return m.group(1) + "4242"
        except (OSError, ValueError, IndexError):
            pass
    return m.group(0)
PRINTCALL = re.compile(r"""\b(?:print|puts|echo|console\.(?:log|error)|sys\.std(?:out|err)\.write)\s*\(((?:[^()'"]|'[^']*'|"[^"]*")*)\)""")
AWSVAL = ("--profile", "--region", "--endpoint-url", "--output", "--query", "--color", "--ca-bundle", "--cli-read-timeout", "--cli-connect-timeout", "--cli-binary-format")
HGVAL = ("-R", "--repository", "--cwd", "--config", "--encoding", "--encodingmode", "--color", "--pager")
SQLCLI = ("psql", "mysql", "mariadb", "sqlite3", "mongosh", "sqlcmd", "cqlsh", "clickhouse-client", "clickhouse-local", "clickhouse", "cockroach", "cypher-shell")
SQLCOMMENT = re.compile(r"/\*.*?\*/", re.S)
SQLDROP = re.compile(r"\b(?:drop\s+(?:database|schema|keyspace|table|partition|part)|alter\s+table\s+(?:if\s+exists\s+)?\S+\s+(?:on\s+cluster\s+\S+\s+)?(?:delete|drop|detach|truncate)\b|truncate\s+\w|delete\s+from\s+\w+\s*(?:;|$))", re.I)
DYNCMD = re.compile(r"(?:^|[;&|\n({]|\bthen\b|\bdo\b)\s*\"?(?:\$\([^()]{0,200}\)|`[^`]{0,200}`|\$\{?\w{1,64}\}?)\"?(?:\s+\S+){0,8}?\s+(?:-\w*(?:rf|fr)\w*|--hard)\b")
FORKBOMB = re.compile(r"(\S{1,32})\(\)\s*\{\s*\1\s*\|\s*\1\s*&")
SSH_VAL = "bcDEeFIiJLlmOopQRSWw"
# eval/shell fed a substitution that decodes base64, hex (`xxd -r`) or printf escapes; scanned in bounded windows after at most 64
# shell words and 8 substitutions each (more than that alongside a decoder fails closed), so the cost is linear in the input, never quadratic
DECSTART = re.compile(r"\b(?:eval|source|(?:ba|z|da|k|a)?sh)\b|(?:^|[;&|\n({]|\bthen\b|\bdo\b)\s*(?:\w{1,64}=\S{0,200}\s+){0,8}(?:sudo\s+(?:-\S+\s+){0,8})?(?=\$\(|`)")  # a shell word, or a bare substitution as the command word (its output is the command)
SUBST = re.compile(r"\$\(|`")
DECODE = re.compile(r"\bbase64\b.{0,300}(?:\s-\w*[dD]|--decode)|\bxxd\b.{0,100}\s-\w*r|\bprintf\b.{0,300}\\(?:x[0-9a-fA-F]|[0-7]{3})|\bopenssl\s+enc\b.{0,100}\s-(?:d\b|base64\b|a\b)"
                    r"|\bpython[\d.]*\b.{0,200}(?:b64decode|b32decode|decodebytes|a2b_base64|unhexlify|fromhex)", re.S)
DRY = ("--dry-run", "--dryrun", "--dry-run=client", "--dry-run=server")  # `--dry-run=none` really runs, so it is not listed
BLKDEV = re.compile(r"/dev/(?:[hsv]d|xvd|nvme|r?disk|mmcblk|loop|dm-|md|mapper/|sr|zd|nbd|k?mem|n?st\d|sg\d|bsg/|ada\d|nvd\d|mtd)", re.I)  # a raw disk: any write to it destroys the data on it
WWW = re.compile(r"/var/www/\w[\w.-]*(?:/\w[\w.-]*)*/?")
XTOOLS = ("redis-cli", "valkey-cli", "kubectl", "oc", "docker", "podman", "nerdctl", "gh", "glab", "az", "gcloud", "gsutil", "aws", "helm", "heroku", "doctl", "rclone")
XDEL = re.compile(r"(?i)del|unlink|delete|remove|rm|rmi|destroy|drop|purge|terminate|hdel|srem|zrem")
RMTEMP = re.compile(r"(\brm(?:[ \t]+-[\w-]+)*[ \t]+(?:--[ \t]+)?)([\"]?)(?:\$\(mktemp -d\)|`mktemp -d`)\2(?=[ \t]*(?:$|[;&|)\n]))")
CACHEOP = re.compile(r"(?<=\s)([\"']?)(?:~|\$HOME|\$\{HOME\})/\.cache/(\w[\w.-]*)(?=[\"']?(?:\s|$))")
RAWPROC = re.compile(r"/proc/(?:sysrq-trigger|(?:self|thread-self|\d+)/mem|kcore)", re.I)  # a write here reboots, crashes or rewrites the live kernel
TOPLEVEL = re.compile(r"\$\(git rev-parse --show-toplevel\)/((?:build|dist|out|target|node_modules|__pycache__|coverage)(?:/\w[\w.-]*)*)")  # repo-root child; a failed git leaves `/child`, so only disposable build dirs
MKTEMP = re.compile(r"(?:^|[;\n])[ \t]*(\w{1,32})=[\"]?(?:\$\(mktemp -d\)|`mktemp -d`)[\"]?[ \t]*(?=;|&&|\n|$)")
IMGFILE = re.compile(r"(?:\./)?\w[\w.-]*\.(?:img|raw)")  # a relative disk-image file, not a device
SYMLN = re.compile(r"\bln\b[^;&|\n]*\s(?:-\w*s|--symbolic\b)")  # a symlink made in the same line can point a scratch path at the host
RMREC = re.compile(r"\brm\b[^;&|\n]*\s(?:-\w*[rR]|--rec)")
FRBOOL = frozenset(("--force", "-f", "--analyze", "--dry-run", "--partial", "--invert-paths", "--use-base-name", "--debug", "--quiet", "--no-gc", "--no-fetch", "--proceed", "--no-data"))
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
CREDBASE = re.compile(r"(?i)id_(?:rsa|dsa|ecdsa|ed25519)|\.(?:netrc|npmrc|pypirc|pgpass|htpasswd|envrc|git-credentials)|service[-_]?account[^/]*\.json|[^/]*credentials[^/]*\.json|authorized_keys|[^/]*\.(?:pem|key|p12|pfx|jks|kdbx|keystore)")
CREDDIR = re.compile(r"(?:^|/)(?:\.aws/(?:credentials|config|sso(?:/|$))|\.ssh/(?!known_hosts)|\.config/gh/hosts\.yml|\.docker/config\.json|\.kube/config|\.config/gcloud(?:/|$)|\.gnupg/(?:private-keys-v1\.d|secring\.gpg|trustdb\.gpg|pubring\.kbx))")
# a quoted payload of gh/glab `--body|--title|-b|-t|--notes|--message|-m` or `git commit -m|--message` is text, not a command (single quotes never expand; double quotes only without `$(`/backtick)
DATAFLAG = re.compile(r"""((?:^|[;&|\n(])[ \t]*(?:\w+=\S*[ \t]+)*(?:(?:gh|glab)\b(?:[ \t]+[^\s;&|'"()]+)*?[ \t]+(?:--(?:body|title|notes|message)|-[btm])|git\b(?:[ \t]+[^\s;&|'"()]+)*?[ \t]+commit\b(?:[ \t]+[^\s;&|'"()]+)*?[ \t]+(?:--message|-\w*m))(?:=|[ \t]+))('[^']*'|"(?:[^"\\$`]|\\.)*")""")
PAAS = ("firebase", "supabase", "vercel", "netlify", "wrangler", "railway", "pscale", "neonctl", "turso", "convex", "appwrite")
PAASDEL = re.compile(r"(?:^|[:_-])(?i:delete|remove|rm|del|destroy|drop|purge|unset)(?![a-z])")  # also deleteSite
HOMEP = re.compile(r"(?:~|\$HOME|\$\{HOME\}|/(?:Users|home)/[^/]+|/root)/\.(?:ssh|bashrc|bash_profile|bash_login|bash_logout|profile|zshrc|zprofile|zshenv|zlogin|zlogout|inputrc|gitconfig|netrc|npmrc|aws|gnupg)(?:/|$)")
ARTGLOB = re.compile(r"\*\.(?:pyc|o|tmp|log|orig|class|map|bak|swp)|node_modules|__pycache__|\.pytest_cache|\.mypy_cache")  # build artifacts, and caches named exactly
LITPATH = re.compile(r"(?:\./)?\w[\w.-]*(?:/\w[\w.-]*)*/?")  # a plain relative path word
SENS = re.compile(r"(?i)(?:id_(?:rsa|dsa|ecdsa|ed25519)|[^/]*\.(?:pem|key|p12|pfx|jks|kdbx|keystore)|\.env(?:\.(?!example|sample|template|dist)\w+)?|\.netrc|\.pgpass|\.htpasswd|\.envrc|\.git-credentials|service[-_]?account[^/]*\.json|[^/]*credentials[^/]*\.json|authorized_keys|credentials|shadow|master\.key)")  # private keys and credential files
EMPTYSRC = ([], [":"], ["true"], ["false"], ["echo"], ["echo", "-n"], ["printf"], ["printf", ""], ["printf", "%s"], ["printf", "%b"], ["cat", "/dev/null"], ["exec"])  # commands whose `>` target is only truncated
SHARED = re.compile(r"(?i)(?:refs/\w+/)?(?:main|master|develop|development|trunk|dev|prod|production|stable|staging|gh-pages|lts|next|(?:release|releases|hotfix|lts)(?:[-_./].*)?)")  # a branch other people build on
PWDP = re.compile(r"^\$(?:PWD|\{PWD\})/")
DBFILE = re.compile(r"(?i)\.(?:sqlite3?|db3?|mdb|ldb|rdb|duckdb|mdf|ndf|ldf|ibd|frm|myd|myi|aof)$|(?:^|/)(?:var/lib/(?:postgresql|mysql|mariadb|mongodb|redis)|pgdata|mysql-data)(?:/|$)")  # database file or server data dir
SCRATCHDIR = re.compile(r"(?:^|/)(?:build|dist|out|target|node_modules|\.?cache|__pycache__|\.?tmp|fixtures?|testdata)/")  # build and cache output is disposable
PSDL = re.compile(r"(?i)\b(?:iwr|irm|invoke-webrequest|invoke-restmethod|downloadstring|downloaddata|curl|wget|webclient|start-bitstransfer)\b")
PSEXEC = re.compile(r"(?i)(?:^|[;&|({])[ \t]*(?:iex|invoke-expression)\b(?![ \t]*(['\"])[^$`]*\1)|\[scriptblock\]::create\s*\(")  # not a literal string
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


def _on(a, *names):
    """True when a boolean flag in `a` is set: bare, or `=` anything but false/0/no."""
    return any(t.split("=")[0] in names and t.partition("=")[2].lower() not in ("false", "0", "f", "no") for t in a if t.startswith("-"))


def _pulprev(a):
    """`pulumi destroy` that is only a preview: a standalone `--preview-only` (never an option value), none turned off, no `--skip-preview`/`--yes`."""
    on, k = [], 0
    while k < len(a):
        t, k = a[k], k + 1
        if t in ("-m", "--message", "-s", "--stack", "-C", "--cwd", "--config-file", "-t", "--target", "--exclude", "--secrets-provider", "--policy-pack", "--policy-pack-config", "--parallel", "-p", "--color", "--tracing", "--profiling", "--plan"):
            k += 1  # the next token is this option's value
        elif t.split("=")[0] == "--preview-only":
            on.append(_on([t], "--preview-only"))
        elif _on([t], "--skip-preview", "--yes", "-y") or _bundle(t, "y"):
            return False
    return bool(on) and all(on)


def _zero(v):
    """A `--replicas` value that is zero (`0`, `+0`, `-0`, `0x0`, `0o0`) or cannot be read as a number (a variable): both block."""
    try:
        return int(v, 0) == 0
    except ValueError:
        return True


def _yank1(a):
    """`cargo yank` of one literal prerelease version (`--vers V`, `--version=V` or `crate@V`); a variable or a missing version is not pinned."""
    v = [a[k + 1] for k, t in enumerate(a[:-1]) if t in ("--vers", "--version")] + [t.partition("=")[2] for t in a if t.startswith(("--vers=", "--version="))] \
        + [t.split("@", 1)[1] for t in a if "@" in t and not t.startswith("-")]
    return len(v) == 1 and re.fullmatch(r"\d+\.\d+\.\d+-[0-9A-Za-z][0-9A-Za-z.+-]*", v[0]) is not None


CORE = re.compile(r"(?:libc6(?:-dev)?|libc-bin|libc|glibc(?:-common|-minimal-langpack|-all-langpacks)?|musl|busybox|libsystemd\d*|systemd(?:-sysv|-libs)?|kernel(?:-core)?|linux|linux-generic"
                  r"|linux-image-(?:generic|amd64|virtual|aws|azure|gcp|lowlatency|oem|cloud-amd64|arm64)|sudo|dpkg|apt|apk-tools|rpm|yum|dnf5?|pacman|filesystem|base|base-files|base-passwd|alpine-base|openrc"
                  r"|bash|dash|coreutils|openssh-server|openssh-client|ssh|grub(?:-pc|-efi-amd64|-efi-arm64|-common|2-common)?|libpam(?:0g|-modules|-modules-bin|-runtime|-systemd)?|pam|shadow-utils|shadow"
                  r"|util-linux|login|init|sysvinit-core|udev|e2fsprogs|passwd|mount|perl-base|tar|dbus|libssl\d\S*|openssl(?:-libs)?|libgcc-s1|libcrypt1|libaudit1|libacl1|libattr1|libblkid1|libmount1|libsmartcols1|libuuid1|zlib1g|ncurses-base|ncurses-libs|findutils|sed|gzip|netplan\.io"
                  r"|libgcc|zlib|libselinux|libstdc\+\+\d*|libxcrypt|rpm-libs|libdnf|krb5-libs|python3-(?:libs|dnf|rpm|hawkey|libdnf)|network-?manager|initramfs-tools|dracut|selinux-policy|libselinux1|ubuntu-(?:minimal|standard|desktop))(?:[:.=]\S+|-\d\S*)?", re.I)  # exact names plus a version/arch suffix: `bash-completion`, `apt-utils`, `kernel-devel`, `linux-headers-*` stay allowed
GLOBN = ("kernel", "kernel-core", "libc6", "glibc", "libsystemd0", "systemd", "linux-image-generic", "sudo", "bash", "dpkg", "openssl", "libssl3")
PKGVERB = {"rpm": r"--erase|-[a-zA-Z]*e[a-zA-Z]*", "dpkg": r"--remove|--purge|-[a-zA-Z]*[rP][a-zA-Z]*", "pacman": r"--remove|-[a-zA-Z]*R[a-zA-Z]*"}
PKGDRY = ("--simulate", "--just-print", "--dry-run", "--no-act", "--recon", "--test", "--assumeno", "--assume-no", "--print", "--downloadonly", "--download-only", "--print-uris")
PKGSHORT = {"apt": "sd", "apt-get": "sd", "aptitude": "s", "zypper": "D", "pacman": "p", "apk": "s"}
PKGROOT = {"pacman": "-r", "apk": "-p"}
HOMESUB = r"(?:~|\$\{?HOME\}?)/."
INFCMD = frozenset(("write", "query", "task", "auth", "user", "dashboard", "secret", "stack", "telegraf", "check", "rule", "endpoint", "label", "scraper", "notebook", "template", "config", "dbrp", "bucket", "org", "list", "create", "update", "find", "v1", "apply", "export"))
TOPDIRS = frozenset(("/home", "/root", "/Users", "/bin", "/sbin", "/usr", "/etc", "/lib", "/lib64", "/boot", "/var", "/dev", "/sys", "/proc"))
CYDEL = re.compile(r"\bdelete\b", re.I)
CYNODE = r"\(\s{0,20}(?:\(\s{0,20}\w{0,64}\s{0,20}\)|\w{0,64})\s{0,20}\)"  # `(n)`, `()` or the redundantly parenthesised `((n))`
CYMATCH = re.compile(r"\bmatch\s{0,20}(?:\w{1,64}\s{0,20}=\s{0,20})?" + CYNODE + "|,\\s{0,20}" + CYNODE, re.I)
CYFILT = re.compile(r"[(\[]\s{0,20}\w{0,64}\s{0,20}(?::[\w`]|\{\s{0,5}\w{1,64}\s{0,5}:)")  # a label, type or property map inside a node or relationship pattern
CYEND = re.compile(r"\b(?:(?<!starts )(?<!ends )with|return|set|remove|unwind|merge|create|foreach|order|limit|skip)\b", re.I)  # the pattern or predicate ends here
CYAND = re.compile(r"\band\b", re.I)
CYOR = re.compile(r"\b(?:or|xor)\b", re.I)
CYSKIP = re.compile(r"'(?:[^'\\]|\\.?)*(?:'|\Z)|\"(?:[^\"\\]|\\.?)*(?:\"|\Z)|//[^\n]*|/\*.*?(?:\*/|\Z)", re.S)  # strings and comments; an unterminated one runs to the end, so the scan stays linear
CYSPLIT = re.compile(r"\b(match|where|delete|call)\b", re.I)
CYAPOC = re.compile(r"apoc\.(?:periodic|cypher)\.", re.I)


SQLWHY = "SQL DROP/TRUNCATE/DELETE-all through a database client. Ask the owner, or for Cypher filter the delete with WHERE terms the guard can read: v.prop =|<>|<|>|STARTS WITH|IN literal or $param, v:Label, v.prop IS [NOT] NULL, id(v) or elementId(v) = or IN, a pattern predicate, joined by AND/OR (NOT only on those, no functions)"
CYLIT = r"(?:-\s{0,3})?(?:\d{1,20}(?:\.\d{1,20})?(?:e[+-]?\d{1,3})?|(?:'')+|true|false|\$\w{1,64}(?:\.\w{1,64}){0,3})"  # a literal or a parameter (strings are already `''`; a doubled quote gives two)
CYLIST = r"(?:\[\s{0,5}(?:" + CYLIT + r"(?:\s{0,5},\s{0,5}" + CYLIT + r"){0,200})?\s{0,5}\]|\$\w{1,64})"
CYOPD = r"\w{1,64}(?:\.\w{1,64}){1,3}"  # `n.a`, `n.a.b`
CYTERM = re.compile(r"(?:" + CYOPD + r"\s{0,5}(?:=|<>|<=|>=|<|>|=~)\s{0,5}" + CYLIT + "|" + CYOPD + r"\s{1,5}(?:starts\s{1,5}with|ends\s{1,5}with|contains)\s{1,5}" + CYLIT
                    + "|" + CYOPD + r"\s{1,5}in\s{0,5}" + CYLIST + r"|\w{1,64}(?::\w{1,64}){1,5}|" + CYOPD + r"\s{1,5}is\s{1,5}(?:not\s{1,5})?null"
                    + r"|(?:element)?id\s{0,5}\(\s{0,5}\w{1,64}\s{0,5}\)\s{0,5}=\s{0,5}" + CYLIT + r"|(?:element)?id\s{0,5}\(\s{0,5}\w{1,64}\s{0,5}\)\s{1,5}in\s{0,5}" + CYLIST + ")", re.I)
CYPAT = re.compile(r"\(\s{0,5}\w{1,64}\s{0,5}(?::\w{1,64}\s{0,5}){0,5}\)\s{0,5}<?-[-\w\[\]:>{}$|()\s]{0,200}", re.I)  # a pattern predicate: `(n)--()`, `(n)-[:R]->(:L)`; no `*`: `(n)-[*0..]-()` matches n itself
CYISN = re.compile(r"([\w.]{1,129})\s{1,5}is\s{1,5}(not\s{1,5})?null\b", re.I)


CYKEY = re.compile(r"(?:element)?id\s{0,5}\(\s{0,5}\w{1,64}\s{0,5}\)|\w{1,64}(?:\.\w{1,64}){0,3}(?::\w{1,64}){0,5}", re.I)


def _wfilter(seg):
    """Allowlist: a WHERE filters only when it has no `NOT` (except `IS NOT NULL`) and no `XOR`, and every OR branch is an AND of simple terms (`v.p OP literal|$param`, `v:Label`, `v.p IS [NOT] NULL`,
    `id(v)|elementId(v) =|IN literal|list|$param`, a pattern predicate without `*`) and no two OR branches touch the same operand (`n.a = 1 OR n.a <> 1`, `n.a IS NULL OR n.a = 1`, `n.id = 1 OR n.id = 2`
    are refused; use `IN [..]`). Other functions, constant-vs-constant terms, `id()` ranges and property-vs-property comparisons are not filters."""
    seg = re.sub(r"\s*\bdetach\s*$", "", seg, flags=re.I)
    if re.search(r"\bnot\b(?!\s+null\b)|\bxor\b", seg, re.I):
        return False
    prev = set()
    for b in CYOR.split(seg):
        ops = set()
        for t in CYAND.split(b):
            t = t.strip()
            if CYPAT.fullmatch(t) and not re.search(r"\b(?:not|xor|or|and|is|in|true|false)\b", t, re.I):
                ops.add(re.sub(r"\s+", "", t.lower()))
                continue
            t = t.strip(" \t\r\n()")
            if not CYTERM.fullmatch(t):
                return False
            ops.add(re.sub(r"\s+", "", CYKEY.match(t)[0].lower()))
        if ops & prev:
            return False
        prev |= ops
    return True


def _cypher(t):
    """Cypher that deletes every node/path: a DELETE reached after an unlabeled, unfiltered `MATCH (n)` (also `, (n)`, `p=()`, `-[r]->`), including inside `CALL {} IN TRANSACTIONS`, or an `apoc.periodic|cypher`
    call within 300 characters of a `delete`. A WHERE filters only when every `or|xor` branch names a property, label or pattern and none is a constant comparison, self-comparison, `size(`/`coalesce(` or `id(n) >= 0`
    (`WHERE n.x IS NULL OR n.x IS NOT NULL` too). Strings and `//`, `/* */` comments are removed and each `;` statement
    is read as a stream of MATCH/WHERE/DELETE keywords, so padding and a `;` in a string cannot hide the MATCH. Linear: every pattern is bounded."""
    dl = [m.start() for m in CYDEL.finditer(t)]
    if dl and any(next((d for d in dl if d >= m.end()), 1 << 30) - m.end() <= 300 for m in CYAPOC.finditer(t)):
        return True
    for st in re.sub(r"\s+", " ", CYSKIP.sub(lambda m: "''" if m[0][0] in "'\"" else " ", t)).split(";"):
        base = cur = False
        parts = CYSPLIT.split(st)
        for k in range(1, len(parts), 2):
            kw, seg = parts[k].lower(), CYEND.split(parts[k + 1], 1)[0]
            if kw == "match":
                z = parts[k] + seg
                last = max((x.end() for x in CYMATCH.finditer(z)), default=-1)  # unfiltered iff no `:Label` or `{k:` starts after the last bare pattern
                base, cur = base or cur, last >= 0 and not any(f.start() >= last for f in CYFILT.finditer(z, last))
            elif kw == "where":
                if parts[k - 1].count("(") <= parts[k - 1].count(")") and _wfilter(seg):  # a WHERE inside a call filters nothing
                    cur = False
            elif kw == "delete" and (base or cur):
                return True
    return False


SHCOMMENT = re.compile(r"""'[^']*'|"(?:[^"\\]|\\.)*"|\\.|(?<![^\s;&|()<>])#[^\n]*""", re.S)


def _nocomment(c):
    """Remove unquoted shell comments (`#` at the start of a word to end of line): `rm -rf ./build # not /` is judged without the comment. Quotes, `\\#`, `$#` and `a#b` are kept."""
    return SHCOMMENT.sub(lambda m: "" if m[0][0] == "#" else m[0], c) if "#" in c else c


def _sqlhit(t):
    """SQL DROP/TRUNCATE/DELETE-all or a Cypher delete-everything in `t`."""
    return bool(SQLDROP.search(t) or _cypher(t))


SYSTREE = ("/etc", "/usr", "/bin", "/sbin", "/lib", "/lib32", "/lib64", "/libx32", "/boot", "/dev", "/sys", "/proc", "/root", "/System", "/Library", "/private/etc")


def _findfar(x):
    """A `find` start that is the whole host or a user area: `/`, `..`, `~`, `$HOME`, `/home`, `/home/<user>`, `/var`, or anything inside `/etc`, `/usr` (not `/usr/local`), `/bin`, `/lib*`, `/boot`, `/root`, `/System`,
    `/Library`, ... (not `/var/www`, `/srv/x`, `/opt/x`, `/home/<user>/<project>`)."""
    p = posixpath.normpath(re.sub("/+", "/", x)) if x else "."
    return p in ("/", "..", "/var", "/private") or p.startswith("../..") or p in TOPDIRS or x in ("~", "$HOME", "${HOME}") or re.fullmatch(r"/(?:home|Users)/[^/]+", p) is not None \
        or (any(p == d or p.startswith(d + "/") for d in SYSTREE) and not p.startswith("/usr/local/") and p != "/usr/local")


ETCSYS = re.compile(r"/etc/(?:passwd|shadow|group|gshadow|sudoers|ssl|ld\.so|pam|fstab|host|resolv|nsswitch|login\.defs|security|systemd|init|rc|profile|environment|cron|ca-cert|alternatives|apt|dpkg|default|skel|localtime|selinux|udev|network|netplan|X11|modprobe|sysctl|mtab|issue|shells|machine-id)[^/]*(?:/|$)")  # system-owned /etc children; `/etc/myapp` is not
SYSDIRS = ("/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc", "/var")


def _frev(st, m):
    """`_revoke` for `find ... -exec chmod`: `go-rwx` of `/home` is routine hardening, so non-owner bits count only for `/` and the system directories and everything below them (`/etc/ssh`, `/etc/ssl/private` stay secret-file carve-outs)."""
    ps = [posixpath.normpath(re.sub("/+", "/", x)) for x in st]
    return _revoke(m, not any(x.startswith("..") or p == "/" or (any(p == d or p.startswith(d + "/") for d in SYSDIRS) and not re.match(r"/etc/(?:ssh|ssl/private)(?:/|$)", p) and not (p.startswith("/etc/") and not ETCSYS.match(p))) for x, p in zip(st, ps)))


def _corepkg(name, a, ph=None):
    """Removal of a core OS package (libc, systemd, kernel, dpkg, sudo, ...), a `*`/`@group` removal or a list built at run time, or `rpm -e --nodeps` of anything, via apt/dnf/yum/zypper/apk/rpm/dpkg/pacman.
    A preview (`--simulate`, `-s`, `-D`, `-p`, `--test`, `APT::Get::Simulate=true`; only true/yes/1/on/with/enable or no value counts, `=false|no|off|0` does not) or an `--installroot`/`--root` outside `/` allows it."""
    pv = rt = False  # the LAST preview switch and the LAST root option win, as in the tools
    for k, t in enumerate(a):
        b, _, v = t.partition("=")
        o = re.fullmatch(r"apt::get::(?:simulate|just-print|dry-run|no-act)(?:=(.*))?", t[2:] if t.startswith("-o") else t, re.I)
        if b in PKGDRY:
            pv = v.lower() in ("", "true", "yes", "1", "on", "with", "enable")
        elif b.startswith("--no-") and "--" + b[5:] in PKGDRY and b != "--no-act":
            pv = False
        elif b == "--setopt" and v.startswith("tsflags=") or t.startswith("--setopt=tsflags="):
            pv = "test" in t.partition("tsflags=")[2]
        elif o:
            pv = o[1] is None or o[1].lower() in ("true", "yes", "1", "on", "with", "enable")
        elif re.fullmatch(r"-[A-Za-z]+", t) and not t.startswith("-o") and any(c in t[1:] for c in PKGSHORT.get(name, "\0")) \
                and (not name.startswith("apt") or re.fullmatch(r"-[yqsdfmuVv]+", t)):  # an apt bundle with a value flag (`-tstable`, `-ca`) is no preview
            pv = True
        m = re.fullmatch(r"(?:-o)?(?:dir::)?rootdir=(.*)", t, re.I)
        rv = m[1] if m else v or (a[k + 1] if k + 1 < len(a) else "") if b in ("--installroot", "--root", "--instdir", "--sysroot", "--rootdir", PKGROOT.get(name, "\0")) else ""
        if rv and "$" not in rv:
            rt = posixpath.normpath(re.sub("/+", "/", rv)) != "/"
    if pv or rt:
        return False
    w = [t for t in a if not t.startswith("-")]
    removal = True
    if name in PKGVERB:
        if not any(re.fullmatch(PKGVERB[name], t) for t in a):
            return False
        if name == "rpm" and "--nodeps" in a:
            return True
        pk = w
    else:
        k = next((i for i, t in enumerate(w) if t in ("remove", "purge", "erase", "del", "rm", "autoremove", "autopurge", "uninstall", "groupremove", "grouperase", "swap", "install", "in", "add")), None)
        if k is None or w[k - 1:k] == ["mark"]:
            return False
        if w[k].startswith("group") or w[k - 1:k] == ["group"]:
            return True  # a whole package group
        v, pk = w[k], w[k + 1:]
        if v == "swap":
            pk = pk[:1]
        elif v in ("install", "in", "add"):  # `apt-get install libc6-` removes it; `--remove` flips install into removal; `zypper in -glibc`
            pk = [t[:-1] for t in pk if t.endswith("-")] + [t[1:] for t in a if name == "zypper" and re.fullmatch(r"-[A-Za-z]\w+", t)] + (pk if "--remove" in a else [])
            removal = False
    return (removal and (ph is not None or any(re.search(r"[$`]", t) for t in pk))) or any(
        re.fullmatch(r"\\?\*", t) or t.startswith("@") or (re.search(r"[*?\[]", t) and any(fnmatch.fnmatchcase(n, t.lower()) for n in GLOBN)) or CORE.fullmatch(t)
        or (name in ("dnf", "yum", "microdnf", "tdnf") and re.fullmatch(r"python3(?:\.\d+)?(?:[:=]\S+|-\d\S*)?", t)) for t in pk)


CRITBIN = re.compile(r"/(?:usr/)?(?:local/)?s?bin/(?:sudo|su|doas|bash|sh|dash|zsh|login|sshd|ssh|systemctl|init|mount|chmod|chown|rm|cp|mv|ls|cat|env|ln|tar|apt|apt-get|dpkg|rpm|yum|dnf|passwd|visudo|reboot|shutdown|halt|poweroff|getty|agetty)"
                     r"|/(?:usr/)?lib(?:64|32|x32)?/(?:[\w-]+-linux-gnu/)?(?:libc\.so\.6|libc-[\d.]+\.so|libm\.so\.6|libpthread\S*|ld-linux\S*|ld-\d\S*)|/(?:usr/)?lib/systemd/systemd"
                     r"|/etc/(?:passwd|shadow|group|gshadow|sudoers|fstab|hosts|resolv\.conf|nsswitch\.conf|login\.defs|ld\.so\.\S+|ssh/sshd_config|pam\.d/\S+|sudoers\.d/\S+)|/boot/(?:vmlinuz|initrd|initramfs)\S*"
                     r"|/(?:bin|sbin|lib|lib64|usr|usr/bin|usr/sbin|usr/lib|etc|boot|home|root|var|opt|srv)?")
CRITDATA = re.compile(r"/etc/(?:shadow|gshadow|sudoers(?:\.d(?:/.*)?)?|ssh/.*|ssl/private(?:/.*)?)|/root(?:/.*)?|/(?:home|Users)/[^/]+(?:/.*)?|/(?:opt|srv)(?:/.*)?|/var/.+")  # secret and user data: only losing the owner's access locks the host out, not `go-rwx` hardening; `/etc`, `/var`, `/home` and world-read system files must stay readable


def _core_bin(t):
    """A path to a binary or file whose loss locks the host out (sudo, su, shells, login, ssh, libc, systemd, pam, `/etc/passwd|shadow|sudoers`, kernel) or a top-level system directory, after normalizing."""
    return t.startswith("/") and bool(CRITBIN.fullmatch(posixpath.normpath(re.sub("/+", "/", t))))


def _revoke(m, owner=False):
    """A chmod mode that wipes everything or removes read/execute from anyone (`000`, `a-x`, `-x`, `go-rwx`); `owner` counts only a clause that touches the owner (`u-`, `a-`, bare `-`)."""
    return _wipe(m) or any(re.fullmatch(r"(?:a|[ugoa]*u[ugoa]*|)-[rwxXst]*[rxX][rwxXst]*" if owner else r"[ugoa]*-[rwxXst]*[rxX][rwxXst]*", c) is not None for c in m.split(","))


def _permissive(m):
    """A chmod mode that opens everything (`777`, `666`, `a+rwx`, `o+w`) or wipes it."""
    return _wipe(m) or re.fullmatch(r"0?(?:777|666)|(?:a|[ug]*o[ug]*)[+=][rwxXst]*w[rwxXst]*", m) is not None


def _rootlock(name, a):
    """`passwd -l|-d|-x 0`, `usermod -L|-e|-s nologin|-p '!'`, `chsh -s nologin`, `chage -E` of root (no user = root under sudo), or `sed -i` on `/etc/passwd|shadow|group|sudoers`."""
    if name in ("usermod", "chsh", "chage"):  # attached short values: `-pxx`, `-s/sbin/nologin`, `-E0`
        a = [y for t in a for y in ((t[:2], t[2:]) if re.fullmatch(r"-[pesE][^-=].*", t) else (t,))]
    w = [t for t in a if not t.startswith("-")]
    val = lambda *f: [t.partition("=")[2] if "=" in t else a[k + 1] if k + 1 < len(a) else "" for k, t in enumerate(a) if t.split("=")[0] in f]
    nologin = any(os.path.basename(v) in ("nologin", "false", "true") for v in val("-s", "--shell"))
    if name in ("sed", "perl"):
        ed = any(re.fullmatch(r"-[a-zA-Z]*i\S*|--in-place\S*", t) for t in a)
        if ed and re.search(r"PermitRootLogin", " ".join(a), re.I) and re.search(r"PasswordAuthentication", " ".join(a), re.I) and any(re.search(r"(?:^|/)sshd_config(?:\.d/[^/]+)?$", t) for t in w):
            return True  # one edit that turns off root login and password login can lock out every ssh user
        return ed and any(
            re.fullmatch(r"/etc/(?:passwd|shadow|group|gshadow|sudoers(?:\.d/.*)?|pam\.d/.*|fstab|ld\.so\.conf)", posixpath.normpath(re.sub("/+", "/", t))) for t in w if t.startswith("/"))
    if name == "passwd":
        lock = any(t in ("--lock", "--delete") or (not t.startswith("--") and (_bundle(t, "l") or _bundle(t, "d"))) for t in a)
        return (lock and (not w or "root" in w or "0" in w or any(re.search(r"[$`]", t) for t in w))) or ("root" in w and "0" in val("-x", "--maxdays"))
    return "root" in w and ((name == "usermod" and (any(t == "--lock" or _bundle(t, "L") for t in a) or any(v not in ("", "-1") for v in val("-e", "--expiredate")) or nologin
                                                    or any(not v.startswith("$") for v in val("-p", "--password"))))
                            or (name == "chsh" and nologin) or (name == "chage" and any(v not in ("", "-1", "never") for v in val("-E", "--expiredate"))))


def _ansible(a, depth):
    """Judge an ad-hoc `ansible` module call: shell/command/raw args as a command (no -m means command), file state=absent as `rm -rf PATH`. `--check` is a dry run."""
    chk = _on(a, "--check", "-C")  # raw ignores check mode, so it is still judged
    mod, args, k = "command", "", 0
    while k < len(a):
        t, k = a[k], k + 1
        if t in ("-m", "--module-name", "-a", "--args") and k < len(a):
            key, v, k = t, a[k], k + 1
        elif t.startswith(("--module-name=", "--args=")):
            key, _, v = t.partition("=")
        elif t[:2] in ("-m", "-a") and len(t) > 2:
            key, v = t[:2], t[2:]
        else:
            continue
        if key in ("-m", "--module-name"):
            mod = v
        else:
            args = v
    mod = mod.rsplit(".", 1)[-1]
    if chk and mod != "raw":
        return ""
    if mod in ("shell", "command", "raw", "win_shell", "win_command") and args:
        try:  # `cmd='rm -rf /x'`, `_raw_params=...` or a JSON object carry the command
            kv = json.loads(args) if args.lstrip().startswith("{") else dict(x.partition("=")[::2] for x in shlex.split(args))
            args = next((kv[x] for x in ("cmd", "_raw_params") if isinstance(kv, dict) and isinstance(kv.get(x), str)), args)
        except ValueError:
            pass
        return check(args, depth + 1) if depth < MAXDEPTH else "ansible command nested too deep to vet. Run one step at a time"
    if mod == "file" and args:
        try:
            kv = json.loads(args) if args.lstrip().startswith("{") else dict(x.partition("=")[::2] for x in shlex.split(args))
        except ValueError:
            return "ansible file args cannot be parsed, so a removal cannot be vetted. Use `--check` first and ask the owner"
        p = kv.get("path") or kv.get("dest") or kv.get("name") if isinstance(kv, dict) else None
        if p and kv.get("state") == "absent" and isinstance(p, str):
            return check("rm -rf " + shlex.quote(p), depth + 1)
    return ""


def _bundle(t, ch):
    return ch in t and bool(BUNDLE.fullmatch(t))


def _upbase(t):
    """`t` unchanged, or, after an unexpanded base (variable, `~`) followed by `..`, the path left once the `..` run is applied
    (an unexpanded base may land anywhere, so judge what remains); None when no `..` climbs past the base."""
    parts = t.split("/")
    v = next((i for i, x in enumerate(parts) if "$" in x or "`" in x or x.startswith("~")), None)
    if v is None:
        return t
    up, st = 0, []
    for x in parts[v + 1:]:
        if x == "..":
            up, _ = (up, st.pop()) if st else (up + 1, 0)
        elif x not in ("", "."):
            st.append(x)
    return "/" + "/".join(st) if up else None


def _kstdin(a, j):
    """`a[j]` is a kubectl `-f`/`--filename` (also bundled, `-Rf`, or `-fV`) whose manifest comes from stdin: `-`, /dev/stdin, an fd path, or nothing (`-f <(...)`)."""
    m = re.fullmatch(r"--filename(?:=(.*))?|-[A-Za-z]*?f=?(.*)", a[j])
    if not m:
        return False
    v = m[1] or m[2] or (a[j + 1] if j + 1 < len(a) else "-")
    return bool(re.fullmatch(r"-|/dev/(?:stdin|fd/\d+)|/proc/(?:self|\d+)/fd/\d+", posixpath.normpath(re.sub("/+", "/", v)) if v.startswith("/") else v))


def _blk(t):
    """A write target that is a raw disk device (`/dev/sda`, `/dev/nvme0n1`, `/dev/disk2`, ...) or live-kernel file (`/proc/sysrq-trigger`, `/proc/self/mem`)."""
    p = posixpath.normpath(re.sub("/+", "/", _upbase(t) or t))
    return bool(BLKDEV.match(p) or RAWPROC.fullmatch(p))


def _empty(seg):
    """True when the command `seg` prints nothing but blanks (`:`, `true`, `echo ""`, `printf '\\n'`): its pipe feeds an empty file."""
    return seg in EMPTYSRC or (seg[:1] in (["echo"], ["printf"]) and all(not re.sub(r"\\[ntr]|%[sb]|\s", "", t) for t in seg[1:] if not re.fullmatch(r"-[neE]+", t)))


def _cronin(a):
    """`crontab` reads its table from stdin (`-` or no file) and is not a listing/edit."""
    fl = [t for k, t in enumerate(a) if not (t.startswith("-") and t != "-") and not (k and a[k - 1] == "-u")]
    return fl in ([], ["-"]) and not any(_bundle(t, "l") or _bundle(t, "e") for t in a)


RSYNCVAL = ("--rsh", "--exclude", "--include", "--filter", "--exclude-from", "--include-from", "--files-from", "--rsync-path", "--partial-dir", "--backup-dir", "--suffix",
            "--log-file", "--temp-dir", "--compare-dest", "--copy-dest", "--link-dest", "--block-size", "--bwlimit", "--timeout", "--port", "--max-size", "--min-size",
            "--chmod", "--chown", "--remote-option", "--out-format", "--info", "--debug", "--address", "--sockopts", "--modify-window", "--read-batch", "--write-batch", "--only-write-batch")


def _rsyncopts(a):
    """rsync arguments without the values of value-taking options (`--exclude -n`, `-e ssh`): such a value is not a flag."""
    out, i = [], 0
    while i < len(a):
        out.append(a[i])
        i += 2 if a[i] in RSYNCVAL or (BUNDLE.fullmatch(a[i]) and a[i][-1] in "efTBM") else 1
    return out


def _brace(t):
    """Bash brace expansions of `t` (one comma group at a time); a long, wide or deeply multiplied brace word fails closed to `/`."""
    m = re.search(r"\{([^{}]*,[^{}]*)\}", t)
    if not m:
        return [t]
    xs = m[1].split(",")
    if len(t) > 256 or len(xs) > 16:
        return ["/"]
    r = [y for x in xs for y in _brace(t[:m.start()] + x + t[m.end():])]
    return r if len(r) <= 64 else ["/"]


def _sysw(t, app=False):
    """A write target on a system path (case-insensitive for macOS; 2+ leading `..` count as suspect; `/var/log` is exempt for appends)."""
    t = _upbase(t)
    if t is None:
        return False
    p = posixpath.normpath(re.sub("/+", "/", t) or ".")
    if p.startswith("../.."):
        p = re.sub(r"^(?:\.\./)+", "/", p + "/")
    return bool(SYSFILE.match(p)) and not (app and re.match(r"/(?:private/)?var/log(?:/|$)", p, re.I))


def _testsql(name, a):
    """`psql -h localhost -d acme_test -c 'DROP TABLE [IF EXISTS] t'`: one throwaway table in a local test/tmp database. Whitelist only: other
    options (-f, -U, URIs, port), a second statement, `\\` meta-commands and non-local hosts keep the block. ponytail: localhost can be a port-forward; a
    test/tmp database name is the second key."""
    o, j = {}, 0
    while j < len(a):
        if a[j] in ("-h", "-d", "-c") and j + 1 < len(a):
            o.setdefault(a[j], []).append(a[j + 1])
            j += 2
        elif a[j] in ("-X", "-q"):
            j += 1
        else:
            return False
    d, c = o.get("-d", [""]), o.get("-c", [""])
    return name == "psql" and o.get("-h") in (["localhost"], ["127.0.0.1"], ["::1"]) and len(d) == 1 and len(c) == 1 \
        and bool(re.fullmatch(r"(?:\w+[_-])?(?:test|tmp)", d[0])) \
        and bool(re.fullmatch(r"\s*(?:drop\s+table\s+(?:if\s+exists\s+)?|truncate\s+(?:table\s+)?)\w+(?:\.\w+)?\s*;?\s*", c[0], re.I))


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
            c = _unq((m[1] or m[2]).strip())
            r = check(c, depth + 1)
            if r:
                return r
            c = c.split()
            c = c[_unwrap(c)[0]:]  # `.shell env sh`
            if c and (os.path.basename(c[0]) in SHELLS or INTERP.match(os.path.basename(c[0]))) and all(x.startswith("-") for x in c[1:]):
                return "sqlite3 dot-command pipes into a bare shell/interpreter. Run an exact literal command"
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
    if re.fullmatch(r"\*\.[\w~-]+", t):
        return False  # `*.log` in the cwd: scoped by its extension
    if re.fullmatch(r"(?:\$env:(?:TEMP|TMP)|%(?:TEMP|TMP)%)[\\/][\w.-]+(?:[\\/][^$%]*)?", t, re.I) and ".." not in n.split("/"):
        return False  # a named child of the temp dir
    glob = re.search(r"[*?]", u) and "/" in n and not re.search(r"[*?]", n.rsplit("/", 1)[0])  # glob only in the last part of a named relative dir
    return bool(WINABS.match(t)) or bool(re.search(r"[$%]", u)) or (bool(re.search(r"[*?]", u)) and not glob) or n in (".", "..") or n.startswith(("/", "../", "~"))


def _wildsys(t):
    """`del` target that wipes a system dir: drive/%SystemRoot%/bare `Windows` + `*` or `*.*` (shlex ate the backslashes); `*.ext` is scoped."""
    return bool(re.match(r"(?i)(?:[A-Za-z]:[\\/]*|[\\/]*)(?:windows|users|program|system32|boot|recovery)|(?:%|\$env:)(?:systemroot|windir|systemdrive|programfiles\w*)%?", t)
                and re.search(r"[*?]+(?:\.[*?]+)?$", t))


SYSWIN = re.compile(r"(?i)(?:[A-Za-z]:[\\/]*|[\\/]+|(?:%|\$env:)(?:systemroot|windir|systemdrive|programfiles\w*)%?[\\/]*)"
                    r"(?:windows(?![\\/]*temp)|system32|syswow64|program|boot(?:mgr|\.ini)?(?![a-z])|ntldr|pagefile|hiberfil|recovery)")
WINDEL = re.compile(r"(?i)(?:^|[;&|\n(]|/[ck][ \t]+[\"']?)[ \t]*(?:del|erase)\b([^;&|\n]*)")


def _windel(raw):
    """`del`/`erase` read from the RAW text (shlex eats the backslashes of `..\\x`): `..` paths, a bare `*`/`*.*` in the cwd or under a
    drive/variable/`..` dir, and any file under a Windows system dir. `del /s /q *.log` and `del build\\*.*` stay allowed."""
    for m in itertools.islice(WINDEL.finditer(raw), 200):  # bounded: each match scans the prefix for quote parity
        pre = raw[:m.start()]
        if (pre.count('"') % 2 or pre.count("'") % 2) and not m[0].lstrip(";&|\n( \t").startswith("/"):
            continue  # inside a quoted mention
        for t in re.findall(r"\"[^\"]*\"|'[^']*'|\S+", m[1]):
            t = t.strip("\"'")
            if re.fullmatch(r"/[A-Za-z?]", t):
                continue
            u = t.replace("\\", "/")
            dirpart, _, last = u.rpartition("/")
            if ".." in u.split("/") or SYSWIN.match(t) or (re.fullmatch(r"\*+(?:\.\*+\w*)?", last) and (
                    not dirpart or WINABS.match(t) or u.startswith("/") or "$" in u)):
                return "del of a system file, `..` path or whole directory contents. Delete exact in-project files"
    return ""


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
    if n in ("remove-item", "ri") and not tg and not any(t.lower().startswith("-wh") and "-whatif".startswith(t.lower()) for t in a):
        return "Remove-Item fed from a pipeline cannot be vetted. Delete an exact in-project path"
    if n in ("del", "erase", "rd", "rmdir") and (any(t.lower() == "/s" for t in a) or any(re.fullmatch(r"[A-Za-z]:[\\/]*[*?.]*", t) or _wildsys(t) for t in tg)) and any(_wintarget(t) for t in tg):
        return f"{name} /s on a drive, variable, glob or system path. Delete an exact in-project path"
    if n in ("format", "format.com") and any(re.match(r"[A-Za-z]:(?:[\\/]|\s|$)", t) for t in a) or n == "diskpart":
        return f"{name} wipes a volume or disk. Do it in a VM, never on the host"
    if n == "bcdedit" and any(t.lower() in ("/delete", "/deletevalue", "/set") for t in a):
        return "bcdedit changes boot configuration. Ask the owner"
    if n == "reg" and a[:1] and (a[0].lower() in ("delete", "import", "restore") or (a[0].lower() in ("add", "copy", "save", "load", "unload") and any(
            re.match(r"(?i)(?:\\\\[^\\]+\\)?(?:HKLM|HKEY_LOCAL_MACHINE|HKCR|HKEY_CLASSES_ROOT)|(?:HKCU|HKEY_CURRENT_USER)\\*Software\\*Classes"
                     r"|(?:HKU|HKEY_USERS)\\*.{0,80}?Software\\*Classes", t) for t in a[1:]))):
        return "reg delete/import/restore or a write to HKLM changes the registry. Ask the owner"
    if n == "wmic" and (any(t in ("delete", "uninstall", "terminate") for t in map(str.lower, a)) or {"call", "format"} <= set(map(str.lower, a))
                        or {"call", "create"} <= set(map(str.lower, a)) or ("call" in map(str.lower, a) and {"reboot", "shutdown", "win32shutdown"} & set(map(str.lower, a)))):
        return "wmic delete/call create/uninstall changes system objects or runs commands. Ask the owner"
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


def _rec(t):
    """`--recursive` or a unique prefix of it (`--rec`, `--recurs`), or a bundle holding R."""
    return (t.startswith("--rec") and "--recursive".startswith(t)) or _bundle(t, "R")


def _wipe(m):
    """A chmod mode whose final state removes every permission from u, g and o: `0`-`0000`, `a=`, `u=,g=,o=`, `a-rwx`, `-rwx`, `u+r,a=`. Not `go-rwx`."""
    if re.fullmatch(r"0{1,4}", m):
        return True
    st = dict.fromkeys("ugo", False)  # True = wiped so far
    for c in m.split(","):
        x = re.fullmatch(r"([ugoa]*)([-+=])([rwxXst]*)", c)
        if not x:
            return False
        for k in ("ugo" if "a" in x[1] or not x[1] else x[1]):
            if x[2] == "=":
                st[k] = not x[3]
            elif x[2] == "+":
                st[k] = st[k] and not x[3]
            elif all(ch in x[3] for ch in "rwx"):
                st[k] = True
    return all(st.values())


CHMOD_TGT = frozenset(("$", ".", "*", ".*", "$PWD", "${PWD}", "$(pwd)", "`pwd`"))


def _chmod000(a):
    """`chmod -R <mode that wipes every permission>` aimed at an absolute, home, `.`, glob, `$PWD` or `..` path."""
    pos, k = [], 0
    while k < len(a):
        t = a[k]
        k += 1
        if t == "--":
            pos += a[k:]
            break
        if not t.startswith("--") and t.startswith("-") and _revoke(t) or not t.startswith("-"):
            pos.append(t)  # a mode may start with `-`
    rv = lambda m, p: _revoke(m, bool(CRITDATA.fullmatch(p))) and not (p in ("/home", "/Users") and all(re.fullmatch(r"o-[rwxXst]*", c) for c in m.split(",")))  # `o-rwx /home` is hardening
    if any(_core_bin(t) and any(rv(m, posixpath.normpath(re.sub("/+", "/", t))) for m in pos if m is not t) for t in pos if not _revoke(t)):
        return True  # one critical binary or system directory needs no -R; a data path (`/etc/*`, `/root`, `/home`) only when the owner loses access
    modes = [t for t in pos if _wipe(t)]
    return bool(modes) and any(_rec(t) for t in a) and any(
        (t.startswith(("/", "~")) and not _scoped(t)) or posixpath.normpath(t) in CHMOD_TGT or t.rstrip("/") == "./*" or ".." in t.split("/")
        for t in pos if t not in modes)


def _launchctl(a, depth):
    """Reason string for a launchctl call that stops or removes a system-domain service, else ''."""
    b = []
    for t in a:  # split a glued `-w/Library/...` or `-Dsystem`
        m = re.fullmatch(r"(-[A-Za-z]*w)(/.*)", t) or re.fullmatch(r"(-D)(\w+)", t)
        b += list(m.groups()) if m else [t]
    w = [t for t in b if not t.startswith("-")]
    dom = [x.casefold() for k, t in enumerate(b) for x in ([b[k + 1]] if t == "-D" and k + 1 < len(b) else [])]
    if w[:1] == ["asuser"] and len(w) > 2:
        rest = a[a.index(w[2]):]
        return _inner(rest, depth)
    if w[:1] == ["submit"] and "--" in a:
        return _inner(a[a.index("--") + 1:], depth)
    uid = r"(?:\d+|\$[^/]*)"  # a number or any expansion: `gui/$UID`, `gui/$(id -u)`
    if w[:1] in (["bootout"], ["disable"]) and any(re.match(r"system(?:/|$)", t) for t in w[1:]) \
            or w[:1] == ["bootout"] and any(re.fullmatch(r"(?:gui|user)/" + uid + "/?", t) for t in w[1:]) \
            or w[:1] == ["remove"] \
            or w[:1] == ["unload"] and any(_bundle(t, "w") for t in b) and any(
                re.match(r"/(?:system/)?library/launchdaemons/", posixpath.normpath(re.sub("/+", "/", t)).casefold()) for t in w[1:]) \
            or w[:1] in (["unload"], ["load"]) and any(d in ("system", "all") for d in dom):
        return "launchctl bootout/unload -w/remove/disable of a system daemon stops it and can persist the change. Ask the owner"
    return ""


CRIT = ("ssh", "sshd", "network", "networking", "networkmanager", "network-manager", "network-online", "network-pre", "systemd-networkd", "systemd-resolved", "systemd-logind",
        "systemd-journald", "systemd-udevd", "systemd-machined", "systemd-homed", "systemd-hostnamed", "docker", "containerd", "dbus", "dbus-broker", "dbus-daemon",
        "firewalld", "ufw", "kubelet", "k3s", "k3s-agent", "libvirtd", "tailscaled", "nftables", "iptables", "wpa_supplicant", "wg-quick", "amazon-ssm-agent")
SVAL = frozenset(("-t", "--type", "-H", "--host", "-M", "--machine", "-p", "--property", "-n", "--lines", "-s", "--signal", "--root", "-o", "--output", "-a"))  # value-taking systemctl options


def _critunit(t):
    """True when systemd unit `t` (path, instance, suffix and case ignored, globs matched) is one that keeps the host reachable."""
    n = re.sub(r"(?:@[^.]*)?(?:\.(?:service|socket|target|mount|timer|path|slice|scope|device))?$", "", posixpath.basename(t).lower())
    return any(fnmatch.fnmatchcase(c, n) for c in CRIT) if re.search(r"[*?\[]", n) else n in CRIT


HELMV = frozenset(("history", "list", "ls", "get", "install", "upgrade", "status", "show", "template", "search", "repo", "plugin", "pull", "push", "package", "lint",
                   "create", "dependency", "dep", "diff", "env", "test", "verify", "version", "uninstall", "registry", "help", "completion", "login", "logout", "fetch"))
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


def _sens(t):
    """A private-key or credential file (by basename) or a dotfile under `~/.ssh|.aws|.gnupg|...`."""
    return bool(HOMEP.search(t) or re.search(r"(?:^|/)\.(?:docker|kube)(?:/|$)|(?:^|/)\.config/(?:gcloud|gh)(?:/|$)", t) or SENS.fullmatch(posixpath.basename(t.rstrip("/"))))


def _db(t):
    """A database file or server data dir that is not scratch (temp dir, build/cache output)."""
    return bool(DBFILE.search(t)) and not _scoped(t) and not SCRATCHDIR.search(t)


def _trunc(t):
    """A file whose truncation is unrecoverable: private key, credential file or database."""
    return _sens(t) or _db(t)


def _cred(t):
    """A credential file `rm` must not delete: cloud/registry/gpg configs, `.netrc`, `.envrc`, `.git-credentials`, service-account JSON, private keys."""
    return bool(CREDDIR.search(t) or CREDBASE.fullmatch(posixpath.basename(t.rstrip("/"))))


def _data(cmd):
    """Blank the quoted payload of gh/glab body/title and git commit message flags so raw-text scans do not read prose as commands."""
    if len(cmd) >= 20000 or not re.search(r"\b(?:gh|glab|git)\b", cmd):
        return cmd
    for _ in range(16):
        new = DATAFLAG.sub(r"\1x", cmd)
        if new == cmd:
            break
        cmd = new
    return cmd


def _rel(x):
    """A relative path with no variable, glob or `..`: inside the working tree."""
    return not (x.startswith(("/", "~", "-")) or re.search(r"[$`*?\[{]", x) or ".." in x.split("/"))


def _narrow(r):
    """True if `r` is an action (-delete|-exec|-execdir), optionally after `-type d` / `-prune`, or literal `-not|!` `-path|-name|-iname` exclusions
    (each with a word character, no `$`) followed by `-delete` only: the exclusions just narrow a `-delete`, they never open `-exec` or `-quit` combinations."""
    while r[:2] == ["-type", "d"] or r[:1] == ["-prune"]:
        r = r[2:] if r[:1] == ["-type"] else r[1:]
    if r[:1] in (["-delete"], ["-exec"], ["-execdir"]):
        return True
    while r[:1] in (["-not"], ["!"]) and r[1:2] in (["-path"], ["-name"], ["-iname"]) and len(r) > 2 and re.search(r"\w", r[2]) and not re.search(r"[$`]", r[2]):
        r = r[3:]
    return r[:1] == ["-delete"]


SYSROOT = re.compile(r"/(?:private/)?(?:(?:etc|usr|bin|sbin|boot|lib|lib64|var|opt|srv|root|home|dev|proc|sys|System|Library|Users|Applications)?|\*)(?:/\*)?", re.I)


def _mvsys(t):
    """A mv operand that is a system root, `/*`, a subpath of /usr or /System, or an absolute path whose first component is a glob or a variable/quote concat."""
    if t.startswith("-"):
        return False
    if not t.startswith("/"):  # `~/../../etc`, `$HOME/../..`: the `..` run climbs out of the unexpanded base
        t = ".." in t.split("/") and _upbase(t) or t
    if not t.startswith("/"):
        return False
    p = posixpath.normpath(re.sub("/+", "/", t))
    return bool(SYSROOT.fullmatch(p) or re.match(r"/(?:usr|System)/", p, re.I) or re.search(r"[*?\[$`{]", p.split("/")[1] if p.count("/") else ""))


def _shred_ok(a):
    """True when every file `shred` is given is inside a named child of $TMPDIR or /tmp (values of -n/-s are not files)."""
    tg, i = [], 0
    while i < len(a):
        t = a[i]
        i += 1
        if t == "--":
            tg += a[i:]
            break
        if t in ("--iterations", "--size", "--random-source") or (BUNDLE.fullmatch(t) and t[-1] in "nsS"):
            i += 1
        elif not t.startswith("-"):
            tg.append(t)
    return bool(tg) and all(_scoped(t) for t in tg)


def _sqlfile(p):
    """`psql < FILE`: scan FILE when it is a regular file (first 256 KB; read-only), else judge its name."""
    why = SQLWHY
    if not os.path.isfile(p):
        return why if re.search(r"(?i)drop|truncate|destroy|purge|wipe|nuke", os.path.basename(p)) else ""
    try:
        with open(p, errors="replace") as f:
            return why if _sqlhit(SQLCOMMENT.sub(" ", f.read(1 << 18))) else ""
    except OSError:
        return ""


def _rm(args, ph, moved=False):
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
    if any(_cred(t) and not _scoped(t) for t in tg):
        return "rm of a credential or key file (cloud CLI config, .netrc, .envrc, service-account JSON, private key). Move it aside (`mv f f.bak`) and ask the owner"
    if not rec:
        return ""
    if not tg and ph:
        return "rm -r with targets from xargs. List them first (`ls`), then `rm` the exact paths"
    for t in tg:
        if not moved:  # after a cd/pushd/popd `$PWD` is somewhere else
            t = PWDP.sub(lambda m: "" if _rel(t[m.end():]) else m[0], t, 1)  # `$PWD/build` is `build`
        n = posixpath.normpath(re.sub("/+", "/", t) or ".")
        if _scoped(t) and not (ph and any(p in t for p in ph if p)):
            continue
        if posixpath.basename(n) == ".git" or re.search(r"(?:^|/)\.git/(?:\*|objects|refs)", n):
            return "rm -r of .git destroys the repository history. Use `git clean`/`git worktree remove`, or ask the owner"
        if re.search(r"[$`*?\[]|\{[^}]*(?:,|\.\.)", t) or (ph and any(p in t for p in ph if p)) or n == "." or _far(t) \
                or n.startswith("..") or (n.startswith("/") and _sysw(n)) or re.match(r"/(Users|home|usr|etc|var|opt|root|srv|mnt|media|Volumes|private/etc)/", n) or (
                    re.match(r"/private/(?:etc|var|root|usr|opt|home|Users)/", n) and not re.match(r"/private/var/(?:folders|tmp)/", n)):
            return f"rm -r on `{t}` (variable, glob, placeholder, `.`, `..`, root, home or system path). Delete an exact, quoted in-project path, or use a container/VM"
    return ""


GITCFG = re.compile(r"(?i)alias\.\S+|core\.(?:sshcommand|pager|editor|fsmonitor|askpass|gitproxy)|sequence\.editor|gpg\.(?:\w+\.)?program|credential\.(?:\S+\.)?helper|diff\.external|pager\.\S+"
                    r"|(?:diff|merge|filter|difftool|mergetool)\.\S+\.(?:command|cmd|textconv|driver|clean|smudge|process|path)")


def _gitcfg(kv, depth=1):
    """`key=value` of a git setting that git runs as a command (alias, core.sshCommand, pager, editor, filter, ...): the value is checked."""
    k, _, v = kv.partition("=")
    if re.fullmatch(r"(?i)core\.hookspath|include(?:if\.\S+)?\.path", k) and re.match(r"[/~$]|.*\.\.", v):
        return "git config of hooksPath/include.path outside the repo plants code git runs later. Use a path inside the repo"
    if not GITCFG.fullmatch(k):
        return ""
    return check(v[1:] if v.startswith("!") else v if not k.lower().startswith("alias.") else "git " + v, depth)


def _git(a, cwd="", genv=False):
    i, gcv, away = 0, [], False  # away: -C/--git-dir/--work-tree retarget the repo  # gcv: `-c gc.reflogExpire[Unreachable]=V` values
    while i < len(a) and a[i].startswith("-"):
        if a[i] == "-c" and i + 1 < len(a) and re.match(r"(?i)gc\.(?:\S+\.)?reflogexpire(?:unreachable)?=", a[i + 1]):
            gcv.append(a[i + 1].split("=", 1)[1])
        r = _gitcfg(a[i + 1]) if a[i] == "-c" and i + 1 < len(a) else ""
        if r:  # a config value that git runs as a command
            return r
        away = away or a[i] in ("-C", "--git-dir", "--work-tree") or a[i].startswith(("--git-dir=", "--work-tree="))
        i += 2 if a[i] in GIT_OPT_VAL else 1
    if i >= len(a):
        return ""
    sub, r = a[i], a[i + 1:]
    if r[:1] in (["--help"], ["-h"]):
        return ""  # prints usage and exits
    if sub == "config":
        for j, t in enumerate(r[:-1]):
            c = _gitcfg(t + "=" + r[j + 1]) if "=" not in t else _gitcfg(t)
            if c:
                return c
    if sub == "update-ref" and any(t == "--delete" or _bundle(t, "d") for t in r):
        return "git update-ref -d deletes a ref (branch, tag) without any safety check. Use `git branch -d` or ask the owner"
    longs = [t.split("=")[0] for t in r if t.startswith("--") and len(t) > 2]

    def has(full):  # unique-prefix long option (>= 4 chars, e.g. --ha, --mir, --forc)
        return any(len(x) >= 4 and full.startswith(x) for x in longs)
    leased = [t.split("=", 1)[1].split(":")[0] for t in r if t.startswith("--force-with-lease=")]  # `--force-with-lease=REF:EXPECT`
    flags = [t for t in r if re.fullmatch(r"-[A-Za-z]+", t)]
    force = has("--force") or any("f" in t for t in flags)
    dele = has("--delete") or any("d" in t for t in flags)
    if sub == "filter-repo" and any(t in ("--analyze", "--dry-run") and not (k and r[k - 1].startswith("-") and "=" not in r[k - 1] and r[k - 1] not in FRBOOL) for k, t in enumerate(r)):
        return ""  # analysis report or preview only
    if sub in ("filter-branch", "filter-repo"):
        return "git filter-branch/filter-repo rewrites the whole history. Work on a fresh clone and ask the owner"
    if sub == "push" and has("--dry-run"):
        return ""
    if sub == "reset" and has("--hard"):
        return "git reset --hard discards work. Use `git stash` or `git reset --soft`/`--mixed`"
    cp, k = [], 0  # `git clean -fdx ./build`: only named paths under the current dir are removed; -e/--exclude take a pattern, not a path
    while k < len(r):
        t = r[k]
        k += 1 if not ((re.fullmatch(r"-[A-Za-z]*e", t) or (len(t) >= 4 and "--exclude".startswith(t))) and k < len(r)) else 2
        if not t.startswith("-") and t != "--":
            cp.append(t)
    if sub == "clean" and (force or any(x.startswith("--f") for x in longs)) and not (has("--dry-run") or any("n" in t for t in flags)) \
            and not (cp and not away and not genv and not cwd and all(_rel(x) and not x.startswith(":") and ".git" not in x.split("/") and posixpath.normpath(x) != "." for x in cp)):
        return "git clean -f deletes untracked files. Preview with `git clean -n`, delete exact paths"
    if sub == "push" and (has("--force-with-lease") or has("--force-if-includes")):  # a lease still overwrites the remote ref when it matches: only a named non-shared branch is exempt
        refs = [t.rpartition(":")[2].removeprefix("refs/heads/").lstrip("+") for t in [x for x in r if not x.startswith("-")][1:] + leased]
        if any(SHARED.fullmatch(x) or re.search(r"[$`]", x) for x in refs):  # a bare push, HEAD, --all and --tags resolve at run time and stay allowed
            return "force push (even --force-with-lease/--force-if-includes) to a shared or computed branch overwrites shared history. Use a new commit, or ask the owner first"
    wtp = [t for t in r if not t.startswith("-")][1:]  # `worktree remove [-f] PATH`
    if sub == "worktree" and "remove" in r and force and not (
            not away and not genv and len(wtp) == 1 and r.count("--force") + sum(t.count("f") for t in flags) == 1 and _clean_wt(wtp[0], cwd)):
        return "git worktree remove --force deletes uncommitted work. Check `git -C <path> status` and remove without --force"
    if sub == "push" and (force or dele or has("--mirror") or any(
            not t.startswith("-") and (t.startswith(("+", ":")) or ":+" in t or "*" in t) for t in r)):
        return "force/delete/mirror push rewrites shared history. Use a new commit instead, or ask the owner"
    if sub in ("checkout", "switch") and (force or has("--discard-changes")):
        return "git checkout/switch -f discards uncommitted changes. Use `git stash` or name the exact file"
    if sub in ("checkout", "restore") and any(_tree(t) for t in r if not t.startswith("-")) \
            and not (sub == "restore" and (has("--staged") or any("S" in t for t in flags))
                     and not (has("--worktree") or any("W" in t for t in flags))):
        return "whole-tree git checkout/restore discards uncommitted changes. Use `git stash` or name the exact file"
    if sub == "branch" and (any(_bundle(t, "D") for t in r) or (force and dele)) and not (
            not away and not genv and _pushed([t for t in r if not t.startswith("-")], cwd)):
        return "git branch -D deletes an unmerged branch. Use `git branch -d` (refuses if unmerged)"
    ev = [t.split("=", 1)[1] for t in r if t.startswith("--expire") and "=" in t] + [y for x, y in zip(r, r[1:]) if x in ("--expire", "--expire-unreachable")] + gcv
    pv = [t.split("=", 1)[1] for t in r if t.startswith("--prune=")] + [y for x, y in zip(r, r[1:]) if x == "--prune"]
    if (sub == "reflog" and ("delete" in r or "expire" in r and any(re.fullmatch(r"now|all|0|-\d\S*|\d+(?:\.(?:second|minute|hour)s?(?:\.ago)?)?", v) for v in ev))) \
            or (sub == "gc" and any(v in ("now", "all") for v in pv)) or (sub == "prune" and "now" in r):
        return "git reflog expire/gc --prune=now makes lost commits unrecoverable. Ask the owner"
    if sub == "stash" and any(t in ("clear", "drop") for t in r) and not (r[:1] == ["drop"] and len(r) == 2 and re.fullmatch(r"stash@\{\d+\}", r[1])):
        return "git stash clear/drop loses stashed work. Use `git stash list`/`apply` and keep it"
    return ""


def _pk_ok(a):
    """`pkill -V|--version|--help` alone, or `pkill [-SIG] -P <pid>`: a version probe, or the children of one literal PID this session owns (see `_own_pid`; no pattern)."""
    if a in (["-V"], ["--version"], ["-h"], ["--help"]):
        return True
    if "-P" not in a:
        return False
    i = a.index("-P")
    rest = a[:i] + a[i + 2:]
    return a[i + 1:i + 2] != [] and a[i + 1].isdigit() and _own_pid(int(a[i + 1])) and all(re.fullmatch(r"-(?:[A-Z]+|\d+)", t) for t in rest)


def _late():
    """True once this hook has run `_BUDGET` seconds: the host's hook timeout fails OPEN, so the helpers below give up (deny) first."""
    return time.monotonic() - _T0 > _BUDGET


def _ppid(n):
    """`(parent pid, command name)` of `n` via read-only `ps`, or None."""
    if _late():
        return None
    try:
        a, _, b = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(n)], capture_output=True, text=True, timeout=2).stdout.strip().partition(" ")
        return int(a), b.strip()
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def _own_pid(n):
    """True when pid `n` descends from the nearest `claude` ancestor of this hook (this session's process tree, not the terminal's or other sessions') and is not one of the hook's own ancestors; any doubt, including no `claude` ancestor, is False."""
    mine, p = set(), os.getpid()
    for _ in range(32):
        r = _ppid(p)
        if not r or r[0] <= 1:
            return False
        p = r[0]
        mine.add(p)
        c = _ppid(p)
        if c and "claude" in os.path.basename(c[1]):
            break
    else:
        return False
    if n <= 1 or n in mine or n == os.getpid():
        return False
    for _ in range(32):
        r = _ppid(n)
        if not r or r[0] <= 1:
            return False
        n = r[0]
        if n == p:
            return True
    return False


STDIN_IDX = r"(?:\[(?:'[\w-]*'|\"[\w-]*\"|\d+)\])*"
STDIN_LOAD = r"json\.loads?\(sys\.stdin(?:\.read\(\))?\)"
JSONONLY = re.compile(rf"\s*import (?:json,\s*sys|sys,\s*json)\s*;\s*(?:print\({STDIN_LOAD}{STDIN_IDX}\)|d\s*=\s*{STDIN_LOAD}\s*;\s*print\(d{STDIN_IDX}\))\s*")


JSONPIPE = ". Allowed pipes: `python3 -m json.tool [--indent N] [--sort-keys] [--compact]` and `python3 -c 'import json,sys; print(json.load(sys.stdin)[\"key\"])'` (json-only code)"


def _stdin_data(name, a):
    """ALLOWLIST: piped fetch into an interpreter is data only for `python3 -m json.tool [--indent N] [--sort-keys] [--compact]` or `python3 [-I|-B|-s|-S|-u|-q]... -c CODE` where CODE is json-only (`json.load(sys.stdin)` / `json.loads(sys.stdin.read())`, optionally `d=...;`, then `print` of it or of `d` with literal indexing). Every other interpreter, flag or script stays denied (a denylist of code-running calls cannot be complete)."""
    if re.fullmatch(r"python[\d.]*", name) is None:
        return False
    while a and a[0] in ("-I", "-B", "-s", "-S", "-u", "-q"):
        a = a[1:]
    if a[:2] == ["-m", "json.tool"]:  # `python3 -m json.tool [--indent N] [--sort-keys] [--compact]`, stdin only
        o = a[2:]
        while o and (o[0] in ("--sort-keys", "--compact") or (o[0] == "--indent" and o[1:2] and o[1].isdigit())):
            o = o[2:] if o[0] == "--indent" else o[1:]
        return not o
    return len(a) == 2 and a[0] == "-c" and JSONONLY.fullmatch(a[1]) is not None


def _clean_wt(path, cwd):
    """True when the linked worktree at literal `path` has no modified or untracked files (read-only `git status`); any doubt is False."""
    if not path or re.search(r"[$`*?\[~{]", path) or "$" in cwd or cwd.startswith("~"):
        return False
    d = path if path.startswith("/") else os.path.join(cwd or os.getcwd(), path)
    return _gq(d, "status", "--porcelain") == ""


def _gq(d, *args):
    """Output of a read-only `git -C d ...` query, or None on any failure."""
    if _late():
        return None
    try:
        p = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True, timeout=2)
    except (OSError, subprocess.SubprocessError):
        return None
    return p.stdout.strip() if p.returncode == 0 else None


def _pushed(names, cwd):
    """True when every literal branch in `names` exists and its tip is already on a remote-tracking ref or in HEAD, so `branch -D` loses no commit."""
    d = cwd if cwd.startswith("/") else os.getcwd()
    if not names or len(names) > 3 or "$" in cwd or any(not re.fullmatch(r"[\w][\w./+@-]*", n) for n in names):
        return False
    for n in names:
        tip = _gq(d, "rev-parse", "--verify", "-q", "refs/heads/" + n)
        if not tip or (not _gq(d, "branch", "-r", "--contains", tip) and _gq(d, "merge-base", "--is-ancestor", tip, "HEAD") is None):
            return False
    return True


def _strip_triple(t):
    """Blank each real triple-quoted string literal, found by parsing `t` as Python (a `'''` inside another string is not one); unparsable text is left whole."""
    try:
        nodes = [n for n in ast.walk(ast.parse(t)) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    except (SyntaxError, ValueError, RecursionError):
        return t
    for seg in {ast.get_source_segment(t, n) or "" for n in nodes}:
        if seg[:3] in ("'''", '"""') or seg[1:4] in ("'''", '"""') and seg[:1].isalpha():
            t = t.replace(seg, " ")
    return t


def _body(t):
    """Interpreter/awk one-liner or fed text: deletes a non-literal path, or system() on a non-literal command."""
    if not RUNSTR.search(t):
        t = _strip_triple(t)
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


def _cmd(name, a, ph, depth=0, cwd="", genv=False):
    if name in ("k3s", "microk8s", "minikube") and a[:1] == ["kubectl"]:  # `minikube kubectl -- delete ...`
        name, a = "kubectl", [t for k, t in enumerate(a[1:]) if not (k == 0 and t == "--")]
    elif name == "oc":
        name = "kubectl"
    strict = name in ("rm", "chmod", "chown", "dd", "shred", "diskutil") or name.startswith("mkfs")  # a lone --help only
    hl = [t for t in a if t in ("--help", "-help", "-h")]  # usage only when it is the sole flag: `terraform destroy -h`, never beside other flags, paths or payloads
    rest = [t for t in a if t not in hl]
    if len(hl) == 1 and (not rest or (not strict and len(rest) <= (1 if hl[0] == "-h" else 3) and all(re.fullmatch(r"[a-z][a-z-]*", t) for t in rest))) \
            and not (hl[0] == "-h" and name in ("shutdown", "reboot", "halt", "poweroff", "systemctl", "rsync", "ls", "df", "du", "sort", "psql", "mysql", "ssh", "redis-cli", "mongo", "mongosh")) \
            and not (name in SHELLS + AWK + ("ssh", "eval", "su", "git") or INTERP.match(name)):
        return ""  # prints usage and exits
    r = _win(name, a, depth)
    if r:
        return r
    dr = [t for t in a if re.match(r"--(?:no-)?dry-?run", t)]
    if name in ("aws", "kubectl", "helm") and dr and all(t in DRY for t in dr) and dr[-1] in DRY:
        return ""  # any `--no-dry-run` or `--dry-run=none` among them means the command really runs
    if name in ("rm", "unlink"):
        return _rm(a, ph, bool(cwd))
    if name == "git":
        return _git(a, cwd, genv)
    if name == "find":
        k = 0
        while k < len(a) and (a[k] in ("-H", "-L", "-P", "-D") or re.fullmatch(r"-O\d", a[k])):
            k += 2 if a[k] == "-D" else 1
        st = []
        while k < len(a) and not a[k].startswith(("-", "(", "!")):
            st.append(a[k])
            k += 1
        sc = bool(st) and all(_scoped(x) for x in st)  # scratch space: deleting there is fine, other -exec bodies still run through check
        kk = k
        while "-delete" not in a and a[kk:kk + 1] in (["-type"], ["-maxdepth"], ["-mindepth"]) and a[kk + 1:kk + 2] and not re.search(r"[$`]", a[kk + 1]):  # `-type f` / `-maxdepth 2` before the name narrow an `-exec rm` (a `-delete` keeps the name-first rule)
            kk += 2
        ext = a[kk:kk + 1] in (["-name"], ["-iname"]) and bool(ARTGLOB.fullmatch(a[kk + 1] if kk + 1 < len(a) else "")) \
            and _narrow(a[kk + 2:])  # build-artifact glob, optionally narrowed by -not/! -path|-name exclusions
        # the cwd-tree exemption needs ONE action, no alternatives, no symlink following and no earlier cd out of the tree
        one = len([t for t in a[k:] if t in ("-delete", "-exec", "-execdir", "-ok", "-okdir")]) == 1 \
            and not any(x in ("-o", "-or", ",", "(", "\\(") for x in a[k:]) and not any(x in ("-L", "-H") for x in a[:k]) and "-follow" not in a \
            and (not cwd or _scoped(cwd))
        tree = one and all(_rel(x) or (ext and x in ("$TMPDIR", "${TMPDIR}", "/tmp")) for x in st or ["."]) and (
            ext or all(posixpath.normpath(x) != "." for x in st or ["."]))  # inside a named child of the cwd, or `.` with an artifact glob
        if "-delete" in a and not (sc or tree):
            return "find -delete. List with `find ... -print` first, then remove exact paths"
        for j, t in enumerate(a[:-1]):
            if t in ("-exec", "-execdir", "-ok", "-okdir"):
                k = next((m for m in range(j + 1, len(a)) if a[m] in (";", "+", "\x01")), len(a))
                sub = a[j + 1:k]
                u = _unwrap(sub)[0]  # sudo/env/nice rm
                simple = sub[u:u + 1] == ["rm"] and sub[-1:] == ["{}"] and all(x.startswith("-") for x in sub[u + 1:-1])
                if u < len(sub) and os.path.basename(sub[u]) in ("rm", "shred") and not (sc or (tree and simple)):
                    return "find -exec rm. List with `find ... -print` first, then remove exact paths"
                bn = os.path.basename(sub[u]) if u < len(sub) else ""
                if any(_findfar(x) for x in st) and (bn in ("chown", "chgrp", "setfacl", "chattr") or (bn == "chmod" and any(_permissive(x) or _frev(st, x) for x in sub[u + 1:]))
                                                                                              or (bn in SHELLS and any(re.search(r"\b(?:chown|chgrp|setfacl|chattr)\b", x) for x in sub[u + 1:]))):
                    return "find -exec chown/chgrp/setfacl/chattr (or a permissive chmod) over root or /home rewrites the host. Target an exact in-project path"
                r = check(" ".join(shlex.quote(x) for x in sub), depth + 1)
                if r:
                    return r
    if name == "tee" and any(not t.startswith("-") and (_sysw(t, any(x == "--append" or _bundle(x, "a") for x in a)) or _blk(t)) for t in a):
        return "tee writes a system file. Edit a copy and ask the owner"
    if name in ("cp", "mv", "install") and any(t in ("/dev/null", "/dev/zero") for t in a[:-1]) and _trunc(a[-1] if a else ""):
        return f"{name} of /dev/null onto a key/credential file empties it. Back it up and ask the owner"
    if name == "dd" and any(t.startswith("of=") and _trunc(t[3:]) for t in a):
        return "dd onto a key/credential file overwrites it. Back it up and ask the owner"
    if name == "mv" and any(_mvsys(x) for t in a for x in _brace(t)):
        return "mv of a system directory (or /) breaks the host. Ask the owner"
    if name == "mv" and a[-1:] == ["/dev/null"]:
        return "mv to /dev/null destroys the source. Use `rm` on an exact path if you mean it"
    if name in ("curl", "wget") and any(re.fullmatch(r"-X\s*DELETE|--request[= ]DELETE|--method=DELETE", t, re.I) or (
            t.upper() == "DELETE" and k and a[k - 1] in ("-X", "--request", "--method")) for k, t in enumerate(a)):
        return "HTTP DELETE to a remote API is hard to undo. Ask the owner"
    if name == "dd" and any(t.startswith("of=") and (_blk(t[3:]) or (lambda p: p.startswith("/dev/") and p not in SAFE_DEV)(
            posixpath.normpath(re.sub("/+", "/", t[3:]) or "."))) for t in a):
        return "dd to a device. Write to a file image, or do it in a VM"
    pos = [t for t in a if not t.startswith("-")]  # ponytail: a relative *.img/*.raw file is not a device; a symlink planted by an earlier command is out of sight
    if name.startswith("mkfs") and not _mkfs_dry(name, a) and not (pos and all(IMGFILE.fullmatch(t) and not os.path.realpath(t).startswith("/dev/") for t in pos)):
        return "mkfs formats a device. Do it in a VM, never on the host"
    if name in ("chmod", "chown", "chgrp", "setfacl", "chattr") and any(_rec(t) for t in a) \
            and any(_far(t) for t in a if not t.startswith("-")):
        return f"{name} -R on root/home. Target an exact in-project path"
    if name == "chmod" and _chmod000(a):
        return "chmod -R 000 on an absolute, home, `.`, glob or `..` path locks everyone out of the tree. Target an exact in-project path"
    if name in ("pkill", "killall") and not _pk_ok(a):
        return f"{name} kills by pattern. Use `kill` on the exact PID you started"
    sig0 = a[1:] if a[:1] == ["-0"] else a[2:] if a[:2] == ["-s", "0"] else None  # signal 0 probes, sends nothing
    tgt = sig0[1:] if sig0 and sig0[0] == "--" else sig0
    # ponytail: exempt one non-option target only; `kill -0 $S` with S="-9 1" still word-splits into a signal
    # whitelist one PID-shaped target (digits, $VAR, ${VAR}, a quoted "$(...)"); braces, globs, an unquoted `$(`
    # (the segment ends at `(`, token "$") or a second word could expand into an option, so they stay denied
    probe = tgt is not None and len(tgt) == 1 and bool(PROBE_PID.fullmatch(tgt[0]))
    if name == "kill" and not probe \
            and any(re.search(r"[$`]|pgrep|pidof", t) for t in a):
        return "kill by pattern/substitution. Use `kill` on the exact PID you started"
    if name in ("curl", "wget") and any(re.match(r"https?://\S*\?\S*\$\{?\w*(?:SECRET|TOKEN|PASSW|API_?KEY|PRIVATE)", t, re.I) for t in a):
        return "secret variable in a URL query string leaves the host. Send it in an Authorization header to a host you trust"
    w = [t for t in a if not t.startswith("-")]  # positional words; option values may leak in, which only widens a match
    gv = AWSVAL if name == "aws" else HGVAL if name == "hg" else ()
    if gv:  # global options with a value precede the verb
        w = [t for k, t in enumerate(a) if not t.startswith("-") and not (k and a[k - 1] in gv)]
    if name in ("npx", "bunx", "pnpx") or (name in ("pnpm", "npm", "yarn") and any(t in ("dlx", "exec", "x") for t in w[:1])) or name == "yarn":
        for k in range(min(len(w), 4)):  # the tool may follow `-p pkg`: try the first few suffixes
            r = check(" ".join(shlex.quote(x) for x in w[k:]), depth + 1)
            if r:
                return r
    pair = lambda *x: any(w[k:k + len(x)] == list(x) for k in range(len(w)))
    if name in ("gh", "glab") and (w[1:2] == ["delete"] or (w[:1] == ["api"] and any(
            re.fullmatch(r"(?:-X|--method)?=?DELETE", t, re.I) or (t.upper() == "DELETE" and k and a[k - 1] in ("-X", "--method"))
            for k, t in enumerate(a)))):
        return f"{name} delete is irreversible on the remote. Ask the owner"
    if name == "vault" and (w[:2] in (["kv", "destroy"], ["kv", "delete"], ["secrets", "disable"], ["auth", "disable"]) or w[:1] == ["delete"]
                            or w[:3] == ["kv", "metadata", "delete"] or w[:2] in (["operator", "seal"], ["operator", "rekey"], ["lease", "revoke"], ["token", "revoke"], ["policy", "delete"], ["namespace", "delete"])):
        return "vault kv destroy/metadata delete, lease/token revoke or policy delete is hard to undo. Ask the owner"
    if name in ("dropdb", "dropuser", "pg_dropcluster") or (name == "mysqladmin" and "drop" in w):
        return f"{name} drops a database or role. Ask the owner"
    if name in ("mongo", "mongosh") and any(re.search(r"\.drop\s*\(|delete(?:Many|One)\b|findOneAndDelete\s*\(|\.remove\s*\(|\.dropIndex(?:es)?\s*\(", t) for t in a):
        return "mongo drop/deleteMany removes documents or collections. Ask the owner"
    tdir = lambda x: len(x) > 3 and "--target-directory".startswith(x.split("=")[0])  # getopt long-option prefixes
    dest = [y for x in a[-1:] + [x for j, x in enumerate(a) if j and (a[j - 1] == "-t" or (tdir(a[j - 1]) and "=" not in a[j - 1]))]
            + [x.split("=", 1)[1] for x in a if x.startswith("--t") and "=" in x and tdir(x)] + [x[2:] for x in a if x.startswith("-t") and x[2:3] in ("/", "~", "$")] for y in _brace(x)]
    ra = _rsyncopts(a) if name == "rsync" else a  # option values are not flags
    www = lambda t: name == "rsync" and bool(WWW.fullmatch(re.sub(r"^[^/:\s]{2,}:(?!//)", "", t)))  # deploying into a named child of /var/www adds web content, it is not a system file
    if name in ("cp", "mv", "install", "ln", "rsync", "scp") and not (name == "rsync" and any(t == "--dry-run" or _bundle(t, "n") for t in ra)) and any(
            not t.startswith("-") and not www(t) and (_sysw(re.sub(r"^[^/:\s]{2,}:(?!//)", "", t) if name in ("rsync", "scp") else t) or _blk(t)) for t in dest):
        return f"{name} onto a system path. Edit a copy and ask the owner"
    if name == "ln" and any(HOMEP.match(t) for t in dest):
        return "ln onto a shell startup file or ~/.ssh|.aws|.gnupg replants a persistent hook. Ask the owner"
    if name == "chroot":
        k = 0
        while k < len(a) and a[k].startswith("-"):
            k += 2 if a[k] in ("--userspec", "--groups", "-u", "-g", "-G") else 1
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
    if (name == "aws" and ((pair("s3", "rm") and "--recursive" in a) or (pair("s3", "rb") and "--force" in a) or (pair("s3", "sync") and any(t.startswith("--del") for t in a))
                           or pair("ec2", "terminate-instances") or any(t.startswith("delete-db-") for t in w) and "rds" in w)) \
            or (name == "gcloud" and pair("projects", "delete")) or (name == "az" and pair("group", "delete")) or (name == "gsutil" and "rsync" in w and any(_bundle(t, "d") for t in a)):
        return f"{name} bulk or whole-resource delete. Name the exact resource and ask the owner"
    if name in ("terraform", "tofu", "terragrunt") and (w[:1] == ["destroy"] or w[:2] == ["state", "rm"] or (
            w[:1] == ["apply"] and any(t in ("-destroy", "--destroy") for t in a)) or (name == "terragrunt" and "destroy" in w)):
        return f"{name} destroy/state rm removes real infrastructure or its record. Run `plan -destroy` and ask the owner"
    pw = [t for t in a if not t.startswith("-")]  # positional words: flag values stay in, so look for adjacent verbs, never a fixed position
    if name in ("terraform", "tofu", "terragrunt") and ("workspace", "delete") in zip(pw, pw[1:]) and _on(a, "-force", "--force"):
        return f"{name} workspace delete -force removes a workspace with live state. Ask the owner"
    if name == "helm" and "rollback" in pw and not HELMV & set(pw[:pw.index("rollback")]) and _on(a, "--force"):
        return "helm rollback --force deletes and recreates resources. Ask the owner"
    if name == "launchctl" and (r := _launchctl(a, depth)):
        return r
    sw = [t for k, t in enumerate(a) if not t.startswith("-") and not (k and a[k - 1] in SVAL)]
    if name == "systemctl" and "--user" not in a and sw[:1] in (["disable"], ["mask"], ["stop"]) and any(_critunit(t) for t in sw[1:]):
        return "systemctl stop/disable/mask of ssh, network, docker, dbus, firewall or systemd units can lock you out of the host. Ask the owner"
    bw = [t for k, t in enumerate(a) if not t.startswith("-") and not (k and a[k - 1] == "--format")]  # skip `--format json`
    if name == "btrfs" and len(bw) > 1 and "subvolume".startswith(bw[0]) and len(bw[0]) >= 2 and "delete".startswith(bw[1]):
        return "btrfs subvolume delete removes a subvolume and its data. Ask the owner"
    recur = any(t == "--recursive" or _bundle(t, "r") or _bundle(t, "R") for t in a)
    ddb1 = w[:2] == ["dynamodb", "delete-item"] and ph is None and any(t == "--key" or t.startswith("--key=") for t in a) and not any(re.search(r"[$`]", t) for t in a)  # one literal item
    pulprev = _pulprev(a)
    if name == "etcdctl" and any(t in ("del", "delete") for t in w) and _on(a, "--from-key", "--prefix"):
        return "etcdctl del --from-key/--prefix deletes a whole key range. Name exact keys and ask the owner"
    if name == "kubectl" and "replace" in w and _on(a, "--force"):
        return "kubectl replace --force deletes the object and recreates it, dropping its dependents. Use `kubectl apply` and ask the owner"
    if name == "kubectl" and "scale" in w and _on(a, "--all") and any(_zero(t.partition("=")[2] or (a[k + 1] if k + 1 < len(a) else "")) for k, t in enumerate(a) if t.split("=")[0] == "--replicas"):
        return "kubectl scale --all --replicas=0 stops every workload. Name the objects to scale and ask the owner"
    if name == "bq" and "rm" in w and any(t.split("=")[0] in ("-r", "-f", "--recursive", "--force") and _on([t], t.split("=")[0]) or _bundle(t, "r") or _bundle(t, "f") for t in a):
        return "bq rm -r/-f deletes a dataset or table without a prompt. Name the exact table, omit -f, and ask the owner"
    if name in ("apt", "apt-get", "aptitude", "dnf", "yum", "microdnf", "tdnf", "zypper", "apk", "rpm", "dpkg", "pacman") and _corepkg(name, a, ph):
        return f"{name} removal of a core system package (libc, systemd, kernel, dpkg, sudo, ...) breaks or bricks the host. Preview with `--simulate` and ask the owner"
    if name == "influx" and "delete" in w:
        k = w.index("delete")
        pred = [t.partition("=")[2] if "=" in t else a[x + 1] if x + 1 < len(a) else "" for x, t in enumerate(a) if t.split("=")[0] == "-p" or (t.startswith("--pred") and "--predicate".startswith(t.split("=")[0]))]
        if w[k - 1:k] in (["bucket"], ["org"]) or (not set(w[:k]) & INFCMD and not any(p.strip() for p in pred)):
            return "influx delete without a non-empty --predicate (or bucket/org delete) wipes a whole time range or bucket. Add a --predicate and ask the owner"
    if name == "influx" and any(x in ("bucket", "org") and w[i + 1:i + 2] in (["remove"], ["rm"]) for i, x in enumerate(w)):
        return "influx bucket/org remove deletes a whole bucket or org. Ask the owner"
    if (name == "eksctl" and "delete" in w and w[w.index("delete") + 1:][:1] == ["cluster"] and not _on(a, "--dry-run")) or (name in ("skopeo", "crane", "regctl", "oras") and "delete" in w):
        return f"{name} delete removes a cluster or a registry image for good. Ask the owner"
    if name == "borg" and any(x in ("delete", "prune", "rdelete", "repo-delete") for x in w) and not any(t == "--dry-run" or _bundle(t, "n") for t in a):
        return "borg delete/prune/rdelete destroys backup archives for good. Preview with `--dry-run` and ask the owner"
    if name == "velero" and ("uninstall" in w or ("delete" in w and (_on(a, "--all", "--from-schedule") or any(t.split("=")[0] in ("-l", "--selector") for t in a) or w[-1:] == ["delete"]))):
        return "velero delete --all/--selector/--from-schedule (or uninstall) removes backups for good. Name one backup and ask the owner"
    if name in ("vipw", "vigr"):
        return f"{name} edits the account database by hand. Ask the owner"
    if name in ("userdel", "deluser") and any(t in ("--remove", "--remove-home", "--remove-all-files", "--force") or (not t.startswith("--") and (_bundle(t, "r") or _bundle(t, "f"))) for t in a):
        return f"{name} with -r/-f deletes the account's home directory and files for good. Back them up and ask the owner"
    if name in ("iptables", "ip6tables", "iptables-legacy", "ip6tables-legacy", "iptables-nft", "ip6tables-nft") and any(
            t in ("-P", "--policy") and a[k + 1:k + 2][0:1] and a[k + 1].upper() in ("INPUT", "OUTPUT") and a[k + 2:k + 3][0:1] and a[k + 2].upper() in ("DROP", "REJECT") for k, t in enumerate(a)):
        return "iptables default policy DROP/REJECT on INPUT/OUTPUT (with -F) cuts every connection, ssh included. Add the allow rules first and ask the owner"
    if name in ("passwd", "usermod", "chsh", "chage", "sed", "perl") and _rootlock(name, a):
        return f"{name} locks out root or edits the account database. Ask the owner"
    if name == "ansible" and (r := _ansible(a, depth)):
        return r
    if (name == "aws" and len(w) > 1 and not ddb1 and re.match(r"(?:(?:delete|terminate|purge)-|schedule-key-deletion$)", w[1])) \
            or (name == "gcloud" and ("delete" in w or ("rm" in w and recur))) \
            or (name == "gsutil" and "rm" in w and recur) \
            or (name == "az" and any(t in ("delete", "purge") for t in w)) \
            or (name == "pulumi" and ((w[:1] == ["destroy"] and not pulprev) or w[:2] == ["stack", "rm"])) \
            or (name == "helm" and w[:1] in (["uninstall"], ["delete"], ["un"], ["del"])) \
            or (name == "kubectl" and (w[:1] == ["drain"] or ("delete" in w and any(
                t in ("--all", "--all-namespaces") or _bundle(t, "A") for t in a)))):
        return f"{name} deletes cloud/cluster resources. Name the exact resource and ask the owner"
    if name in ("npm", "pnpm") and (("deprecate" in w and w[w.index("deprecate") + 2:][:1] != [""]) or ("owner" in w and any(x in ("rm", "remove") for x in w))):  # an empty message un-deprecates
        return f"{name} deprecate/owner rm changes who can publish or use a package. Ask the owner"
    pre1 = name in ("npm", "pnpm") and ph is None and len(w) == 2 and not any((t.startswith("--f") and len(t.split("=")[0]) >= 3 and "--force".startswith(t.split("=")[0])) or _bundle(t, "f") for t in a) \
        and re.fullmatch(r"(?:@[\w.-]+/)?[\w.-]+@\d+\.\d+\.\d+-[0-9A-Za-z][0-9A-Za-z.-]*", w[1]) is not None  # one exact prerelease version
    if (name in ("npm", "pnpm", "yarn") and "unpublish" in w and not pre1) or (name in ("cargo", "gem") and "yank" in w and "--undo" not in a and not (name == "cargo" and ph is None and _yank1(a))) \
            or (name in ("apt", "apt-get", "aptitude") and ("--allow-remove-essential" in a or (
                    ("purge" in w or "remove" in w) and any(re.search(r"[*?\[]", t) for t in w)))
                and not any(t in ("-s", "--simulate", "--just-print", "--dry-run", "--no-act") for t in a)) \
            or (name in ("pip", "pip3") and "uninstall" in w and (ph is not None or any(
                t in ("-r", "--requirement") or t.startswith("--requirement=") for t in a))):
        return f"{name} unpublish/yank/purge/bulk uninstall is hard to undo. Name the exact package and ask the owner"
    if name == "sgdisk" and any(t.split("=")[0] in ("--zap", "--zap-all", "--clear", "--delete", "--new", "--load-backup", "--mbrtogpt", "--gpttombr", "--replicate") or any(_bundle(t, c) for c in "zZodnlgmR") for t in a):
        return "sgdisk zap/clear/delete/new/load rewrites the partition table. Do it in a VM, never on the host"
    if name in ("gpg", "gpg2") and any(re.fullmatch(r"--delete-(?:secret-)?(?:and-public-)?keys?|--delete-secret-and-public-keys?", t.split("=")[0]) for t in a):
        return "gpg --delete-keys/--delete-secret-keys destroys keys for good. Export a backup (`gpg --export-secret-keys`) and ask the owner"
    if name == "security" and w[:1] and w[0].startswith("delete-"):
        return "security delete-* removes keychains, passwords or certificates for good. Use `security find-*` to inspect and ask the owner"
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
        kinds = set(r.split(",")) | {t.split("/")[0].lower() for t in a[a.index("delete"):] if "/" in t and not t.startswith("-") and not t.endswith((".yaml", ".yml", ".json"))}  # `pods,nodes`, `pod/a node/b`
        kinds = {re.sub(r"\.(?:v1|project\.openshift\.io)$", "", x) for x in kinds}  # `namespaces.v1`; a CRD such as `namespace.foo.io` is not a namespace
        if kinds & {"node", "nodes", "no"}:
            return "kubectl delete node removes the node from the cluster and strands its pods. Use `kubectl cordon` and ask the owner"
        if kinds & {"ns", "namespace", "namespaces", "project", "projects", "projectrequest", "projectrequests"} or (r == "all" and ("--all" in a or "-A" in a or "--all-namespaces" in a)):
            return "kubectl delete namespace/all removes a whole workload. Delete exact named objects and ask the owner"
    if name == "kubectl" and "delete" in w and any(_kstdin(a, j) for j in range(len(a))):
        return "kubectl delete -f - deletes whatever manifest is piped in, which cannot be vetted. Write it to a file, read it, then delete by exact name"
    if name == "ssh-add" and any(t == "--delete-all" or _bundle(t, "D") for t in a):
        return "ssh-add -D removes every loaded key from the agent. Use `ssh-add -d KEYFILE` or ask the owner"
    if name == "cipher" and any(t.lower().startswith("/w") for t in a):
        return "cipher /w overwrites deleted data on a volume for good. Do it in a VM, never on the host"
    if name in ("gh", "glab") and w[:2] == ["alias", "set"] and len(w) > 3:  # an alias body is a gh command, or a shell command with -s/--shell
        r = check(w[3] if any(t in ("-s", "--shell") for t in a) else name + " " + w[3], depth + 1)
        if r:
            return r
    if name == "tmutil" and any(t in ("delete", "deletelocalsnapshots") for t in w[:1]):
        return "tmutil delete removes Time Machine backups. Ask the owner"
    if name in ("cdk", "cdktf", "sst", "serverless", "sls") and w[:1] in (["destroy"], ["remove"]):
        return f"{name} destroy removes a cloud stack. Run a diff/plan and ask the owner"
    if (name == "doctl" and "delete" in w) or (name in ("flyctl", "fly") and any(t in ("destroy", "delete") for t in w)) \
            or (name == "heroku" and any(re.search(r":(?:destroy|delete|reset)$", t) or t == "destroy" for t in w[:1])):
        return f"{name} deletes a cloud resource. Name the exact resource and ask the owner"
    if name == "rclone" and not any(t in ("--dry-run", "-n") for t in a) and (any(
            x in ("purge", "delete", "deletefile", "rmdirs", "cleanup", "dedupe", "sync", "move", "moveto", "bisync") for x in w) or any(t.startswith("--delete") for t in a)):
        return "rclone purge/delete/sync removes remote files (sync mirrors a possibly empty source). Preview with `--dry-run` and ask the owner"
    if name == "restic" and not any(t in ("--dry-run", "-n") for t in a) and (any(x in ("forget", "prune") for x in w[:4]) or (
            "unlock" in w and "--remove-all" in a) or any(x == "key" and w[k + 1:k + 2] in (["remove"], ["rm"]) for k, x in enumerate(w))):
        return "restic forget/prune/key remove/unlock --remove-all deletes backup snapshots for good. Preview with `--dry-run` and ask the owner"
    if name in ("zfs", "zpool") and not any(t == "--dry-run" or _bundle(t, "n") for t in a) and (
            w[:1] in (["destroy"], ["labelclear"]) or (name == "zfs" and w[:1] in (["rollback"], ["receive"], ["recv"]) and (w[0] == "rollback" or any(
                _bundle(t, "F") for t in a))) or (name == "zpool" and w[:1] == ["create"] and any(_bundle(t, "f") or t == "--force" for t in a))):
        return f"{name} destroy/rollback/receive -F/create -f/labelclear erases datasets, snapshots or pools. Preview with `-n` and ask the owner"
    lv = w[0] if name == "lvm" and w else name  # `lvm lvresize ...`
    sz = re.findall(r"(?:^|\s)(?:-[Ll]|--size|--extents)(?:=|\s*)(\S+)", " ".join(a))
    nf = sum(t.count("f") for t in a if re.fullmatch(r"-[A-Za-z]+", t)) + a.count("--force")
    if lv in ("lvremove", "vgremove", "pvremove", "lvreduce", "lvresize", "pvcreate", "vgcreate") and not any(t in ("--test", "-t", "-h") for t in a) and (
            lv != "lvresize" or not (sz and all(x.startswith("+") for x in sz))) and (lv not in ("pvcreate", "vgcreate") or nf >= 1):
        return f"{lv} removes, shrinks or force-overwrites LVM volumes. Do it in a VM, never on the host"
    if name in PAAS and (any(PAASDEL.search(x) for x in w) or (
            name == "supabase" and "reset" in w[:3] and any(t == "--linked" or t.startswith("--db-url") for t in a))):
        return f"{name} deletes or resets a hosted project or its data. Ask the owner"
    if name == "hg" and w[:1] in (["strip"], ["purge"]):
        return "hg strip/purge destroys history or untracked files. Ask the owner"
    if name == "make" or name == "gmake":
        if any(re.search(r"clean|purge|wipe|nuke|uninstall|destroy|reset", x) for x in w if "=" not in x) and any(
                "=" in t and not t.startswith("-") and _far(t.split("=", 1)[1]) and t.split("=", 1)[1] for t in a):
            return "make clean with a variable pointing at root or home. Name an in-project directory"
    if name == "gem" and w[:1] == ["uninstall"] and (len(w) == 1 or (any(t == "--all" or _bundle(t, "a") for t in a) and any(
            t == "--ignore-dependencies" or _bundle(t, "I") for t in a))):
        return "gem uninstall of every gem or with --ignore-dependencies breaks the toolchain. Name the exact gem"
    if name == "diskutil" and [x.lower() for x in w[:1]] in (["apfs"], ["ap"], ["corestorage"], ["cs"]) and w[1:2] and re.match(r"(?i)(?:delete|erase)", w[1]):
        return "diskutil apfs/cs delete or erase destroys volumes. Do it in a VM, never on the host"
    if name in ("kubectl", "oc") and ("run" in w or "debug" in w) and (any(
            re.search(r"""["']?(?:hostPID|hostNetwork|hostIPC|privileged)["']?\s*:\s*true|["']?hostPath["']?\s*:""", t) or re.fullmatch(
                r"--privileged(?:=true)?|--profile=(?:sysadmin|privileged)", t) for t in a) or ("debug" in w and any(t.startswith("node/") for t in w))):
        return "kubectl run with host namespaces, privileged or hostPath escapes the pod. Ask the owner"
    if name == "redis-cli" and any(t.upper() in ("FLUSHALL", "FLUSHDB") for t in a):
        return "redis FLUSHALL/FLUSHDB wipes the keyspace. Ask the owner"
    if name in ("mongo", "mongosh") and any(re.search(r"dropDatabase\s*\(", t) for t in a):
        return "mongo dropDatabase. Ask the owner"
    if name == "wipefs" and not any(t in ("-n", "--no-act") for t in a) and any(
            t.startswith(("--all", "--offset")) or _bundle(t, "a") or _bundle(t, "o") for t in a):
        return "wipefs erases filesystem signatures on a device. Do it in a VM, never on the host"
    pre = lambda t, f: len(t) >= 5 and t.startswith("--") and f.startswith(t.split("=")[0])  # getopt long-option prefix
    if name == "mdadm" and any(pre(t, "--zero-superblock") or pre(t, "--create") or _bundle(t, "C") for t in a):
        return "mdadm --zero-superblock/--create erases RAID metadata on member disks. Do it in a VM, never on the host"
    if name == "cryptsetup" and any(x in ("luksErase", "erase", "luksFormat", "luksKillSlot", "luksRemoveKey", "reencrypt") for x in w[:3]):
        return "cryptsetup erase/luksFormat/luksKillSlot/luksRemoveKey destroys the key slots, so the data is gone for good. Do it in a VM, never on the host"
    if ph is not None and name in XTOOLS and any(XDEL.fullmatch(x) or x.startswith(("delete-", "terminate-", "purge-")) for x in w[:6]):
        return f"{name} delete fed by xargs removes a whole piped list that cannot be vetted. Delete exact named objects and ask the owner"
    if name == "blkdiscard" and not any(t in ("-V", "--version", "-h", "--help") for t in a):
        return "blkdiscard discards every block of a device for good. Do it in a VM, never on the host"
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
        pr = next((x for x in ("container", "image", "volume", "network", "builder", "buildx", "plugin", "config", "pod") if d[:2] == [x, "prune"]), "")  # `prune -f` skips the prompt
        fl = [d[2:][m + 1] if t == "--filter" and m + 1 < len(d[2:]) else t[9:] for m, t in enumerate(d[2:]) if t == "--filter" or t.startswith("--filter=")]
        if pr and any(t == "--force" or _bundle(t, "f") for t in d[2:]) and not (fl and all(re.match(r"(?:until|label|dangling)=", x) for x in fl)):  # only age, label=KEY or dangling= filters scope it
            return f"{name} {pr} prune -f deletes unused objects without a prompt. Run it without -f to review, or name exact objects and ask the owner"
        if d[:1] in (["compose"], ["container"]):
            d = d[1:]
        if name == "docker-compose" or a[k:k + 1] == ["compose"]:  # compose options (-f FILE, -p NAME) precede the verb
            v = next((m for m, t in enumerate(d[:16]) if t in ("exec", "run")), None)
            d = d[v:] if v is not None else d
        if name == "docker-compose" or a[k:k + 1] == ["compose"]:
            if d[:1] == ["down"] and any(t in ("--volumes", "--rmi") or _bundle(t, "v") for t in d):
                return "compose down -v/--rmi removes volumes or images with their data. Use `compose stop`, or ask the owner"
        if d[:1] in (["exec"], ["run"]):  # `docker run [opts] IMG CMD...`: the container command is checked
            r = _ctr(d[1:], depth, "euwvplhmac", CTR_VAL)
            if r:
                return r
        if d[:2] == ["system", "reset"] and name != "docker":
            return f"{name} system reset removes all images, containers and volumes. Ask the owner"
        # `$(` tokenizes to a bare `$`, so bulk rm shows as t == "$"
        if d[:2] in (["volume", "rm"], ["volume", "prune"]) or (d[:2] == ["system", "prune"] and any(
                t in ("--volumes", "--all") or _bundle(t, "a") for t in d)) or (
                d[:1] in (["rm"], ["rmi"], ["kill"]) and any(t == "$" or "`" in t or "$(" in t for t in d)) or (
                d[:2] == ["swarm", "leave"] and any(t == "--force" or _bundle(t, "f") for t in d)):
            return "docker volume rm/prune, system prune --volumes/-a or bulk rm removes data. Name the exact container and ask the owner"
    if name == "kill" and a and a[-1] in ("-1", "0") and a[-2:-1] not in (["-s"], ["-n"], ["--signal"]):
        return "kill -1/0 signals every process or the whole process group. Use `kill` on the exact PID"
    if name in ("shutdown", "reboot", "halt", "poweroff") or (name == "systemctl" and any(t in ("poweroff", "reboot", "halt") for t in a)):
        return f"{name} takes the host down. Never run it from an agent"
    tg = [t for t in a if not t.startswith("-") and t != "0"]
    if name == "crontab" and (any(re.fullmatch(r"-[a-zA-Z]*r[a-zA-Z]*", t) for t in (a[:a.index("--")] if "--" in a else a)) or "/dev/null" in a):
        return "crontab -r (or a /dev/null install) deletes every scheduled job with no confirmation or undo. Back up with `crontab -l > file`, then ask the owner"
    if (name == "shred" and not _shred_ok(a)) or (name == "truncate" and any(_sens(t) for t in tg)) or (name == "truncate" and re.search(r"(?:^|\s)(?:-s\s*0|--size[= ]0)(?:\s|$)", " ".join(a))
                           and not (tg and all(not t.startswith(("/", "~", "$")) and ".." not in t.split("/") and re.search(r"\.(?:log|out|err|tmp|txt)$", t) and not re.search(r"[*?\[`$]", t) for t in tg))):
        return f"{name} irrecoverably destroys file contents. Write to a new file or ask the owner"
    if name == "rsync" and any(t.startswith(("--delete", "--remove-")) or t in ("--del", "--dele", "--delet") for t in ra) and not any(t == "--dry-run" or _bundle(t, "n") for t in ra):
        return "rsync --delete (or --remove-source-files) removes files. Preview with `--dry-run` and name an exact destination"
    if name in SQLCLI:  # `psql -f FILE`, `--file=FILE`, `--queries-file FILE`
        for j, t in enumerate(a):
            f = t.split("=", 1)[1] if t.startswith(("--file=", "--queries-file=")) else a[j + 1] if t in ("-f", "--file", "--queries-file") and j + 1 < len(a) else ""
            r = _sqlfile(f) if f else ""
            if r:
                return r
    if name == "sqlite3":
        r = _sqlite(a, depth)
        if r:
            return r
    if name in SQLCLI and not (name == "sqlite3" and ":memory:" in a and not re.search(r"attach|\.shell|\.system|\.read", " ".join(a), re.I)) and not _testsql(name, a) and any(_sqlhit(SQLCOMMENT.sub(' ', re.sub(r"^-[A-Za-z]", r"\g<0> ", t))) for t in a[:512]):  # first 512 args bound the scan; `-c'drop ...'` joins flag and text
        return SQLWHY
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


def _emitted(cmd, depth):
    """Reason when a shell word (`bash -c`, `eval`, `source`) runs the output of `$(printf ...)` / `$(echo ...)`: that output is the command."""
    if not re.search(r"printf|echo", cmd):
        return ""
    for n, m in enumerate(DECSTART.finditer(cmd)):
        if n >= 64:
            break
        w = cmd[m.end():m.end() + 600]
        g = re.search(r"[|;&\n]", w[:300])
        for k, su in enumerate(SUBST.finditer(w[:g.start() if g else 300])):
            if k >= 8:
                break
            body = re.match(r"\s*(printf|echo)\s+(.*)", _subbody(w[su.end():su.end() + 400], w[su.start()] == "`"), re.S)
            if not body:
                continue
            try:
                args = shlex.split(body[2])
            except ValueError:
                continue
            if "\\" in body[2] or (body[1] == "printf" and args and len(args) > 1 and len(args) - 1 > len(re.findall(r"%[-+# 0-9.]*[a-zA-Z]", args[0].replace("%%", ""))) > 0):
                return "output of printf/echo run by a shell uses escapes or a reused format and cannot be vetted. Write the command out, read it, then run it"  # fail closed
            args = [t for t in args if not (body and body[1] == "echo" and re.fullmatch(r"-[neE]+", t))]
            if not args:
                continue
            out = " ".join(args) if body[1] == "echo" else re.sub(r"%[sb]", lambda _, it=iter(args[1:]): next(it, ""), args[0])
            r = check(out, depth + 1)
            if r:
                return r
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
    return os.path.basename(toks[i]) if i < len(toks) else "sh" if any(os.path.basename(t) == "xargs" for t in toks) else ""  # bare xargs: judge the text as commands


def _feed(name, text):
    """Reason when `text` is fed to shell/interpreter `name` and is destructive."""
    if name in SHELLS + ("eval",):
        return check(text, 1)
    if name == "chpasswd" and re.search(r"(?m)^\s{0,20}(?:root|0):", text):
        return "chpasswd of root can lock root out (a `!`/`x` hash, a typo). Ask the owner"
    if INTERP.match(name) or name in AWK:
        return _body(text)
    if name == "sqlite3" and _sqlite([text], 1):
        return _sqlite([text], 1)
    if name in SQLCLI and _sqlhit(SQLCOMMENT.sub(' ', text)):
        return SQLWHY
    return ""


def _np(f):
    return f[2:] if f.startswith("./") else f


REMOTE = ("docker", "podman", "nerdctl", "kubectl", "oc", "docker-compose", "chroot")
WROTE = re.compile(r"(?<![0-9&])>>?[ \t]*([^\s&|;<>()]+)|\btee[ \t]+(?:-\w+[ \t]+)*([^\s&|;<>()-][^\s&|;<>()]*)")


def _remote(pre, body):
    """Reason when a heredoc body is the script a remote/container shell reads on stdin (`ssh host <<EOF`, `docker exec -i c sh <<EOF`)."""
    try:
        toks = shlex.split(re.split(r"[;&|\n(]", pre)[-1])
    except ValueError:
        return ""
    i = _unwrap(toks)[0]
    n, a = (os.path.basename(toks[i]), toks[i + 1:]) if i < len(toks) else ("", [])
    if n == "ssh":
        k = 0
        while k < len(a) and a[k].startswith("-"):
            k += 2 if a[k][-1] in SSH_VAL and len(a[k]) == 2 else 1
        a = a[k + 1:]
        return check(body, 1) if not a or os.path.basename(a[0].split()[0] if a[0].split() else "") in SHELLS else ""
    return check(body, 1) if n in REMOTE and any(os.path.basename(t) in SHELLS for t in a) else ""


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
    return "destructive pattern in unparseable command (regex fallback). Spell it out as plain quoted words, one command per step" if any(p.search(cmd) for p in FALLBACK) else ""


def _ansic(m):
    """`$'\\x72\\x6d'` is the word `rm`: decode escapes to a quoted literal; text with control characters or bad escapes stays as written."""
    try:
        t = codecs.decode(m[1].encode("latin-1", "backslashreplace"), "unicode_escape")
    except (UnicodeError, ValueError):
        return m[0]
    return shlex.quote(t) if t.isprintable() else m[0]


def _substs(body):
    """Texts to vet for the unescaped `$(` and backtick substitutions of an unquoted heredoc body: from each start to the end of the body (no paren matching, so quotes, `case` and comments cannot hide the
    rest). A backtick pair counts as one substitution."""
    out, tick = [], False
    for x in re.finditer(r"(\\*)(\$\(|`)", body):
        if len(x[1]) % 2:
            continue
        if x[2] == "`":
            tick = not tick
            if not tick:
                continue
        out.append(body[x.end():])
    return out


DATAHD = re.compile(r"\s*(?:cat\s*(?:>>?\s*[\w./~-]+\s*)?|tee\s+(?:-a\s+)?[\w./~-]+\s*|git\s+commit\s+(?:-\S+\s+)*-F\s*-\s*)<<(-?)\s*(['\"]?)(\w+)\2\s*(?:>>?\s*[\w./~-]+\s*)?")


def _nodata(cmd):
    """`cmd` without the bodies of heredocs fed to a plain `cat`/`tee`/`git commit -F -`; a heredoc fed to anything else (`bash`, `python`) stays. An unterminated heredoc, or an unquoted one whose body expands `$(`/backticks, stays too."""
    ls, out, i = cmd.split("\n"), [], 0
    while i < len(ls):
        out.append(ls[i])
        m, i = DATAHD.fullmatch(ls[i]), i + 1
        if m:
            end = next((j for j in range(i, len(ls)) if (ls[j].lstrip("\t") if m[1] else ls[j]) == m[3]), None)
            if end is not None and (m[2] or not re.search(r"\$(?:\\\n)?\(|`", "\n".join(ls[i:end]))):
                i = end
    return "\n".join(out)


def _sshsplit(cmd):
    """An edit of `sshd_config`, `sshd_config.d/*` or an `sshd_*` glob, by any command that has `sed|gsed|perl|awk|gawk|ex|vim|vi|ed` as a word and the file as another word (so no wrapper list is needed;
    `ed` reads its script from the heredoc that follows), that sets a value `no`, where one edit names `PermitRootLogin` and another
    `PasswordAuthentication|KbdInteractiveAuthentication|ChallengeResponseAuthentication`. Quote-aware: `;`, `|` inside a quoted script stay in their command."""
    root = pw = False
    ls = cmd.split("\n")
    for n, line in enumerate(ls):
        try:
            lx = shlex.shlex(line, posix=True, punctuation_chars=True)
            lx.whitespace_split = True
            lx.commenters = ""
            toks = list(lx)
        except ValueError:
            continue
        cmds, cur = [], []
        for t in toks:
            if t and set(t) <= set(";&|()"):
                cmds.append(cur)
                cur = []
            else:
                cur.append(t)
        for t in cmds + [cur]:
            ws = [os.path.basename(y) for y in t]
            if not any(w in ("sed", "gsed", "perl", "awk", "gawk", "ex", "vim", "vi", "ed") for w in ws) or not any(re.fullmatch(r"(?:.*/)?sshd_(?:config(?:\.d/\S*|\*)?|\*|\?+)", y) for y in t):
                continue
            sc = " ".join(y for y in t if not re.fullmatch(r"(?:.*/)?sshd_\S*", y))
            if "ed" in ws and any("<<" in y for y in t):
                sc += " " + "\n".join(ls[n + 1:])
            if re.search(r"(?:(?<![\w-])|(?<=\\[ts]))no(?![\w-])", sc, re.I):
                root |= re.search(r"PermitRootLogin|\bRootLogin", sc, re.I) is not None
                pw |= re.search(r"PasswordAuthentication|KbdInteractiveAuthentication|ChallengeResponseAuthentication", sc, re.I) is not None
    return root and pw


MAXCMD, MAXLINES, MAXHARD = 65536, 2000, 10_000_000


def check(cmd, _depth=0, _ph=None):
    """Return a one-line reason `cmd` is destructive, or '' (parse errors use the regex fallback).

    `_ph`: xargs placeholders inherited by a nested `sh -c` body."""
    if _depth == 0 and len(cmd) > MAXHARD:
        return f"command over {MAXHARD} characters cannot be vetted (fail closed). Split it or run it yourself"
    if _depth == 0 and (len(cmd) > MAXCMD or cmd.count("\n") > MAXLINES):
        d = _nodata(cmd)  # a plain `cat >f`/`tee f`/`git commit -F -` heredoc body is data, not counted
        if len(d) > MAXCMD or d.count("\n") > MAXLINES:
            return f"command over {MAXCMD} characters or {MAXLINES} lines cannot be vetted (fail closed). Split it or run it yourself"
    if _sshsplit(cmd):
        return "sshd_config edits that turn off root login and password login can lock out every ssh user. Keep one login method on, or run the edits yourself with the `!` prefix"
    cmd = PIDFILE.sub(_pidfile, cmd.replace("\\\n", ""))
    if _depth > MAXDEPTH:
        return _fallback(cmd)
    if "$'" in cmd:
        cmd = re.sub(r"\$'((?:[^'\\]|\\.)*)'", _ansic, cmd)
    if not re.search(r"\bgit\s*\(|\bfunction\s+git\b|\balias\b|\bhash\b|\bPATH=|\bGIT_", cmd):  # a redefined git could print any root
        cmd = TOPLEVEL.sub(r"./\1", cmd)  # `rm -rf "$(git rev-parse --show-toplevel)/out"` is the relative `./out`
    for m in itertools.islice(MKTEMP.finditer(cmd), 8) if not re.search(r"\bmktemp\s*\(|\bfunction\s+mktemp\b|\balias\b|\bhash\b|\bPATH=", cmd) else ():  # `td=$(mktemp -d)`, set once and never reassigned (`${td:=x}`, read, for), is a fresh dir: `rm -rf "$td"` removes only it
        if len(re.findall(r"(?<![\w$])" + m[1] + r"\b(?!\})", cmd)) == 1:
            cmd = cmd[:m.end()] + re.sub(r"(\brm(?:[ \t]+-[\w-]+)*[ \t]+(?:--[ \t]+)?)(\"?)\$(?:" + m[1] + r"|\{" + m[1] + r"\})\2(?=[ \t]*(?:$|[;&|)\n]))", r"\1/tmp/mktemp-dir", cmd[m.end():])
    if "mktemp" in cmd and not re.search(r"\bmktemp\s*\(|\bfunction\s+mktemp\b|\balias\b|\bhash\b|\bPATH=", cmd):  # `rm -rf $(mktemp -d)` removes the fresh empty dir it just made, as the sole operand
        cmd = RMTEMP.sub(r"\1/tmp/mktemp-dir", cmd)
    if "${TMPDIR:?" in cmd and "TMPDIR" not in re.sub(r"\$\{TMPDIR(?::\?[^}$`]*)?\}|\$TMPDIR\b", "", cmd):  # `${TMPDIR:?}/x` is `$TMPDIR/x` (fails when unset); any assignment or other mention of TMPDIR keeps it unscoped
        cmd = re.sub(r"\$\{TMPDIR:\?[^}$`]*\}(?=/)", "$TMPDIR", cmd)
    if "/.cache/" in cmd and "HOME" not in re.sub(r"\$\{HOME\}|\$HOME\b", "", cmd):  # removing a named child of the cache dir (no `..`, glob or variable), HOME never reassigned
        cmd = re.sub(r"\brm\b[^;&|\n]*", lambda m: CACHEOP.sub(r"\1/tmp/hc-\2", m[0]), cmd)
    if SYMLN.search(cmd) and re.search(r"\bmkfs[^;&|\n]*\.(?:img|raw)\b", cmd):
        return "mkfs of an image after `ln -s` in the same command: the link may point at a device. Run the steps separately"
    if SYMLN.search(cmd) and RMREC.search(cmd) and re.search(r"(?:\$TMPDIR|\$\{TMPDIR\}|/tmp)/\w", cmd):
        return "rm -r in scratch space after `ln -s` in the same command: the link may point at the host. Run the steps separately and `rm` the link itself (no trailing slash)"
    wr = {}  # file -> texts written to it; a later `sh FILE` / `./FILE` runs them
    for m in HEREDOC.finditer(cmd):  # a heredoc into a shell/interpreter is code; any other body is data
        pre = cmd[cmd.rfind("\n", 0, m.start()) + 1:m.start()]
        r = _feed(_head(pre), m.group(3)) or _remote(pre, m.group(3)) or (_feed("sh", m.group(3)) if re.search(r"\b(?:eval|(?:ba|z|da|k|a)?sh)\b[^\n]*(?:\$\(\s*cat\s*(?:\)|$)|`cat`)", pre) else "")  # eval "$(cat)" <<EOF
        if r:
            return r
        if not m.group(1):  # an unquoted body expands `$(..)` and backticks: vet each substitution's text (to its quote-aware close, else to the end of the body)
            subs = _substs(m.group(3))
            if len(subs) > 64:
                return "heredoc with over 64 command substitutions cannot be vetted (fail closed). Use a quoted tag (<<'EOF') or split it"
            for x in subs:
                r = check(x, _depth + 1)
                if r:
                    return r
        for w in WROTE.findall(pre + m.group(0).split("\n", 1)[0]):
            wr.setdefault(_np(w[0] or w[1]), []).append(m.group(3))
    cmd = _nocomment(_data(HEREDOC.sub(lambda m: m.group(0).split("\n", 1)[0], cmd)))
    if re.search(r">\(\s*(?:\S*/)?(?:bash|sh|zsh|dash|ash|ksh)\s*(?:-\w+\s*)*\)", cmd):
        return "text relayed into a shell by >(sh) cannot be vetted. Write it to a file, read it, then run it"
    r = _windel(cmd)
    if r:
        return r
    if any(PSDL.search(x) and PSEXEC.search(x) for x in cmd.split("\n")):
        return "iex/Invoke-Expression of downloaded content cannot be vetted. Download to a file, read it, then run it"
    ifs = re.search(r"\bIFS=(['\"]?)([^\s$'\"\w])\1", cmd)  # `IFS=,; set -- rm,-rf,/; "$@"`: split on the custom separator, then judge `set --` words
    sp = cmd.replace(ifs[2], " ") if ifs else cmd
    lastpos = max((x.end() for x in re.finditer(r"\$@|\$\*|\$\{[@*]\}", sp)), default=-1)  # one scan; each `set --` is judged against it
    for m in itertools.islice(re.finditer(r"\bset\s+--\s+([^;&|\n]+)", sp), 32):  # bounded: each match runs a nested check
        if m.end() < lastpos:
            r = check(m[1], _depth + 1)
            if r:
                return r
    cmd = re.sub(r"\$\{IFS\}|\$IFS\b", " ", cmd)  # rm${IFS}-rf is rm -rf
    if "()" in cmd and FORKBOMB.search(cmd):
        return "fork bomb. Never run it"
    r = _emitted(cmd, _depth)
    if r:
        return r
    for m in itertools.islice(re.finditer(r"(?:^|[;&|\n]\s*)(\w{1,32})=\"?(?:\$\(|`)", cmd), 8):  # `x=$(printf 'rm\x20-rf\x20/'); $x`: a variable holding decoded text, then run as the command word
        body = _subbody(cmd[m.end():m.end() + 400], cmd[m.end() - 1] == "`")
        if (DECODE.search(body) or re.match(r"\s*(?:printf|echo)\b[^\n]*\\", body)) and re.search(r"(?:^|[;&|\n({]|\bthen\b|\bdo\b)\s*\"?\$\{?" + m[1] + r"\b", cmd[m.end():]):
            return "variable set from decoded or escaped text is run as the command. Write the command out, read it, then run it"
    if _decexec(cmd):
        return "eval/shell of a decoded base64/hex payload cannot be vetted. Decode to a file, read it, then run it"
    if (_depth < 1 or (_depth < 2 and len(cmd) < 20000)) and "=" in cmd and "$" in cmd:  # `x=rm; $x -rf /` (also inside `bash -c`): expand simple assignments and re-check; depth-capped so `a=$b; b=$a` ends
        env = {m[1]: m[2][1:-1] if re.fullmatch(r"'[^']*'|\"[^\"]*\"", m[2]) else m[2]
               for m in re.finditer(r"(?:^|[;&|\n]\s*)(\w{1,32})=('[^']{0,200}'|\"[^\"]{0,200}\"|[^\s;&|'\"]{0,200})", cmd)}
        ex = re.sub(r"\$(?:\{(\w+)\}|(\w+))", lambda m: env.get(m[1] or m[2], m[0]), cmd)
        if env and ex != cmd:
            r = check(ex, _depth + 1)
            if r:
                return r
            used = re.findall(r"\$(?:\{(\w+)\}|(\w+))", cmd)
            once = {v: m for v in env for m in [re.search(r"(?:^|[;\n])\s*" + v + r"=[^\s;&|]*(?=\s*(?:;|\n|&&|$))", cmd)] if m and len(re.findall(r"(?<![\w$])" + v + "=", cmd)) == 1}
            if used and len(cmd) < 20000 and all((a or b) in once and once[a or b].start() < cmd.index("$" + ("{" if a else "") + (a or b)) and re.fullmatch(r"\.?/?[\w.-]+(?:/[\w.-]+)*", env[a or b]) for a, b in used):
                cmd = ex  # every variable is a plain path set once, at statement level, before use: judge the expanded command only
    elif _depth == 1 and len(cmd) >= 20000 and "=" in cmd and re.search(r"\$\{?\w", cmd):  # padding must not switch expansion off: fail closed
        return "padded command with variable use cannot be vetted. Shorten it and spell the command out"
    if DYNCMD.search(cmd):
        return "command word built from a variable or substitution with -rf/--hard. Spell the command out"
    cmd = cmd.replace("\\;", "\x01")  # find's `\;` terminator must not split the segment: tokens keep \x01, find treats it like `;`
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
    segs, ops, hs, hd, ri, ro, skip = [[]], [""], [None], [False], [None], [None], None
    for t in toks:
        if PUNCT.fullmatch(t):
            if t == "(" and not segs[-1] and ops[-1] == "|":
                continue  # `| (sh)`: stay in the pipeline
            if (re.search(r"[;|()\n]", t) and t != ">|") or not re.search(r"[<>]", t):
                segs.append([])
                hs.append(None)
                hd.append(False)
                ri.append(None)
                ro.append(None)
                ops.append("|" if t in ("|", "|&") else "<(" if "<(" in t else "")
                skip = None
            else:  # redirection: the next token is its target; the command continues
                if segs[-1] and segs[-1][-1].isdigit():
                    segs[-1].pop()
                skip = "hs" if t.endswith("<<<") else "t>" if t in (">", ">|", "&>") else "ta" if t in (">>", "&>>") else "t<" if t == "<" else "t"
                hd[-1] = hd[-1] or "<<" in t
        elif skip:
            if skip in ("t>", "ta") and (_sysw(t, skip == "ta") or _blk(t)):
                return "redirect writes a system file or raw disk. Edit a copy and ask the owner"
            if skip == "t>" and segs[-1] in EMPTYSRC and _trunc(t):
                return "redirect truncates a key/credential or database file. Back it up and ask the owner"
            if skip in ("t>", "ta"):
                ro[-1] = t
            if skip == "hs":
                hs[-1] = t
            elif skip == "t<":
                ri[-1] = t
            skip = None
        elif not segs[-1] and re.fullmatch(r"\{[^{}\s,]*(?:,[^{}\s,]*)+\}", t):
            segs[-1].extend(t[1:-1].split(","))  # `{rm,-rf,$X}` brace-expands to a command
        else:
            segs[-1].append(t)
    # fetch: curl/wget earlier in the pipeline; feed: echo/printf text; src: an earlier stage relays text
    fetch, prev, feed, src, up, cwd, pseg = False, "", None, False, [], "", []
    genv = bool(re.search(r"\bGIT_(?:DIR|WORK_TREE|INDEX_FILE|COMMON_DIR)=", cmd))
    for n, (seg, op, here) in enumerate(zip(segs, ops, hs)):
        if not seg:
            continue
        if op != "|":
            fetch, feed, src, up, catf = False, None, False, [], None
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
        if name == "popd":
            cwd = "~"  # back to an unknown earlier directory
        elif name in ("cd", "pushd"):  # a cd out of the tree makes later relative `rm` targets absolute (`cd /srv && rm -rf acme`); `cd` alone is home
            d = ([t for t in a if not t.startswith("-")] or ["~"])[0]
            cwd = d.rstrip("/") or "/" if d.startswith(("/", "~", "$")) or ".." in d.split("/") or d == "-" else cwd + "/" + d if cwd else ""
        elif name == "rm" and cwd:
            a = [t if t.startswith(("-", "/", "~", "$")) else cwd + "/" + t for t in a]
        if name == "rm" and ph and op == "|" and prev == "echo" and feed and feed[1:] and (not cwd or _scoped(cwd)) and all(LITPATH.fullmatch(x) for x in feed[1:]):
            a, ph = [y for t in a for y in (feed[1:] if t in ph else [t])], None  # `echo ./build | xargs -I{} rm -rf {}`: the targets are literal
        r = _cmd(name, a + ([t for t in seg[:i] if re.match(r"\w+=", t)] if name in ("make", "gmake", "psql") else []), ph, _depth, cwd, genv)
        if not r and ph and op == "|" and "find" in up and any(_findfar(t) for t in up if not t.startswith("-")) and (name in ("chown", "chgrp", "setfacl", "chattr") or (
                name == "chmod" and any(_permissive(t) or _frev([x for x in up if not x.startswith("-")], t) for t in a)) or (name in SHELLS and any(re.search(r"\b(?:chown|chgrp|setfacl|chattr|chmod)\b", t) for t in a))):
            r = "chown/chgrp/setfacl/chattr fed by `find` over root or /home rewrites the host. Target an exact in-project path"
        if not r and name == "rm" and ph and op == "|" and any((t.startswith(("/", "~", "$")) and not _scoped(t)) or ".." in t.split("/") for t in up):
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
        if not r and op == "|" and last and (name in SHELLS or INTERP.match(name)) \
                and all(t.startswith("-") for t in a):
            r = "text relayed into a shell/interpreter cannot be vetted. Write it to a file, read it, then run it" + JSONPIPE
        if not r and wr:  # `sh FILE`, `source FILE`, `sh < FILE`, `./FILE`: run a file written earlier in this command
            ran = ([t for t in a if not t.startswith("-")][:1] + [ri[n] or ""]) if name in SHELLS + ("source", ".") else [seg[i]]
            r = next((x for f in ran for t in wr.get(_np(f), []) for x in [_feed("sh", t)] if x), "")
        if not r and name in SHELLS + ("source", ".") and "/dev/stdin" in a:
            r = "shell reading /dev/stdin cannot be vetted. Write it to a file, read it, then run it"
        if not r and op == "<(" and prev in SHELLS + ("source", "."):
            r = "shell/source fed by process substitution cannot be vetted. Write it to a file, read it, then run it"
        if not r and here is not None:
            r = _feed(name, here)
        if not r and name in SQLCLI:  # `psql < F` and `cat F | psql`
            r = next((x for x in (_sqlfile(f) for f in ([ri[n]] if ri[n] else []) + (catf or [])) if x), "")
        if not r and op == "|" and feed:
            r = next((x for x in (_feed(name, f) for f in feed) if x), "")
        if not r and name == "tee" and not any(x == "--append" or _bundle(x, "a") for x in a) and any(_trunc(x) for x in a if not x.startswith("-")) \
                and (ri[n] == "/dev/null" or (op == "|" and _empty(pseg))):
            r = "tee of empty input truncates a key/credential or database file. Back it up and ask the owner"
        if not r and name == "crontab" and _cronin(a) and (ri[n] == "/dev/null" or (here is not None and not here.strip()) or (op == "|" and _empty(pseg))):
            r = "crontab fed empty input replaces the whole table with nothing, like `crontab -r`. Back up with `crontab -l > file`, then ask the owner"
        if not r and op == "|" and fetch and (name in SHELLS or INTERP.match(name)) and not _stdin_data(name, a):
            r = "curl/wget piped to a shell/interpreter. Download, read it, then run it" + JSONPIPE
        if r:
            return r
        up = (up + seg[:20])[-200:]
        src = src or hd[n] or name in ("echo", "printf", "cat", "tee") or (name == "openssl" and a[:1] == ["enc"] and any(
            t in ("-d", "-base64", "-a") for t in a)) or (name == "xxd" and any(_bundle(t, "r") for t in a)) or (
            name == "base64" and any(B64D.fullmatch(t) for t in a))
        fetch = fetch or name in ("curl", "wget")
        catf = [t for t in a if not t.startswith("-")] if name == "cat" else None
        feed = ([" ".join(a)] + a) if name in ("echo", "printf") else feed if name == "tee" and op == "|" else None  # joined, and each arg (printf FORMAT ARG)
        for f in ([ro[n]] if ro[n] and name in ("echo", "printf") else [t for t in a if not t.startswith("-")] if name == "tee" else []):
            wr.setdefault(_np(f), []).extend(feed or [])  # text echoed or tee'd into a file
        prev, pseg = name, seg[i:]
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


TIMEOUT = 10  # seconds of wall clock before the hook gives up and blocks


def main():
    """Run the check in a forked child the parent can kill: a regex spin holds the GIL, so an in-process alarm
    never fires, and a hook killed by a signal or rlimit exits non-2, which Claude Code treats as allow."""
    if "--selftest" in sys.argv:
        return selftest() or 0
    if not (hasattr(os, "fork") and hasattr(signal, "SIGALRM")):  # Windows: no watchdog
        return _run()
    try:
        pid = os.fork()
    except OSError:  # no process slot: vet in-process rather than exit 1 (allow)
        return _run()
    if not pid:
        try:
            code = _run()
            sys.stderr.flush()
        except BaseException:
            code = 2
        os._exit(code)

    def stop(sig, _):
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            pass
        if sig == signal.SIGALRM:
            print(f"Blocked: destructive guard did not finish within {TIMEOUT}s, so the command was not vetted.", file=sys.stderr)
        sys.exit(2)

    signal.signal(signal.SIGALRM, stop)
    signal.signal(signal.SIGTERM, stop)
    signal.alarm(TIMEOUT)
    st = os.waitpid(pid, 0)[1]
    signal.alarm(0)
    return os.WEXITSTATUS(st) if os.WIFEXITED(st) else 2  # killed by a signal: fail closed


def _run():
    raw = "" if sys.stdin.isatty() else sys.stdin.read()  # an interactive run must not hang
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
    try:
        code = main()
    except SystemExit as e:
        code = e.code
    except BaseException:
        code = 2
    sys.exit(code if code in (0, 2) else 2)  # Claude Code allows on any exit but 2, so every failure blocks
