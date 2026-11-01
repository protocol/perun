"""flow_alarm.py: stop-starting hook (throughput exemption, denial log), one symptom alarm, value-stream split."""
import importlib.util
import io
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

SCRIPT = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/flow_alarm.py"
GREEN = {"isDraft": False, "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
RED = {"isDraft": False, "statusCheckRollup": [{"conclusion": "FAILURE"}]}
DRAFT = {"isDraft": True, "statusCheckRollup": [{"conclusion": "SUCCESS"}]}
NOW = 1_800_000_000
# A hermetic git for the repos below and for the hook under test: no inherited GIT_* (a hook's GIT_DIR or GIT_INDEX_FILE would aim git
# at another repo), no user or system config, a fixed identity, and no search for a repo above the temp dir.
ENV = {**{k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "PERUN_THROUGHPUT_", "PERUN_STOP_STARTING_"))},
       "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CEILING_DIRECTORIES": tempfile.gettempdir(),
       "GIT_AUTHOR_NAME": "Jane Smith", "GIT_AUTHOR_EMAIL": "jane@example.com",
       "GIT_COMMITTER_NAME": "Jane Smith", "GIT_COMMITTER_EMAIL": "jane@example.com"}
LEDGER, DENIALS = "perun-throughput.jsonl", "perun-flow-denials.jsonl"  # in the repo's git common dir
WIDE_FAILED = "flow_alarm: queue read past 100 PRs failed; counted on the newest 100\n"  # the hook's notice for a failed second read


def run(args, open_prs=(), merged=(), stdin="", fail=False, env=None, cwd=None, fail_files=False, compare=None, fail_compare=False,
        recount=None, wide=None, fail_wide=False):
    """flow_alarm.py `args` as a process (fake gh serving `open_prs` and `merged`) in `cwd`, by default a plain temp dir: no repo.
    The per-lane recount's two calls: `compare` (a JSON-able reply, default `{}`) answers `gh api .../compare/...`, which `fail_compare`
    fails alone; `recount` (default `open_prs`: a list of PRs, or a str written as it is) answers the `gh pr list` that asks for `files`,
    which `fail_files` fails alone. The wide read (`--limit 500`, no `files`: the hook's second read of the queue, and `symptom`'s) answers
    `wide` (default `open_prs`, so both reads agree) and `fail_wide` fails it alone; the first read (`--limit 100`) answers `open_prs`.
    With the lanes variable set the hook's second read asks for `files` too, so `recount` answers it and `fail_files` fails it."""
    d = tempfile.mkdtemp()
    pathlib.Path(d, "open.json").write_text(json.dumps(list(open_prs)))
    pathlib.Path(d, "merged.json").write_text(json.dumps(list(merged)))
    pathlib.Path(d, "compare.json").write_text(json.dumps({} if compare is None else compare))
    pathlib.Path(d, "recount.json").write_text(recount if isinstance(recount, str) else json.dumps(list(open_prs if recount is None else recount)))
    pathlib.Path(d, "wide.json").write_text(json.dumps(list(open_prs if wide is None else wide)))
    gh = pathlib.Path(d, "gh")
    # the compare's arguments may hold `files` (a branch named so): its case comes first
    gh.write_text(f'#!/bin/sh\n[ {int(fail)} -eq 1 ] && exit 1\ncase "$*" in\n'
                  f'*compare*) [ {int(fail_compare)} -eq 1 ] && exit 1; cat {d}/compare.json;;\n'
                  f'*files*) [ {int(fail_files)} -eq 1 ] && exit 1; cat {d}/recount.json;;\n'
                  f'*"--limit 500"*) [ {int(fail_wide)} -eq 1 ] && exit 1; cat {d}/wide.json;;\n'
                  f'*"--state open"*) cat {d}/open.json;;\n'
                  f'*"--state merged"*) cat {d}/merged.json;;\nesac\n')
    gh.chmod(0o755)
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--now", str(NOW)], input=stdin, capture_output=True, text=True,
                          cwd=cwd or d, env={**ENV, "PERUN_GH": str(gh), **(env or {})})


def hook(cmd, ready, env=None):
    return run([], [GREEN] * ready, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}), env=env)


def git(cwd, *a):
    """stdout of `git a...` in `cwd` under ENV; raises on a non-zero exit."""
    return subprocess.run(["git", *a], cwd=cwd, env=ENV, check=True, capture_output=True, text=True).stdout


def branch(repo, name, files, base="origin/main", push=True):
    """Check out `name` off `base`, commit `files` ({path: text}) and, with `push`, point `origin/<name>` at the commit."""
    git(repo, "checkout", "-q", "--no-track", "-b", name, base)
    for path, text in files.items():
        f = pathlib.Path(repo, path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text)
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", name)
    if push:
        git(repo, "update-ref", f"refs/remotes/origin/{name}", "HEAD")


class T(unittest.TestCase):
    def test_hook_blocks_pr_create_at_threshold(self):
        r = hook("gh pr create --title x", 5)
        self.assertEqual(r.returncode, 2)
        self.assertIn("5 ready-but-unmerged", r.stderr)

    def test_hook_allows_below_threshold_priority_and_other_commands(self):
        self.assertEqual(hook("gh pr create --title x", 4).returncode, 0)
        self.assertEqual(hook("gh pr create --title x # priority: red trunk fix", 9).returncode, 0)
        self.assertEqual(hook("gh pr list", 9).returncode, 0)
        self.assertEqual(hook("gh pr create", 2, {"PERUN_STOP_STARTING_READY": "2"}).returncode, 2)

    def test_hook_gh_timeout_degrades_with_notice(self):
        import importlib.util
        import unittest.mock as m
        spec = importlib.util.spec_from_file_location("fa", SCRIPT)
        fa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fa)
        seen = []

        def slow(*a, timeout=60):
            seen.append(timeout)
            raise subprocess.TimeoutExpired("gh", timeout)
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create"}})
        with m.patch.object(fa, "gh_json", slow), m.patch("sys.stdin", __import__("io").StringIO(stdin)), \
                m.patch("sys.stderr", __import__("io").StringIO()) as err:
            self.assertEqual(fa.hook(), 0)
        self.assertEqual(seen, [10])
        self.assertIn("timed out", err.getvalue())

    def test_hook_fails_open(self):
        self.assertEqual(run([], fail=True, stdin='{"tool_input":{"command":"gh pr create"}}').returncode, 0)
        self.assertEqual(run([], stdin="garbage").returncode, 0)

    def test_draft_and_red_prs_are_not_ready(self):
        r = run([], [GREEN, RED, DRAFT] * 3, stdin='{"tool_input":{"command":"gh pr create"}}',
                env={"PERUN_STOP_STARTING_READY": "4"})
        self.assertEqual(r.returncode, 0)  # 3 ready < 4

    def test_the_train_marker_is_not_a_check(self):
        ok = {"__typename": "CheckRun", "status": "COMPLETED", "conclusion": "SUCCESS"}
        marker = {"__typename": "StatusContext", "context": "perun/train-stage", "state": "PENDING"}
        queued = {"isDraft": False, "statusCheckRollup": [ok, marker]}
        dropped = {"isDraft": False, "statusCheckRollup": [ok, dict(marker, state="FAILURE")]}
        other = {"isDraft": False, "statusCheckRollup": [ok, dict(marker, context="ci/other")]}
        alone = {"isDraft": False, "statusCheckRollup": [dict(marker, state="SUCCESS")]}
        stale, alarm = [{"mergedAt": "2027-01-15T05:00:00Z"}], (1, "ALARM flow: 1 ready PR(s) and nothing merged in 3.0h\n")
        # Still ready: queued or dropped by the train (any marker state, as landing_watchdog.green() reads it), and with the
        # script's own directory off sys.path (PYTHONSAFEPATH, like python3 -P or -I). A crash also exits 1, so stdout is checked.
        for pr, env in ((queued, None), (dropped, None), (queued, {"PYTHONSAFEPATH": "1"})):
            r = run(["symptom"], [pr], stale, env=env)
            self.assertEqual((r.returncode, r.stdout), alarm)
        self.assertEqual(run(["symptom"], [other, alone], stale).returncode, 0)  # another pending status blocks; the marker alone is no check
        self.assertEqual(run([], [queued] * 5, stdin='{"tool_input":{"command":"gh pr create --title x"}}').returncode, 2)  # the cap counts the train's queue

    def test_symptom_ready_but_nothing_landed(self):
        r = run(["symptom"], [GREEN], [{"mergedAt": "2027-01-15T05:00:00Z"}])  # epoch 1.8e9 = 2027-01-15T08:00:00Z
        self.assertEqual((r.returncode, r.stdout), (1, "ALARM flow: 1 ready PR(s) and nothing merged in 3.0h\n"))

    def test_symptom_healthy_cases(self):
        self.assertEqual(run(["symptom"], [GREEN], [{"mergedAt": "2027-01-15T07:30:00Z"}]).returncode, 0)
        self.assertEqual(run(["symptom"], [], [{"mergedAt": "2020-01-01T00:00:00Z"}]).returncode, 0)  # idle, not stuck

    def test_symptom_trunk_red_and_fail_closed(self):
        r = run(["symptom", "--red-since", str(NOW - 7200)], [], [{"mergedAt": "2027-01-15T07:30:00Z"}])
        self.assertEqual((r.returncode, r.stdout), (1, "ALARM flow: trunk red for 2.0h\n"))
        self.assertEqual(run(["symptom"], fail=True).returncode, 2)

    def test_split_prints_medians_and_largest(self):
        f = pathlib.Path(tempfile.mkdtemp(), "v.json")
        row = {"queuedAt": "2027-01-01T00:00:00Z", "startedAt": "2027-01-01T10:00:00Z",
               "readyAt": "2027-01-01T12:00:00Z", "mergedAt": "2027-01-01T13:00:00Z"}
        f.write_text(json.dumps([row, {"queuedAt": "2027-01-01T00:00:00Z"}]))
        r = run(["split", str(f)])
        self.assertEqual(r.returncode, 0)
        self.assertIn("waiting-to-start\tmedian_h=10.0", r.stdout)
        self.assertIn("largest\twaiting-to-start\trows=1", r.stdout)

    def test_split_bad_input_exit_2(self):
        f = pathlib.Path(tempfile.mkdtemp(), "v.json")
        f.write_text("[]")
        self.assertEqual(run(["split", str(f)]).returncode, 2)
        self.assertEqual(run(["bogus"]).returncode, 2)


class Gate(unittest.TestCase):
    """At the cap hook() denies a command that holds `gh pr create` (any case, also with its quotes and backslashes removed, in
    code, a comment or a heredoc body) unless every command in it is a known text tool. MENTION only names it. RUN runs it in a
    shape the old substring test (`OLD`, on the raw text) denied. PROBE runs or hides it in a shape that fooled a looser gate.
    RESIDUAL runs it and still passes (a documented gap). OVERDENY only names it and is denied anyway (the safe direction). The
    module's own pattern is `self.fa.MENTION`."""
    CMD = "gh pr create"
    OLD = re.compile(r"\bgh\s+pr\s+create\b")  # the substring test this gate replaced
    MENTION = [f"grep -rn '{CMD}' docs/", f"git log --grep '{CMD}'", f"echo '{CMD}'", f"git commit -m 'docs: explain {CMD}'",
               "grep 'gh pr creat[e]'",
               f"gh issue create --title x --body \"$(cat <<'EOF'\nThe agent ran {CMD} twice and was blocked.\nEOF\n)\"",
               f"git commit -m \"$(cat <<'EOF'\nit's a \"quoted\" note on {CMD}\nEOF\n)\"",
               f"gh issue create --title t --body-file - <<'EOF'\nUse {CMD} when ready\nEOF",
               f"gh pr comment 5 --body \"the {CMD} step\"", f"cd docs && grep -rn '{CMD}' . | head -n 5",
               f"rg -n '{CMD}' scripts", f"echo \"$(date) {CMD} blocked\"", f"echo a\\\\\\\n{CMD}",
               f"# note: {CMD} later\ngit status", f"git log --grep '{CMD}' 2>&1 | head -n 5",
               f"grep -rn '{CMD}' docs/ 2>/dev/null",
               f"git -C /repo log --grep '{CMD}'", f"git commit -m 'x' -m '{CMD}' 2>&1",
               f"echo '{CMD}' >&2", f"echo '{CMD}' >/dev/null 2>&1",
               f"git diff -- docs | grep '{CMD}'",
               f"git commit -m \"$(cat <<'EOF'\n# Title\nit's about {CMD}\nEOF\n)\"",
               f"echo $(cat <<EOF\nuse {CMD}\nEOF\n)", f"echo ok # {CMD} here\ngit status", f"echo ok # don't {CMD}\ngit status",
               f"echo \"# not a comment {CMD}\"",
               f"git add -A && git commit -m \"$(cat <<'EOF'\nfix: explain {CMD}\nEOF\n)\"",
               f"LC_ALL=C grep -rn '{CMD}' docs/", f"printf '%s\\n' '{CMD}' | head -n 1", f"echo \"${{HOME:-x}} {CMD}\"",
               f"git commit -am \"$(date): {CMD}\"", f"TZ=UTC NO_COLOR=1 git log --grep '{CMD}'",
               f"GIT_AUTHOR_NAME=a GIT_AUTHOR_EMAIL=a@example.com git commit -m 'on {CMD}'",
               f"echo '{CMD}'; gh pr view 5 --comments",
               "echo 'GH Pr Create'"]
    RUN = [f"{CMD} --title x", f"/usr/bin/{CMD} --title x", f"cd repo && {CMD} --title x", f"echo ok; {CMD} --title x",
           f"echo ok | {CMD} --title x", f"GH_HOST=example.com {CMD} --title x", f"env GH_HOST=example.com {CMD} --title x",
           f"bash -c '{CMD} --title x'", f"sh -lc '{CMD} --title x'", f'echo "$({CMD} --title x)"', f"url=$({CMD} --title x)",
           f"echo ok\n{CMD} --title x", f"git push -u origin x  # push\n{CMD} --title x", f"{CMD} \\\n  --title x",
           f"echo `{CMD}`", f'echo "`{CMD}`"', f">/dev/null {CMD} --fill", f"2>&1 {CMD}", f"< /dev/null {CMD}",
           f"timeout 600 {CMD}", f"nice -n 5 {CMD}", f"env -i PATH=/usr/bin {CMD}", f"sudo -u root {CMD}", f"time -p {CMD}",
           f"command -p {CMD}", f"exec -a x {CMD}", f"caffeinate -i {CMD}", f"python3 -c \"import os; os.system('{CMD}')\"",
           f"echo '{CMD}' | sh", f"ksh -c '{CMD}'", f"echo x;>f {CMD}", f"cat <({CMD} --fill)",
           f"diff a <({CMD})", f"bash <<EOF\n{CMD} --fill\nEOF", f"python3 - <<'EOF'\nimport os; os.system(\"{CMD}\")\nEOF",
           f"cat <<EOF | sh\n{CMD}\nEOF", f"cat <<EOF\n$({CMD})\nEOF", f"cat <<'EOF'\nnotes\nEOF\n{CMD}",
           f"gh -R o/r pr create && echo '{CMD}'", f"git config alias.x '!{CMD}'", f"git -c 'alias.x=!{CMD}' x",
           f"rg --pre '{CMD}' x", f'echo "$(echo $({CMD}))"', f"cat <<EOF\nnotes on {CMD}", f"echo 'unbalanced {CMD}",
           f"GIT_SSH_COMMAND='{CMD}' git fetch", f"echo a\\\\\n{CMD}", f"rg --hostname-bin '{CMD}' x"]
    NOT_SAFE = ["sed", "awk", "find", "xargs", "sort", "env", "timeout", "nice", "sudo", "exec", "command", "time", "nohup",
                "eval", "source", ".", "watch", "ssh", "sh", "bash", "zsh", "dash", "python3", "node",
                "perl", "ruby", "tee", "uniq"]
    # Each runs `gh pr create`, writes it where a later command runs it, or hides it from a gate that drops or joins text before it
    # parses. The first eleven came from review; the rest cover every step that drops or joins text.
    PROBE = [
        'gh pr "create" --fill', '"gh" pr create --fill', "g\\h pr create --fill", 'gh pr cre""ate --fill',
        "echo ok # <<EOF\ngh pr create --fill\nEOF", '"#"; gh pr create --fill', "echo a#b; gh pr create --fill",
        "git rebase --exec 'gh pr create --fill' HEAD~1", "git bisect run gh pr create --fill",
        "echo 'gh pr create --fill' > \"$TMPDIR/x.sh\"; bash \"$TMPDIR/x.sh\"",
        "echo 'gh pr create --fill' | tee \"$TMPDIR/x.sh\"; sh \"$TMPDIR/x.sh\"",
        # a `<<` that is not a heredoc: quoted, in a comment, in arithmetic, in a second operator, after an ANSI-C quote
        'echo "<<EOF"\ngh pr create --fill\nEOF', "echo $'x\\'' # it's <<EOF\ngh pr create --fill\nEOF",
        'cat <<A "<<B"\nx\nA\ngh pr create --fill\nB', 'echo "$(echo ok # <<EOF\ngh pr create --fill\nEOF\n)"',
        "echo $((1<<2))\ngh pr create --fill\n2", "echo $[1<<2]\ngh pr create --fill\n2]",
        "echo $[1 <<2 ]\ngh pr create --fill\n2",
        "a[1<<2 ]=5\ngh pr create --fill\n2",
        # a delimiter that is not one whole word, or a body line that hides the delimiter
        "cat <<'EOF'\nx \\\nEOF\ngh pr create --fill\nEOF", 'cat <<E"O"F\nx\nEOF\ngh pr create --fill\nE',
        "cat <<'E'\"O\"\nx\nEO\ngh pr create --fill\nE",
        # a heredoc inside `$(` that a shell may end early, or a command that follows its body
        'echo "$(cat <<\'EOF\'\nx\nEOF\ngh pr create --fill\n)"', "echo $(cat <<EOF)\ngh pr create --fill\nEOF",
        'echo "$(cat <<EOF)"\ngh pr create --fill\nEOF', "echo $(cat <<EOF\n)\ngh pr create --fill\nEOF",
        "echo $(cat <<EOF )\ngh pr create --fill\nEOF", "echo ')' $(cat <<EOF)\ngh pr create --fill\nEOF",
        "echo $(echo ')' ; cat <<EOF)\ngh pr create --fill\nEOF", "echo $(cat <<'EOF'\nbody )\ngh pr create --fill\nEOF\n)",
        # an operator line that opens a `$(`, `<(`, backtick, `(` or quote after the marker: the shell reads it across the body
        # lines, so the body starts later (the last one is zsh; bash calls it a syntax error)
        "cat <<EOF $(echo\ngh pr create --fill\nEOF\n)", "cat <<'EOF' <(echo\ngh pr create --fill\nEOF\n)",
        "cat <<'EOF' `echo\ngh pr create --fill\nEOF\n`", "<<EOF( <(\n)) >&2 gh pr create --fill @\nEOF",
        "cat <<'EOF' \"x\ny\"; gh pr create --fill; echo \"\nEOF\nz\"",
        # a delimiter word whose backslash the shell removes, so its delimiter line is not the one the text spells
        "cat <<E\\OF\nx\nEOF\ngh pr create --fill\nE\\OF", "cat <<\\EOF\nx\nEOF\ngh pr create --fill\n\\EOF",
        'cat <<"E\\\\F"\nx\nE\\F\ngh pr create --fill\nE\\\\F',
        # an unquoted backtick: its output runs as the command
        "`echo gh pr create --fill`", "`echo gh pr create --fill` >/dev/null 2>&1",
        # a `#` that does not start a comment, or a comment that does not swallow the next line
        "echo ok # x \\\ngh pr create --fill", "echo ok # x\ngh pr create --fill", "echo ' #'; gh pr create --fill",
        "echo a\\ #b; gh pr create --fill", "echo ${x:- # y}; gh pr create --fill", "echo `true # x` ; gh pr create --fill",
        "echo 'a\n# b'; gh pr create --fill", "echo $'x' # y \\\ngh pr create --fill", "echo ok #c\\\ngh pr create --fill",
        "echo a;#c\ngh pr create --fill",
        # git running a command
        "git rebase -x 'g\\h pr create --fill' HEAD~1", "git -C . bisect run gh pr create --fill",
        "git submodule foreach 'gh pr create --fill'", "git grep -O 'gh pr create --fill' x",
        "git --git-dir . rebase --exec 'gh pr create --fill' HEAD~1",
        # `create` spelled by an expansion, an option that runs a command, a redirect after a newline, ANSI-C quoting
        "gh pr create$x", "gh pr create${x}", "gh pr create$(true)", "gh pr create{,} --fill", "gh pr create* --fill",
        "gh pr create$x\nprintf }\n", "git log\n>true gh pr create ", "grep fi$'\\''\ngh pr create --fill\n: echo 'echo ",
        "git grep -nO'gh pr create --fill' x", "o=O; git grep -n${o}'gh pr create --fill' x",
        "gh config set pager 'gh pr create --fill'",
        # naming it while writing a file
        "echo 'gh pr create --fill' >> run.sh", "printf 'gh pr create' &> run.sh", "echo 'gh pr create' | cat > x.sh",
        "git log --grep 'gh pr create' > out.txt",
        # a real run after a command that only names it
        "git commit -m 'x' && gh pr create --fill", "git commit -m \"$(cat <<'EOF'\nx\nEOF\n)\" && gh pr create --fill",
        "echo \"$(cat <<'EOF'\nx\nEOF\n)\"; gh pr create --fill",
        # a config, alias or hook that git, gh or rg then runs, written beside a heredoc body that holds the text, by a git option
        # (`--output`) or by a git subcommand that reads a patch on stdin
        "cat >> .git/config <<'EOF'\n[alias]\n\tx = !gh pr create --fill\nEOF\ngit x",
        "cat > gc <<EOF\n[alias]\n\tx = !gh pr create --fill\nEOF\nGIT_CONFIG_GLOBAL=gc git x",
        "cat <<'EOF' > gc\n[alias]\n\tx = !gh pr create --fill\nEOF\nGIT_CONFIG_GLOBAL=gc git x",
        "cat > gc <<'EOF'\n[core]\n\tfsmonitor = gh pr create --fill\nEOF\nGIT_CONFIG_GLOBAL=gc git status",
        "cat <<'EOF' > cfg\n--pre=sh\nEOF\ncat > s.sh <<'EOF'\ngh pr create --fill\nEOF\nRIPGREP_CONFIG_PATH=cfg rg x s.sh",
        "git log -1 --format='[alias]%n%x09x = !gh pr create --fill' --output=gc; GIT_CONFIG_GLOBAL=gc git x",
        "git show -s --format='[alias]%n%x09x = !gh pr create --fill' --output=.git/config; git x",
        "git log -1 --format='diff --git a/gc b/gc%nnew file mode 100644%n--- /dev/null%n+++ b/gc%n@@ -0,0 +1,2 @@%n+[alias]"
        "%n+%x09x = !gh pr create --fill' | git apply; GIT_CONFIG_GLOBAL=gc git x",
        "cat <<'EOF' | git apply\ndiff --git a/gc b/gc\nnew file mode 100644\n--- /dev/null\n+++ b/gc\n@@ -0,0 +1,2 @@\n"
        "+[alias]\n+\tx = !gh pr create --fill\nEOF\nGIT_CONFIG_GLOBAL=gc git x",
        # a variable that git runs (an editor, a config entry, an external diff), spelled by an expansion so that no word holds the
        # text: set by an assignment, by `printf -v` or by `${NAME:=cmd}`; the mention beside it is what the old test denied
        "echo gh pr create; GIT_EDITOR=\"$(echo gh) pr create\" git commit --allow-empty",
        "echo gh pr create; GIT_EXTERNAL_DIFF=\"$(echo gh) pr create\" git diff --cached",
        "echo gh pr create; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0=\"$(echo gh) pr create\" "
        "git status",
        "echo gh pr create; GIT_EDITOR=\"${X:-gh} pr create\" git commit --allow-empty",
        "echo gh pr create; GIT_EDITOR=\"`echo gh` pr create\" git commit --allow-empty",
        "echo gh pr create; X=gh; EDITOR=\"$X pr create\"; git commit --allow-empty",
        "echo gh pr create; GIT_EDITOR='$A $B create' A=gh B=pr git commit --allow-empty",
        "echo gh pr create; ( EDITOR=\"$(echo gh) pr create\"; git commit --allow-empty )",
        "echo gh pr create; printf -v EDITOR 'gh pr create'; git commit --allow-empty",
        "echo gh pr create; printf {-v,EDITOR} 'gh pr create'; git commit --allow-empty",
        "echo gh pr create; o=-v; printf $o EDITOR 'gh pr create'; git commit --allow-empty",
        "echo gh pr create; echo ${EDITOR:=gh pr create}; git commit --allow-empty",
        # `--output=FILE` writes the mention as a config that git runs later, spelled by an expansion (no word starts with it)
        "git commit -q --allow-empty -m i; o=--output=gc; git log -1 --format='[core]%n%x09fsmonitor = gh pr create --fill' "
        "$o; GIT_CONFIG_GLOBAL=gc git status",
        "git commit -q --allow-empty -m i; git log -1 --format='[core]%n%x09fsmonitor = gh pr create --fill' "
        "\"$(echo --output=gc)\"; GIT_CONFIG_GLOBAL=gc git status",
        "git commit -q --allow-empty -m i; git log -1 --format='[core]%n%x09fsmonitor = gh pr create --fill' "
        "$(echo --output=gc); GIT_CONFIG_GLOBAL=gc git status",
        "git commit -q --allow-empty -m i; x=--output=gc; git show -s --format='[core]%n%x09fsmonitor = gh pr create --fill' "
        "\"$x\"; GIT_CONFIG_GLOBAL=gc git status",
        "git commit -q --allow-empty -m i; git log -1 --format='[core]%n%x09fsmonitor = gh pr create --fill' -m "
        "\"$(echo --output=gc)\"; GIT_CONFIG_GLOBAL=gc git status",
        "git commit -q --allow-empty -m i; git log -1 --format='[core]%n%x09fsmonitor = gh pr create --fill' {--output=gc,}; "
        "GIT_CONFIG_GLOBAL=gc git status",
        # a continuation inside the text; `create` after flags, its alias `new`, `gh api`: each ran a stub gh beside a mention
        "gh \\\npr create", "echo 'gh pr create'; gh pr new --fill", "gh pr new --fill # gh pr create",
        "echo 'gh pr create'; gh -R o/r pr new --fill", "echo 'gh pr create'; gh pr -R o/r create --fill",
        "echo 'gh pr create'; gh pr --repo=o/r create --fill", "echo 'gh pr create'; gh pr -t x create --fill",
        "gh pr --repo=o/r create --fill # gh pr create", "echo 'gh pr create'; gh api -X POST repos/o/r/pulls -f title=x",
        # a variable that git runs, set beside a mention (an editor, a config entry, an external diff)
        "echo 'gh pr create'; GIT_EXTERNAL_DIFF='gh pr new --fill;:' git log -p --ext-diff",
        "echo 'gh pr create'; GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=core.fsmonitor GIT_CONFIG_VALUE_0='gh pr new --fill;:' "
        "git status",
        "echo 'gh pr create'; GIT_EDITOR='gh pr new --fill;:' git commit --allow-empty",
        # the mention only in a comment: it counts as the text for a git subcommand outside the read set and for a file write
        "printf 'gh pr cre%s --fill\\n' ate > x.sh; git rebase --exec 'sh x.sh' HEAD~1 # gh pr create",
        "git rebase --exec 'gh pr new --fill;:' HEAD~1 # gh pr create",
        "GIT_SEQUENCE_EDITOR='gh pr new --fill;:' git rebase -i HEAD~1 # gh pr create",
        "FILTER_BRANCH_SQUELCH_WARNING=1 git filter-branch --tree-filter 'gh pr new --fill;:' HEAD # gh pr create",
        "git bisect start HEAD HEAD~1 >/dev/null; git bisect run gh pr new --fill # gh pr create",
        "GD='gh pr new --fill;:' git --config-env=core.fsmonitor=GD status # gh pr create",
        "# gh pr create\ng=gh; printf '[core]\\n\\tfsmonitor = %s pr create;:\\n' \"$g\" > gc; GIT_CONFIG_GLOBAL=gc git status",
        "# gh pr create\ncat > gc <<'EOF'\n[core]\n\tfsmonitor = gh pr new --fill;:\nEOF\nGIT_CONFIG_GLOBAL=gc git status",
        # a command word that is a path, another case, a comment beside a heredoc
        "echo 'gh pr create'; ./echo gh pr create --fill", "GH pr create --fill", "Gh Pr Create --fill", "$GH pr create --fill",
        "cat <<'EOF' # note\ngh pr create --fill\nEOF"]
    # Known gaps: the text `gh pr create` is not in the command, so nothing here is gated.
    RESIDUAL = ["${GH} pr create --fill", "$(which gh) pr create --fill", "gh${IFS}pr create --fill", "gh $'pr' create --fill",
                "gh pr cre{a,}te --fill"]
    # Only name it, and are denied anyway: a single-quoted backtick, a pipeline through a command outside SAFE, a git subcommand
    # outside the read and record set beside a mention (also one only in a comment), a file written beside a mention (also one
    # only in a heredoc body), a comment beside a heredoc, a quoted `#` before a heredoc, a `)` in a heredoc body inside `$(`,
    # a `(` after the marker, a backslash in the delimiter word, a `gh` whose first two words hold `{` (its own `{owner}`
    # placeholder), an expansion after `gh pr`, an assignment of a variable that is not inert, a `printf` with an option, an
    # expansion that assigns, an expansion in a git word, a command word that is a path, and two that ran nothing in a stub:
    # a forced pager and a config fed to git as a stream.
    OVERDENY = [f"echo 'run `{CMD}` later'", f"echo '{CMD}' | sed 's/x/y/'", f"git tag -m '{CMD}' v1",
                f"echo '#'; cat <<EOF\nuse {CMD}\nEOF", f"git commit -m \"$(cat <<'EOF'\nfix (scope) of {CMD}\nEOF\n)\"",
                f"cat <<'EOF' | grep -E '(a|b)'\nuse {CMD}\nEOF", f"cat <<\\EOF\nuse {CMD}\nEOF",
                f"gh api repos/{{owner}}/{{repo}}/issues -f body='use {CMD}'", f"git push origin x && echo '{CMD}'",
                f"cat > notes.md <<'EOF'\nuse {CMD}\nEOF\ngit add notes.md", f"X=$(date +%s) git log --grep '{CMD}'",
                f"printf -v x '%s' '{CMD}'; echo \"$x\"", f"echo \"${{x:=1}} {CMD}\"",
                f"git log \"$base\"..HEAD --grep '{CMD}'", f"git -C \"$PWD\" log --grep '{CMD}'",
                f"git push # then {CMD} later", f"cat > notes.md <<'EOF'\nit's how {CMD} works\nEOF",
                f"cat > notes.md <<'EOF'\n# Heading\nuse {CMD}\nEOF", f"cat > notes.md <<'EOF'\nsee (use {CMD})\nEOF",
                f"echo a # \\\ncat <<EOF\nuse {CMD}\nEOF", f"cat <<'EOF' # note\nuse {CMD}\nEOF",
                f"gh pr comment 5 --body \"$(date) {CMD}\"", f"/bin/echo '{CMD}'", f"git -p log # {CMD}",
                f"X=1 git log --grep '{CMD}'",
                f"printf '[core]\\n\\tfsmonitor = {CMD}\\n' | GIT_CONFIG_GLOBAL=/dev/stdin git status"]

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("fa_gate", SCRIPT)
        cls.fa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.fa)

    def rc(self, cmd, ready):
        """The hook's exit code for `cmd` with `ready` ready-but-unmerged PRs (open_prs stubbed, cap 5; git stubbed to fail, so
        a denied command is never judged as throughput work and no denial log is written)."""
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
        with mock.patch.object(self.fa, "open_prs", lambda timeout=60: [GREEN] * ready), \
                mock.patch.object(self.fa, "_git", side_effect=OSError), mock.patch("sys.stdin", stdin), \
                mock.patch.dict(os.environ, {"PERUN_STOP_STARTING_READY": "5"}), mock.patch("sys.stderr", io.StringIO()):
            return self.fa.hook()

    def test_a_command_that_only_mentions_it_passes_at_the_cap(self):
        for c in self.MENTION:
            self.assertEqual(self.rc(c, 5), 0, c)

    def test_a_command_the_old_substring_test_denied_is_still_denied_at_the_cap(self):
        for c in self.RUN:
            self.assertTrue(self.OLD.search(c), c)  # the old test, run on the raw text, denied it
            self.assertEqual(self.rc(c, 5), 2, c)

    def test_a_shape_that_hides_or_runs_it_is_denied_at_the_cap(self):
        for c in self.PROBE:
            self.assertTrue(self.fa._holds(c), c)  # the precheck lets it reach the parser, even when quotes or backslashes hide it
            self.assertEqual(self.rc(c, 5), 2, c)

    def test_a_program_outside_the_allowlist_is_denied_and_a_listed_one_may_name_it(self):
        for w in self.NOT_SAFE:
            self.assertEqual(self.rc(f"{w} {self.CMD}", 5), 2, w)
        for w in sorted(self.fa.SAFE - {"git"}):  # git is listed too, but only for read and record subcommands: next test
            self.assertEqual(self.rc(f"{w} '{self.CMD}'", 5), 0, w)

    def test_git_may_name_it_only_in_a_read_or_record_subcommand(self):
        for sub in sorted(self.fa.GIT_READ):
            for pre in ("git", "git -C /repo"):
                self.assertEqual(self.rc(f"{pre} {sub} '{self.CMD}'", 5), 0, f"{pre} {sub}")
        for sub in ("rebase -x", "rebase --exec", "bisect run", "submodule foreach", "tag -m", "push --receive-pack", "stash",
                    "config alias.x", "-c alias.x=x log", "-C . rebase -x", "--git-dir . rebase -x", "-p log",
                    "--config-env=core.fsmonitor=X status"):
            self.assertEqual(self.rc(f"git {sub} '{self.CMD}'", 5), 2, sub)
        # git may also write the file that a later git runs (`--output`, a patch on stdin): any such git beside the text denies
        for c in (f"git log --output=x '{self.CMD}'", f"git apply && echo '{self.CMD}'", f"echo '{self.CMD}' | git apply"):
            self.assertEqual(self.rc(c, 5), 2, c)

    def test_a_command_that_names_it_and_writes_a_file_is_denied_but_a_redirect_to_a_stream_is_not(self):
        for w in ("> x.sh", ">> x.sh", "&> x.sh", ">| x.sh", "2> err.txt", "| cat > x.sh", "| tee x.sh"):
            self.assertEqual(self.rc(f"echo '{self.CMD}' {w}", 5), 2, w)
        for w in ("2>&1", ">&2", ">/dev/null", "2>/dev/null", ">/dev/null 2>&1"):
            self.assertEqual(self.rc(f"echo '{self.CMD}' {w}", 5), 0, w)

    def test_the_documented_residuals_still_pass_at_the_cap(self):
        for c in self.RESIDUAL:
            self.assertFalse(self.fa._holds(c), c)  # the text is not in the command, so the gate never looks
            self.assertEqual(self.rc(c, 5), 0, c)
        # a `gh` alias or extension that already exists runs under its own name: nothing in the command spells `pr create`
        c = f"echo '{self.CMD}'; gh newpr --fill"
        self.assertEqual(self.rc(c, 5), 0, c)

    def test_a_variable_set_before_a_command_must_have_an_inert_name(self):
        for name in ("GIT_EXTERNAL_DIFF", "GIT_EDITOR", "GIT_SEQUENCE_EDITOR", "GIT_PAGER", "GIT_CONFIG_COUNT",
                     "GIT_CONFIG_GLOBAL", "GIT_SSH_COMMAND", "PAGER", "EDITOR", "VISUAL", "GH_BROWSER",
                     "RIPGREP_CONFIG_PATH", "X"):
            self.assertEqual(self.rc(f"{name}=x git log --grep '{self.CMD}'", 5), 2, name)
        for name in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_AUTHOR_DATE", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL",
                     "GIT_COMMITTER_DATE", "LANG", "LC_ALL", "LC_CTYPE", "TZ", "NO_COLOR"):
            self.assertEqual(self.rc(f"{name}=x git log --grep '{self.CMD}'", 5), 0, name)

    def test_the_documented_over_denies_stay_on_the_safe_side(self):
        for c in self.OVERDENY:
            self.assertEqual(self.rc(c, 5), 2, c)

    def test_text_without_the_command_is_never_gated_even_when_it_does_not_parse(self):
        self.assertEqual(self.rc("echo 'unbalanced and no mention", 5), 0)

    def test_every_shape_passes_under_the_cap(self):
        for c in self.MENTION + self.RUN + self.PROBE + self.RESIDUAL + self.OVERDENY:
            self.assertEqual(self.rc(c, 4), 0, c)

    def test_priority_override_still_passes_at_the_cap(self):
        self.assertEqual(self.rc(f"{self.CMD} --title x # priority: red trunk fix", 9), 0)


class Throughput(unittest.TestCase):
    """At the cap one lone `gh pr create` of a branch pushed to origin whose every changed file is a throughput path passes while
    fewer than PERUN_THROUGHPUT_OPEN exempt PRs are open (ledger branches among the open PRs' head names); every other deny stands
    and is logged by class: `work` for anything not judged or not throughput-only, `throughput-cap` when only the exempt cap blocked.
    The repo has `src/app.py` on `main`, with `origin/main` and `origin/HEAD` at it (no remote configured unless a test adds one), so a
    branch has a real merge base; `branch()` also points `origin/<name>` at its commit (the push). `work()` and `grant()` run the hook
    and assert the verdict."""
    FILES = {"tests/test_a.py": "x\n", ".github/workflows/ci.yml": "on: push\n"}
    URL = "https://example.com/example-owner/repo.git"  # a fictional remote: nothing is fetched

    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("fa_throughput", SCRIPT)
        cls.fa = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.fa)

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.repo = pathlib.Path(tmp.name, "repo")
        (self.repo / "src").mkdir(parents=True)
        git(self.repo, "init", "-q")
        git(self.repo, "symbolic-ref", "HEAD", "refs/heads/main")
        (self.repo / "src/app.py").write_text("x = 1\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "init")
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/main")

    def create(self, cmd="gh pr create --title x", heads=(), ready=5, cwd=None, env=None):
        """The hook run on `cmd` in `cwd` (default the repo), with `ready` ready PRs open, the first ones named `heads`."""
        prs = [{**GREEN, "headRefName": h} for h in heads] + [GREEN] * (ready - len(heads))
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": str(cwd or self.repo)})
        return run([], prs, stdin=stdin, env=env)

    def lines(self, name):
        """The JSON lines of a file in the repo's git dir ([] when it does not exist)."""
        f = self.repo / ".git" / name
        return [json.loads(line) for line in f.read_text().splitlines()] if f.exists() else []

    def seed(self, *branches):
        """Write a ledger that holds a grant for each of `branches`."""
        (self.repo / ".git" / LEDGER).write_text("".join(json.dumps({"branch": b, "at": 1}) + "\n" for b in branches))

    def work(self, cmd="gh pr create --title x", **kw):
        """Run the hook on `cmd`; assert it is denied as class `work` (exit 2, one new denial, no new grant); return the process."""
        denials, grants = self.lines(DENIALS), self.lines(LEDGER)
        p = self.create(cmd, **kw)
        self.assertEqual(p.returncode, 2, cmd)
        self.assertEqual([d["class"] for d in self.lines(DENIALS)[len(denials):]], ["work"], cmd)
        self.assertEqual(self.lines(LEDGER), grants, cmd)
        return p

    def grant(self, cmd="gh pr create --title x", **kw):
        """Run the hook on `cmd`; assert it passes silently and appends one ledger line, which is returned."""
        grants = self.lines(LEDGER)
        p = self.create(cmd, **kw)
        self.assertEqual((p.returncode, p.stderr), (0, ""), cmd)
        new = self.lines(LEDGER)[len(grants):]
        self.assertEqual(len(new), 1, cmd)
        return new[0]

    def release(self):
        """`origin/release` stays at the init commit while `origin/main` moves on by a product file; the pushed `t1` is test-only
        against main (the default base) but not against release."""
        git(self.repo, "update-ref", "refs/remotes/origin/release", "HEAD")
        branch(self.repo, "m2", {"src/new.py": "x\n"}, push=False)
        git(self.repo, "update-ref", "refs/remotes/origin/main", "HEAD")
        branch(self.repo, "t1", self.FILES)

    def stacked(self):
        """`origin/tb` carries a product file and the pushed `t1` is test-only on top of it: judged against `tb` it passes, against
        main (the default base) it does not."""
        branch(self.repo, "tb", {"src/lib.py": "x\n"})
        branch(self.repo, "t1", self.FILES, base="origin/tb")

    def test_a_test_only_branch_passes_at_the_cap_and_is_recorded(self):
        branch(self.repo, "t1", self.FILES)
        p = self.create()
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertEqual(self.lines(LEDGER), [{"branch": "t1", "at": NOW}])
        self.assertEqual(self.lines(DENIALS), [])

    def test_a_branch_with_a_product_file_is_denied_as_work(self):
        branch(self.repo, "p1", {**self.FILES, "src/app.py": "x = 2\n"})
        p = self.create()
        self.assertEqual(p.returncode, 2)
        self.assertIn("5 ready-but-unmerged", p.stderr)
        self.assertIn("Queue-throughput work (only test or CI paths changed) passes as a lone `gh pr create` (body in `--body-file`) of "
                      "a branch already pushed to origin, while fewer than 2 such PRs are open. Priority work:", p.stderr)
        self.assertEqual(self.lines(DENIALS), [{"at": NOW, "class": "work", "ready": 5, "cap": 5}])
        self.assertEqual(self.lines(LEDGER), [])

    def test_a_product_file_moved_into_tests_is_still_a_product_change(self):
        git(self.repo, "checkout", "-q", "--no-track", "-b", "mv1", "origin/main")
        (self.repo / "tests").mkdir()
        git(self.repo, "mv", "src/app.py", "tests/app.py")  # a rename: git lists only the new path unless told not to detect it
        git(self.repo, "commit", "-q", "-m", "mv")
        git(self.repo, "update-ref", "refs/remotes/origin/mv1", "HEAD")  # pushed: the diff is the only reason to deny
        self.work()

    def test_an_empty_diff_keeps_the_deny(self):
        self.work()  # HEAD is origin/main: nothing to judge
        git(self.repo, "checkout", "-q", "--no-track", "-b", "e1", "origin/main")
        git(self.repo, "commit", "-q", "--allow-empty", "-m", "e1")
        git(self.repo, "update-ref", "refs/remotes/origin/e1", "HEAD")
        self.work()  # pushed as itself, but it changes no file

    def test_the_exempt_cap_denies_the_next_test_only_branch(self):
        self.seed("ex1", "ex2")
        branch(self.repo, "t3", self.FILES)
        p = self.create(heads=["ex1", "ex2"])
        self.assertEqual(p.returncode, 2)
        self.assertEqual(self.lines(DENIALS), [{"at": NOW, "class": "throughput-cap", "ready": 5, "cap": 5}])
        self.assertEqual(len(self.lines(LEDGER)), 2)  # nothing recorded for the denied branch
        self.assertEqual(self.create(heads=["ex1", "ex2"], env={"PERUN_THROUGHPUT_OPEN": "3"}).returncode, 0)
        self.assertEqual([e["branch"] for e in self.lines(LEDGER)], ["ex1", "ex2", "t3"])

    def test_a_ledger_branch_that_is_not_open_does_not_count(self):
        self.seed("ex1", "ex2")  # ex2 has merged: it is not among the open PRs
        branch(self.repo, "t3", self.FILES)
        # ex1 is open and in the ledger; "feature" is open but never had a grant: one exempt PR, under the cap of 2
        self.assertEqual(self.create(heads=["ex1", "feature"]).returncode, 0)
        self.assertEqual(self.lines(DENIALS), [])

    def test_a_pr_for_another_head_or_repo_keeps_the_deny(self):
        branch(self.repo, "t1", self.FILES)
        self.grant()  # the same branch with no such option
        for opt in ("--head x", "--head=x", "-H x", "-fH x", "-Hx", "-R x/y", "-Rx/y", "-dR x/y", "--repo x/y", "--repo=x/y"):
            self.work(f"gh pr create --title t {opt}")
        self.work("GH_REPO=x/y gh pr create --title t")  # a variable in front is a word before `gh`: not judged

    def test_unjudged_words_are_options_expansions_and_comments(self):
        for tok in ("-R", "-H", "--repo", "--repo=x", "--head", "--head=x", "-fH", "-dB", "-dR", "-Brelease", "-B=x", "-fix", "-Hx",
                    "#12", "$X", "a$b", "a`b", "{--base=main,}", "{a}", "x{a,b}", "--*", "*", "?", "-?", "[x]", "a*b", "Why?"):
            self.assertTrue(self.fa.UNJUDGED(tok), tok)
        for tok in ("--title", "Head of queue", "-f", "-d", "--fill", "--draft", "--base", "-B", "--base=main", "--body-file", "main",
                    "x-H", "- item", "Fix #12", "-", "-1", "a-dB"):
            self.assertFalse(self.fa.UNJUDGED(tok), tok)

    def test_the_base_comes_from_the_command_and_the_last_one_wins(self):
        branch(self.repo, "other", {"src/lib.py": "x\n"})
        branch(self.repo, "t1", self.FILES, base="origin/other")  # test-only against `other`, product files against main
        self.work()
        for opt in ("--base other", "--base=other", "-B other", "--base main --base other", "-B main --base=other"):
            self.grant(f"gh pr create --title x {opt}")
        for opt in ("--base other --base main", "--base=other -B main", "--base nope"):
            self.work(f"gh pr create --title x {opt}")  # the flag parser keeps the last; a base that does not exist: git fails

    def test_a_base_option_without_a_value_keeps_the_deny(self):
        self.release()
        self.grant()  # the default base, where the branch is test-only
        for opt in ("--base", '--base ""', "--base=", "-B"):
            self.work(f"gh pr create --title x {opt}")  # not read as "no base": the diff against `origin/` fails

    def test_a_bundled_or_joined_option_is_not_judged(self):
        self.release()
        self.grant()  # test-only against main, the default base
        for opt in ("-dB release", "-fdB release", "-dB main", "-Brelease", "-Bmain", "-B=main", "-dBmain"):
            self.work(f"gh pr create --title x {opt}")  # `-dB release` opens against release; `-Bmain`, joined, is not read as a base

    def test_a_git_that_fails_keeps_the_deny(self):
        branch(self.repo, "t1", self.FILES)
        plain = self.repo.parent / "plain"
        plain.mkdir()
        self.assertEqual(self.create(cwd=plain).returncode, 2)  # not a repo
        self.assertEqual(self.create("gh pr create --base nope").returncode, 2)  # a base that does not exist
        self.assertEqual(self.create("gh pr create --base main").returncode, 0)  # the same branch with a base that does
        git(self.repo, "symbolic-ref", "--delete", "refs/remotes/origin/HEAD")
        self.assertEqual(self.create().returncode, 2)  # no default base
        self.assertEqual([d["class"] for d in self.lines(DENIALS)], ["work", "work"])  # none for the dir that is not a repo

    def test_a_git_that_times_out_keeps_the_deny(self):
        seen = []

        def hang(cmd, **kw):
            seen.append(kw["timeout"])
            raise subprocess.TimeoutExpired(cmd, kw["timeout"])
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create"}, "cwd": str(self.repo)}))
        with mock.patch.object(self.fa, "open_prs", lambda timeout=60: [GREEN] * 5), mock.patch.object(self.fa.subprocess, "run", hang), \
                mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()) as err:
            self.assertEqual(self.fa.hook(NOW), 2)
        self.assertIn("Blocked `gh pr create`", err.getvalue())
        self.assertEqual(set(seen), {5})  # every git call is bounded at 5 s

    def test_any_error_while_judging_keeps_the_deny(self):
        branch(self.repo, "t1", self.FILES)
        (self.repo / ".git" / LEDGER).write_text("not json\n")
        self.assertEqual(self.create().returncode, 2)  # an unreadable ledger
        self.seed()
        self.assertEqual(self.create(env={"PERUN_THROUGHPUT_OPEN": "many"}).returncode, 2)  # a cap that is not a number
        self.assertEqual(self.create().returncode, 0)  # the same branch, once nothing is wrong
        self.assertEqual([d["class"] for d in self.lines(DENIALS)], ["work", "work"])

    def test_the_path_list_comes_from_the_env_and_replaces_the_default(self):
        env = {"PERUN_THROUGHPUT_PATHS": "scripts/ci/*, bench/*"}  # blanks around a glob are dropped
        branch(self.repo, "s1", {"scripts/ci/run.sh": "x\n", "bench/b.py": "x\n"})
        self.assertEqual(self.create(env=env).returncode, 0)
        self.assertEqual(self.create().returncode, 2)  # not in the default list
        branch(self.repo, "d1", self.FILES)
        self.assertEqual(self.create(env=env).returncode, 2)  # the default list is replaced, not extended
        self.assertEqual(self.create(env={"PERUN_THROUGHPUT_PATHS": ""}).returncode, 2)  # an empty list exempts nothing

    def test_the_default_globs(self):
        globs = self.fa.THROUGHPUT.split(",")
        for path in ("tests/a.py", "src/test/a.py", "web/__tests__/a.js", "e2e/login.ts", "spec/a_spec.rb", "src/a.test.ts",
                     "web/a.spec.ts", "pkg/a_test.go", "scripts/test_a.py", "pkg/conftest.py", ".github/workflows/ci.yml",
                     ".gitlab-ci.yml", ".circleci/config.yml", ".buildkite/pipeline.yml", "playwright.config.ts",
                     "web/jest.config.js", "vitest.config.mts", "pytest.ini"):
            self.assertTrue(self.fa._is_throughput(path, globs), path)
        for path in ("src/app.py", "src/test_data/a.py", "test_dir/x.py", "latest/a.py", "testing/a.py", "contest.py",
                     "docs/guide.md", "package.json", ".github/CODEOWNERS", "src/testsuite.py"):
            self.assertFalse(self.fa._is_throughput(path, globs), path)

    def test_below_the_cap_and_a_priority_marker_pass_untouched(self):
        branch(self.repo, "p1", {"src/app.py": "x = 2\n"})
        self.assertEqual(self.create(ready=4).returncode, 0)
        self.assertEqual(self.create("gh pr create --title x # priority: red trunk fix", ready=9).returncode, 0)
        self.assertEqual(self.create("gh pr list", ready=9).returncode, 0)
        self.assertEqual((self.lines(LEDGER), self.lines(DENIALS)), ([], []))

    def test_the_ledger_is_in_the_common_dir_for_a_subdirectory_and_a_linked_worktree(self):
        branch(self.repo, "t1", self.FILES)
        self.assertEqual(self.create(cwd=self.repo / "tests").returncode, 0)  # git prints the common dir relative to the subdirectory
        wt = self.repo.parent / "wt"
        git(self.repo, "worktree", "add", "-q", "--no-track", "-b", "t2", str(wt), "origin/main")
        (wt / "tests").mkdir()
        (wt / "tests/test_w.py").write_text("x\n")
        git(wt, "add", "-A")
        git(wt, "commit", "-q", "-m", "t2")
        git(wt, "update-ref", "refs/remotes/origin/t2", "HEAD")
        self.assertEqual(self.create(cwd=wt).returncode, 0)
        self.assertEqual([e["branch"] for e in self.lines(LEDGER)], ["t1", "t2"])

    def test_without_a_cwd_in_the_hook_json_the_process_cwd_is_used(self):
        branch(self.repo, "t1", self.FILES)
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create"}})
        self.assertEqual(run([], [GREEN] * 5, stdin=stdin, cwd=self.repo).returncode, 0)
        self.assertEqual(self.lines(LEDGER), [{"branch": "t1", "at": NOW}])

    def test_a_denial_log_that_cannot_be_written_is_ignored(self):
        (self.repo / ".git" / DENIALS).mkdir()  # a directory: opening it for append fails
        p = self.create()
        self.assertEqual(p.returncode, 2)
        self.assertIn("Blocked `gh pr create`", p.stderr)

    def test_the_queue_is_one_gh_call_that_also_names_the_heads(self):
        calls = []

        def fake(*a, timeout=60):
            calls.append(a)
            return [{**GREEN, "headRefName": "t1"}] * 5
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create"}}))
        with mock.patch.object(self.fa, "gh_json", fake), mock.patch.object(self.fa, "_git", side_effect=OSError), \
                mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()):
            self.assertEqual(self.fa.hook(NOW), 2)
        self.assertEqual(len(calls), 1)
        self.assertIn("headRefName", calls[0][-1])

    def test_a_command_with_more_than_one_command_in_it_is_not_judged(self):
        self.stacked()
        self.grant("gh pr create --title x --base tb")  # judged against tb: test-only
        for cmd in ("gh pr create --title a --base tb && gh pr create --title b",  # the second create has the default base
                    "gh pr list --base tb && gh pr create --title x", "echo hi; gh pr create --title x --base tb",
                    "gh pr create --title x --base tb;", "gh pr create --title x --base tb | cat", "gh pr create --title x --base tb &",
                    "gh pr create --title x --base tb > /tmp/out", "(gh pr create --title x --base tb)",
                    "gh pr create --title x --base tb\necho done", "gh pr create --title x --base tb 2>&1"):
            self.work(cmd)

    def test_a_word_in_front_of_gh_is_not_judged(self):
        self.stacked()
        for cmd in ("X=1 gh pr create --title x --base tb", "time gh pr create --title x --base tb",
                    "command gh pr create --title x --base tb", "env gh pr create --title x --base tb",
                    "/usr/bin/gh pr create --title x --base tb"):
            self.work(cmd)

    def test_a_branch_switch_or_push_before_the_create_is_not_judged(self):
        branch(self.repo, "p", {"src/lib.py": "x\n"})
        branch(self.repo, "t1", self.FILES)  # HEAD is test-only; the command would open the PR from `p`
        self.grant()
        for cmd in ("git checkout -q p && gh pr create --title x", "git switch -q p && gh pr create --title x",
                    "git push -q origin p && gh pr create --title x", "cd /elsewhere && gh pr create --title x"):
            self.work(cmd)

    def test_an_expansion_a_substitution_or_a_heredoc_is_not_judged(self):
        branch(self.repo, "p", {"src/lib.py": "x\n"})
        branch(self.repo, "t1", self.FILES)
        self.grant()
        for cmd in ('gh pr create --title x --body "$(git switch -q p; echo hi)"',  # runs before gh, even in quotes
                    "gh pr create --title x --body \"$(cat <<'EOF'\nbody\nEOF\n)\"", 'gh pr create --title "`git switch -q p`"',
                    "gh pr create --title `git switch -q p`", "gh pr create --title x --base $B", "gh pr create --title $X",
                    "gh pr create --title ${X}", "gh pr create --title x --body-file - <<'EOF'\nbody\nEOF"):
            self.work(cmd)

    def test_a_brace_word_that_may_add_a_later_base_is_not_judged(self):
        self.stacked()
        self.grant("gh pr create -B tb --title a")  # judged against tb: test-only
        self.work("gh pr create -B tb {--base=main,} --title a")  # bash makes it `-B tb --base=main --title a`: the last base is main

    def test_a_brace_word_that_may_add_a_later_repo_is_not_judged(self):
        branch(self.repo, "t1", self.FILES)
        self.grant("gh pr create --title x")
        self.work("gh pr create --title x {--repo=example-owner/other,}")  # bash makes it `--repo=example-owner/other`
        self.work('gh pr create --title "a {b} c"')  # quoted, so not expanded, but a brace is never judged: the safe side

    def test_a_glob_word_is_not_judged(self):
        self.release()  # t1 is test-only against main, the default base, but holds a product file against release
        self.grant()
        for cmd in ("gh pr create --title x --*", "gh pr create --title x *", "gh pr create --title x --b?se=release",
                    "gh pr create --title x --base=[r]elease",
                    'gh pr create --title "Fix [x]"', 'gh pr create --title "Why?"', 'gh pr create --title "a*b"'):  # quotes are not seen
            self.work(cmd)  # no file matches the glob: the shell passes it on as is
        (self.repo / "--base=release").write_text("")  # the trap: bash expands `--*` into it, so gh opens the PR against release
        self.work("gh pr create --title x --*")

    def test_a_lone_create_with_its_usual_words_passes(self):
        branch(self.repo, "t1", self.FILES)
        for cmd in ("gh pr create --title x --body-file /tmp/pr-body.md", 'gh pr create --title "Fix #12" --body "plain text"',
                    'gh pr create --fill --body "- item one\n- item two"', "gh pr create",
                    'gh pr new --title "gh pr create"',  # the alias is gated only where the text `gh pr create` is also in the command
                    "gh pr create \\\n  --title x \\\n  --body-file /tmp/pr-body.md"):  # a continuation is one line to the shell
            self.grant(cmd)

    def test_a_line_continuation_does_not_hide_an_option(self):
        self.release()
        for cmd in ("gh pr create --title x \\\n--base release", "gh pr create --title x \\\n  --base release"):
            self.work(cmd)  # judged against release, where the branch holds a product file

    def test_a_comment_that_looks_like_an_option_is_not_judged(self):
        self.stacked()
        self.grant("gh pr create --title x --base tb")
        for cmd in ("gh pr create --title x # --base tb", "gh pr create --title x #--base tb"):
            self.work(cmd)  # the shell drops the comment: the PR opens against the default base

    def test_a_configured_merge_base_keeps_the_deny_unless_the_command_names_a_base(self):
        self.release()
        self.grant()
        git(self.repo, "config", "branch.t1.gh-merge-base", "release")
        self.work()  # gh opens the PR against release, not the default branch
        self.grant("gh pr create --title x --base main")  # an explicit base wins

    def test_a_relative_diff_setting_does_not_hide_files_outside_the_directory(self):
        branch(self.repo, "j", {"src/lib.py": "x\n", "tests/test_j.py": "x\n"})
        git(self.repo, "config", "diff.relative", "true")
        self.assertEqual(git(self.repo / "tests", "diff", "--name-only", "origin/main...HEAD").split(), ["test_j.py"])  # the trap
        self.work(cwd=self.repo / "tests")

    def test_a_submodule_change_counts_when_the_config_ignores_submodules(self):
        git(self.repo, "checkout", "-q", "--no-track", "-b", "s1", "origin/main")
        git(self.repo, "update-index", "--add", "--cacheinfo", f"160000,{git(self.repo, 'rev-parse', 'HEAD').strip()},vendor/lib")
        (self.repo / "tests").mkdir()
        (self.repo / "tests/test_s.py").write_text("x\n")
        git(self.repo, "add", "tests")
        git(self.repo, "commit", "-q", "-m", "s1")
        git(self.repo, "update-ref", "refs/remotes/origin/s1", "HEAD")
        git(self.repo, "config", "diff.ignoreSubmodules", "all")
        self.assertEqual(git(self.repo, "diff", "--name-only", "origin/main...HEAD").split(), ["tests/test_s.py"])  # the trap
        self.work()

    def test_a_branch_that_is_not_pushed_as_itself_is_not_judged(self):
        branch(self.repo, "t1", self.FILES, push=False)
        self.work()  # no origin/t1: what is judged may differ from what gh opens
        git(self.repo, "update-ref", "refs/remotes/origin/other-name", "HEAD")
        self.work()  # a remote ref at HEAD, but not under the branch's name
        git(self.repo, "update-ref", "refs/remotes/origin/t1", "HEAD")
        self.work()  # two remote refs at HEAD
        git(self.repo, "update-ref", "-d", "refs/remotes/origin/other-name")
        git(self.repo, "update-ref", "refs/remotes/upstream/t1", "HEAD")
        self.work()  # a second remote at the same commit
        git(self.repo, "update-ref", "-d", "refs/remotes/upstream/t1")
        self.assertEqual(self.grant(), {"branch": "t1", "at": NOW})  # exactly origin/t1 at HEAD

    def test_a_pushed_copy_that_is_not_at_head_is_not_judged(self):
        branch(self.repo, "p", {"src/lib.py": "x\n"})
        branch(self.repo, "t1", self.FILES)
        for where in ("HEAD~1", "refs/remotes/origin/p"):  # behind HEAD; a product commit
            git(self.repo, "update-ref", "refs/remotes/origin/t1", where)
            self.work()
        git(self.repo, "update-ref", "refs/remotes/origin/t1", "HEAD")
        (self.repo / "src/late.py").write_text("x\n")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "late")
        git(self.repo, "update-ref", "refs/remotes/origin/t1", "HEAD")
        git(self.repo, "reset", "-q", "--hard", "HEAD~1")  # the pushed copy is ahead and holds a product file; HEAD is test-only
        self.work()

    def test_a_second_remote_keeps_the_deny_because_gh_may_open_the_pr_on_it(self):
        self.release()  # t1 is test-only against origin/main, which carries a product commit that origin/release lacks
        git(self.repo, "remote", "add", "origin", self.URL)
        self.grant()  # origin is the only remote
        git(self.repo, "update-ref", "refs/remotes/upstream/main", "refs/remotes/origin/release")
        self.assertIn("src/new.py", git(self.repo, "diff", "--name-only", "upstream/main...HEAD").split())  # the trap: the diff gh opens
        for name in ("upstream", "fork"):  # gh prefers `upstream`, but any name besides origin is not judged
            git(self.repo, "remote", "add", name, self.URL)
            self.work()
            git(self.repo, "remote", "remove", name)

    def test_a_default_repo_other_than_origin_keeps_the_deny(self):
        branch(self.repo, "t1", self.FILES)
        git(self.repo, "remote", "add", "origin", self.URL)
        for value in ("example-owner/parent", ""):  # `gh repo set-default` on a fork writes the parent's name
            git(self.repo, "config", "remote.origin.gh-resolved", value)
            self.work()

    def test_one_origin_remote_is_judged(self):
        branch(self.repo, "t1", self.FILES)
        git(self.repo, "remote", "add", "origin", self.URL)
        self.assertEqual(self.grant(), {"branch": "t1", "at": NOW})

    def test_a_default_repo_set_to_base_is_judged(self):
        branch(self.repo, "t1", self.FILES)
        git(self.repo, "remote", "add", "origin", self.URL)
        git(self.repo, "config", "remote.origin.gh-resolved", "base")  # `gh repo set-default` on origin itself
        self.assertEqual(self.grant(), {"branch": "t1", "at": NOW})

    def test_every_default_repo_value_must_be_base(self):
        branch(self.repo, "t1", self.FILES)
        git(self.repo, "remote", "add", "origin", self.URL)
        for values in (["example-owner/parent", "base"], ["base", "example-owner/parent"], ["base", ""], ["base\nbase"]):
            for v in values:  # `git config --get` reads only the last value; a value with a newline is one value, not two
                git(self.repo, "config", "--add", "remote.origin.gh-resolved", v)
            self.work()
            git(self.repo, "config", "--unset-all", "remote.origin.gh-resolved")
        for values in (["base"], ["base", "base"]):
            for v in values:
                git(self.repo, "config", "--add", "remote.origin.gh-resolved", v)
            self.grant()
            git(self.repo, "config", "--unset-all", "remote.origin.gh-resolved")

    def test_every_configured_merge_base_value_is_read(self):
        self.release()
        for values in (("release", ""), ("", "release"), (" ",)):  # `--get` reads only the last value; a blank one is still a value
            for v in values:
                git(self.repo, "config", "--add", "branch.t1.gh-merge-base", v)
            self.work()
            self.grant("gh pr create --title x --base main")  # an explicit base wins
            git(self.repo, "config", "--unset-all", "branch.t1.gh-merge-base")
        git(self.repo, "config", "branch.t1.gh-merge-base", "")
        self.grant()  # an empty value names no base

    def test_a_config_read_gives_every_value_exact_and_raises_unless_the_key_is_unset(self):
        git(self.repo, "config", "--add", "a.b", "x\ny")
        git(self.repo, "config", "--add", "a.b", "")
        with mock.patch.dict(os.environ, ENV, clear=True):  # the module runs git with the process's environment
            self.assertEqual(self.fa._values(self.repo, "a.b"), ["x\ny", ""])  # a newline stays inside its value
            self.assertEqual(self.fa._values(self.repo, "a.none"), [])  # git exits 1
            (self.repo / ".git" / "config").write_text("[a\n")
            with self.assertRaises(subprocess.CalledProcessError):
                self.fa._values(self.repo, "a.b")  # a config git cannot read is not an unset key

    def test_a_remote_or_ref_name_that_only_looks_like_origin_is_another_name(self):
        branch(self.repo, "t1", self.FILES, push=False)
        git(self.repo, "remote", "add", "origin", self.URL)
        for space in ("\u00a0", "\u2028", "\u0085"):  # git allows each in a name: str.split() drops it, str.splitlines() splits at two
            git(self.repo, "update-ref", f"refs/remotes/origin/t1{space}", "HEAD")
            self.work()  # no origin/t1, only a name that reads as it
            git(self.repo, "update-ref", "refs/remotes/origin/t1", "HEAD")
            self.work()  # two remote refs at HEAD
            git(self.repo, "update-ref", "-d", f"refs/remotes/origin/t1{space}")
            self.grant()  # exactly origin/t1 at HEAD
            for name in (f"origin{space}", f"origin{space}origin"):  # a second remote: a name that reads as origin, or as two of it
                git(self.repo, "remote", "add", name, self.URL)
                self.work()
                git(self.repo, "remote", "remove", name)
            git(self.repo, "config", "--rename-section", "remote.origin", f"remote.origin{space}")
            self.work()  # the only remote, named like origin
            git(self.repo, "config", "--rename-section", f"remote.origin{space}", "remote.origin")
            self.grant()
            git(self.repo, "update-ref", "-d", "refs/remotes/origin/t1")

    def test_an_unpushed_branch_is_a_work_deny_even_at_the_exempt_cap(self):
        self.seed("ex1", "ex2")
        branch(self.repo, "t3", self.FILES, push=False)
        self.work(heads=["ex1", "ex2"])  # not `throughput-cap`: the push check comes first

    def test_the_deny_message_names_the_parsed_exempt_cap_or_none(self):
        branch(self.repo, "p1", {"src/app.py": "x = 2\n"})
        for raw in ("3", "03", " 3 "):
            self.assertIn("while fewer than 3 such PRs are open.", self.create(env={"PERUN_THROUGHPUT_OPEN": raw}).stderr, raw)
        p = self.create(env={"PERUN_THROUGHPUT_OPEN": "many"})
        self.assertEqual(p.returncode, 2)
        self.assertIn("Blocked `gh pr create`", p.stderr)
        self.assertNotIn("Queue-throughput", p.stderr)  # no clause rather than a number that is not the cap
        self.assertNotIn("many", p.stderr)


def listing(*names):
    """GitHub's compare reply for a branch that changes `names`: the per-lane recount's source of the new PR's files."""
    return {"files": [{"filename": n} for n in names]}


def lane_pr(*files, total=None, state=GREEN):
    """A PR in `state` (default ready) that changes `files`, as the per-lane recount's `gh pr list` returns it; `total` (default all of
    them) is its `changedFiles`, so a larger one stands for a file list that GitHub cut short."""
    return {**state, "files": [{"path": f} for f in files], "changedFiles": len(files) if total is None else total}


class Lanes(unittest.TestCase):
    """PERUN_STOP_STARTING_LANES: at the global cap (2 here) the new PR passes when fewer than 2 ready PRs sit in its own lane. Throughput's
    repo, with lanes `web=web/*;api=` (`api` is the fallback) unless a test says otherwise; the fake gh serves the same PRs to both lists
    and answers the compare with the branch's own files. Every failure of the recount keeps the deny."""
    setUp, lines = Throughput.setUp, Throughput.lines  # the repo fixture and the JSON-lines reader, without Throughput's own tests
    setUpClass = classmethod(Throughput.setUpClass.__func__)  # loads the script as `cls.fa`
    LANES = "web=web/*;api="
    WEB, API = lane_pr("web/a.ts"), lane_pr("api/x.py")

    def go(self, prs, lanes=LANES, compare=None, **kw):
        """The hook on a lone `gh pr create` with the ready PRs `prs` open; `lanes` None leaves the variable unset. The compare answers
        with the branch's own files (what the local diff lists when the base is fetched) unless `compare` is given."""
        env = {"PERUN_STOP_STARTING_READY": "2", **({} if lanes is None else {"PERUN_STOP_STARTING_LANES": lanes})}
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create --title x"}, "cwd": str(self.repo)})
        if compare is None:
            compare = listing(*git(self.repo, "diff", "--name-only", "origin/main...HEAD").split())
        return run([], prs, stdin=stdin, env=env, compare=compare, **kw)

    def passes(self, prs, **kw):
        """The hook lets the PR through silently and writes no denial and no ledger entry."""
        before = self.lines(DENIALS), self.lines(LEDGER)
        p = self.go(prs, **kw)
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertEqual((self.lines(DENIALS), self.lines(LEDGER)), before)

    def denies(self, prs, lane, count, **kw):
        """The hook denies and writes one denial that names `lane` and `count` (None: unknown); returns the process."""
        seen = len(self.lines(DENIALS))
        p = self.go(prs, **kw)
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertEqual([(d["lane"], d["lane_ready"]) for d in self.lines(DENIALS)[seen:]], [(lane, count)])
        self.assertEqual(count is not None, "Lane `" in p.stderr)  # the message names a lane only when it counted it
        return p

    def test_a_lane_with_room_passes_and_a_full_one_denies(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        self.passes([self.WEB, self.WEB])  # the global count is at the cap, but `api` holds no ready PR
        branch(self.repo, "w1", {"web/a.ts": "x\n"})
        self.passes([self.WEB, self.API])  # one ready PR in `web`: room
        p = self.denies([self.WEB, self.WEB], "web", 2)
        self.assertIn("(cap 2). Lane `web`: 2 ready (cap 2 per lane). Waiting work is queue;", p.stderr)
        self.assertEqual(self.lines(DENIALS), [{"at": NOW, "class": "work", "ready": 2, "cap": 2, "lane": "web", "lane_ready": 2}])

    def test_the_first_lane_with_a_matching_glob_is_the_lane(self):
        branch(self.repo, "m1", {"web/a.ts": "x\n", "api/b.py": "x\n"})
        self.denies([self.WEB, self.WEB], "web", 2)
        self.passes([self.API, self.API])  # the fallback `api` does not take a PR that `web` matched
        self.denies([self.WEB, self.WEB], "web", 2, lanes="api=;web=web/*")  # the fallback may be written first
        self.denies([self.WEB, self.WEB], "web", 2, lanes="web=web/*;api=api/*")  # two lanes with globs: the order written decides
        self.denies([self.API, self.API], "api", 2, lanes="api=api/*;web=web/*")
        self.passes([self.WEB, self.WEB], lanes="api=api/*;web=web/*")
        branch(self.repo, "m2", {"web/deep/a/b.ts": "x\n"})
        self.denies([lane_pr("web/c/d.ts")] * 2, "web", 2)  # `*` crosses `/`
        branch(self.repo, "m3", {"src/web/a.ts": "x\n"})
        self.passes([self.WEB, self.WEB])  # no tail matching: `src/web/a.ts` is not in `web`, it falls to `api`

    def test_a_pr_of_unknown_lane_counts_in_every_lane(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        cut = lane_pr("web/a.ts", total=3)  # GitHub lists at most 100 files: the other two are not seen
        self.passes([self.WEB, cut])  # one unknown PR counts: 1 < 2
        self.denies([cut, cut], "api", 2)
        for bare in ({**GREEN, "files": None, "changedFiles": 1}, GREEN):  # files null; files missing
            self.denies([cut, bare], "api", 2)

    def test_a_pr_that_matches_no_lane_counts_in_every_lane_unless_a_fallback_takes_it(self):
        docs, strict = lane_pr("docs/x.md"), "web=web/*;api=api/*"
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        self.denies([docs, docs], "api", 2, lanes=strict)  # no fallback: both count in `api`, which would hold none otherwise
        self.passes([docs, docs], lanes=f"{strict};misc=")  # `misc` takes them
        branch(self.repo, "d1", {"docs/x.md": "x\n"})
        self.denies([self.WEB, self.WEB], None, None, lanes=strict)  # no lane for the new PR: the deny stands
        self.passes([self.WEB, self.WEB], lanes=f"{strict};misc=")

    def test_a_malformed_map_keeps_the_deny(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        # no `=`; a repeated name (read leniently, either entry would take the new PR's `api/x.py`); two fallbacks; no name; no lane
        for lanes in ("web", "web=a/*;web=b/*", "web=web/*;web=api/*", "web=api/*;web=web/*", "a=;b=", "=x/*", "=api/*;web=", " ; "):
            self.denies([self.WEB, self.WEB], None, None, lanes=lanes)
        spaced = " web = web/* , api/* ; ; api = "  # blanks around names and globs, a blank entry
        self.denies([self.WEB, self.WEB], "web", 2, lanes=spaced)  # `api/x.py` matches the second glob of `web`
        branch(self.repo, "d1", {"docs/x.md": "x\n"})
        self.passes([self.WEB, self.WEB], lanes=spaced)  # the fallback `api`

    def test_a_pr_that_is_not_judged_keeps_the_deny(self):
        self.denies([self.WEB, self.WEB], None, None)  # HEAD is origin/main: an empty diff has no lane
        branch(self.repo, "a1", {"api/x.py": "x\n"}, push=False)
        self.denies([self.WEB, self.WEB], None, None)  # not pushed to origin: its diff may not be the PR's

    def test_a_recount_that_cannot_read_the_queue_keeps_the_deny(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        self.passes([self.WEB, self.WEB])  # the same PRs with a readable queue: room in `api`
        self.denies([self.WEB, self.WEB], "api", None, fail_files=True)  # only the call that asks for `files` fails
        self.denies([self.WEB] * 500, "api", None)  # 500 back: the list may be cut
        self.passes([self.WEB] * 499)

    def test_the_lane_comes_from_the_compare_not_the_local_diff(self):
        branch(self.repo, "up", {"web/base.ts": "x\n"}, push=False)  # a base commit that the local origin/main lacks
        branch(self.repo, "s1", {"api/x.py": "x\n"}, base="up")
        self.assertEqual(git(self.repo, "diff", "--name-only", "origin/main...HEAD").split(), ["api/x.py", "web/base.ts"])  # a superset
        full = [self.API, self.API]
        p = self.denies(full, "api", 2, compare=listing("api/x.py"))  # GitHub lists the branch's own file: its lane is full
        self.assertIn("Lane `api`: 2 ready", p.stderr)
        self.passes(full, compare=listing("web/base.ts", "api/x.py"))  # the superset puts the PR in `web`, which has room

    def test_a_compare_that_cannot_name_the_files_keeps_the_deny(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        many = [f"api/f{i}.py" for i in range(300)]
        self.passes([self.WEB, self.WEB])  # the same PRs with a readable compare: room in `api`
        self.passes([self.WEB, self.WEB], compare=listing(*many[:299]))  # GitHub lists at most 300: 299 is the whole list
        bad = ({"fail_compare": True}, {"compare": listing(*many)},  # a failed call; 300 files, the list may be cut
               {"compare": listing()}, {"compare": {}}, {"compare": {"files": None}},  # no files; an empty list; no list
               {"compare": []}, {"compare": {"files": [{"path": "api/x.py"}]}})  # a reply that is no object; an entry with no name
        for kw in bad:
            self.denies([self.WEB, self.WEB], None, None, **kw)

    def test_a_ready_pr_with_files_but_no_file_count_is_of_unknown_lane(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        bare = {**GREEN, "files": [{"path": "web/a.ts"}]}  # no `changedFiles` to tell whether the list is whole
        self.passes([{**bare, "changedFiles": 1}] * 2)  # with the count they are `web` PRs: room in `api`
        self.denies([bare, bare], "api", 2)  # missing
        self.denies([{**bare, "changedFiles": None}, bare], "api", 2)  # null, and missing

    def test_a_recount_that_does_not_confirm_the_first_read_keeps_the_deny(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        self.passes([self.WEB, self.WEB], recount=[self.WEB, self.WEB])  # confirmed: room in `api`
        draft = lane_pr("web/a.ts", state=DRAFT)
        # prints nothing (exit 0); one ready PR, short of the cap; two PRs but one a draft
        for recount in ("", [self.WEB], [self.WEB, draft]):
            self.denies([self.WEB, self.WEB], "api", None, recount=recount)

    def test_a_red_or_draft_pr_in_the_full_lane_does_not_count(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        self.denies([self.WEB, self.WEB, self.API, self.API], "api", 2)  # ready, they fill it
        self.passes([self.WEB, self.WEB, lane_pr("api/x.py", state=RED), lane_pr("api/x.py", state=DRAFT)])

    def test_a_lane_is_recounted_when_the_wide_read_puts_the_queue_at_the_cap(self):
        branch(self.repo, "w1", {"web/a.ts": "x\n"})
        page = [lane_pr("docs/x.md", state=DRAFT)] * 99  # the newest 100 hold one ready PR, under the cap of 2: the second is behind them
        wide = [self.WEB, self.WEB, *page]  # with lanes set the wide read asks for `files`: the fake gh answers it as the recount
        self.denies([self.WEB, *page], "web", 2, recount=wide)
        self.assertEqual(self.lines(DENIALS)[-1]["ready"], 2)  # the wide count is the one recorded
        p = self.go([self.WEB, *page], recount=wide, fail_files=True)  # only the wide read fails: the first read's count, under the cap
        self.assertEqual((p.returncode, p.stderr), (0, WIDE_FAILED))

    QUIET = lane_pr("docs/x.md", state=DRAFT)

    def test_with_lanes_the_wide_read_lists_the_files_and_is_the_recount(self):
        first = [self.WEB] + [self.QUIET] * 99  # 100 PRs, 1 ready: under the cap of 2
        wide = [self.WEB] * 3 + [self.QUIET] * 127  # 130 PRs, 3 ready, all in `web`: the queue is at the cap
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        rc, err, _ = self.inproc([100.0] * 5, first, recount=wide)
        self.assertEqual((rc, err), (0, ""))  # the new PR is in `api`, which has room
        self.assertEqual([a[0] for a, _, _ in self.calls], ["pr", "pr", "api"])  # the first list, the wide list, the compare: no third list
        self.assertEqual([(a[a.index("--limit") + 1], a[-1]) for a, _, _ in self.calls[:2]],
                         [("100", "isDraft,statusCheckRollup,headRefName"), ("500", "isDraft,statusCheckRollup,headRefName,files,changedFiles")])
        branch(self.repo, "w1", {"web/a.ts": "x\n"})
        rc, _, _ = self.inproc([100.0] * 5, first, recount=wide)  # the new PR is in `web`, which holds the 3 ready PRs
        self.assertEqual((rc, self.last(), len(self.calls)), (2, ("web", 3), 3))
        self.assertEqual(self.lines(DENIALS)[-1]["ready"], 3)  # the wide count is the one recorded

    def test_the_wide_list_is_counted_even_when_the_budget_is_spent_by_then(self):
        first = [self.WEB] + [self.QUIET] * 99
        wide = [self.WEB] * 3 + [self.QUIET] * 127
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        # ticks: the hook's start, before the wide read (14 s left), `_lane_ready`'s opening check (3 s left), the compare after its base
        # lookup (2 s left), and the check before the recount (1.5 s left: a list call of its own would be skipped, and the deny would stand)
        rc, _, _ = self.inproc([100.0, 101.0, 112.0, 113.0, 113.5], first, recount=wide)
        self.assertEqual((rc, [t for _, t, _ in self.calls]), (0, [10, 14.0, 2.0]))  # `api` has room, counted from the wide list
        self.assertEqual([a[0] for a, _, _ in self.calls], ["pr", "pr", "api"])

    def test_a_failed_or_slow_wide_read_with_lanes_keeps_the_first_read_and_says_so(self):
        first = [self.WEB] + [self.QUIET] * 99  # 1 ready: under the cap of 2
        for bad in (RuntimeError("gh failed"), subprocess.TimeoutExpired("gh", 14)):
            rc, err, _ = self.inproc([100.0] * 5, first, recount=bad)  # only the call that asks for `files` fails: the wide read
            self.assertEqual((rc, err, len(self.calls)), (0, WIDE_FAILED, 2))  # no lane work, as the first read alone
        self.assertEqual(self.lines(DENIALS), [])

    def test_a_wide_list_of_500_may_be_cut_and_keeps_the_deny(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        first = [self.WEB] + [self.QUIET] * 99
        rc, _, _ = self.inproc([100.0] * 5, first, recount=[self.WEB] * 2 + [self.QUIET] * 498)  # 500 PRs back
        self.assertEqual((rc, self.last(), len(self.calls)), (2, ("api", None), 3))  # the lane is known, not counted; no list call of its own
        rc, _, _ = self.inproc([100.0] * 5, first, recount=[self.WEB] * 2 + [self.QUIET] * 497)  # 499: the whole list
        self.assertEqual((rc, len(self.calls)), (0, 3))

    def test_a_first_read_at_the_cap_leaves_the_recount_its_own_list_call(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        for first in ([self.WEB] * 2, [self.WEB] * 2 + [self.QUIET] * 98):  # at the cap of 2, short of a full page and a full page
            self.assertEqual(self.inproc([100.0] * 4, first)[0], 0)  # `api` has room
            self.assertEqual([a[0] for a, _, _ in self.calls], ["pr", "api", "pr"])  # the first list, the compare, the recount's list
            self.assertEqual([a[a.index("--limit") + 1] for a, _, _ in self.calls if a[0] == "pr"], ["100", "500"])
            self.assertEqual(self.calls[2][0][-1], "isDraft,statusCheckRollup,headRefName,files,changedFiles")

    def inproc(self, ticks, prs=None, recount=None, command="gh pr create --title x", compare=None, judged=None, lanes=LANES, wide=None):
        """fa.hook() in this process on `command`, in the repo's current branch, with real git reads, at a cap of 2. `gh_json` logs
        (args, timeout, cwd) in `self.calls` and answers the compare with `compare` (default: the branch's own files), the first read with
        `prs` (default: two ready `api` PRs, a full lane), the wide read without files (`--limit 500`, lanes unset) with `wide` and a
        read that asks for `files` with `recount` (both default `prs`): the per-lane recount, or with lanes set the wide read itself; an
        exception is raised. The monotonic clock reads `ticks` in turn: the hook's start, before the wide read (only one that is made),
        and with lanes the opening check of `_lane_ready`, the compare's after its base lookup, and one before the recount (read whether
        or not a list call of its own follows).
        `judged` replaces `_judged` (default: a spy on the real one); `lanes` None leaves the variable unset. Returns (exit code,
        stderr, the `_judged` mock)."""
        self.calls, ticks = [], iter(ticks)
        prs = [self.API, self.API] if prs is None else prs
        recount = prs if recount is None else recount
        wide = prs if wide is None else wide
        if compare is None:
            compare = listing(*git(self.repo, "diff", "--name-only", "origin/main...HEAD").split())

        def gh(*a, timeout=60, cwd=None):
            self.calls.append((a, timeout, cwd))
            out = compare if a[0] == "api" else recount if "files" in a[-1] else wide if "500" in a else prs
            if isinstance(out, Exception):
                raise out
            return out
        spy = judged or mock.Mock(wraps=self.fa._judged)
        env = {**ENV, "PERUN_STOP_STARTING_READY": "2", **({} if lanes is None else {"PERUN_STOP_STARTING_LANES": lanes})}
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(self.repo)}))
        clock = mock.Mock(monotonic=lambda: next(ticks), time=lambda: NOW)
        with mock.patch.object(self.fa, "gh_json", gh), mock.patch.object(self.fa, "_judged", spy), \
                mock.patch.object(self.fa, "time", clock), mock.patch.dict(os.environ, env, clear=True), \
                mock.patch("sys.stdin", stdin), mock.patch("sys.stderr", io.StringIO()) as err:
            return self.fa.hook(NOW), err.getvalue(), spy

    def last(self):
        """(lane, lane_ready) of the latest denial."""
        d = self.lines(DENIALS)[-1]
        return d["lane"], d["lane_ready"]

    def test_the_command_is_judged_once_per_hook_call(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        rc, _, spy = self.inproc([100.0] * 4)  # a deny in a full lane: the recount and the throughput judgement share one judging
        self.assertEqual((rc, spy.call_count), (2, 1))
        rc, _, spy = self.inproc([100.0] * 4, judged=mock.Mock(side_effect=OSError))  # a raise is class `work`, and is not retried
        self.assertEqual((rc, spy.call_count, self.lines(DENIALS)[-1]["class"]), (2, 1, "work"))
        branch(self.repo, "t1", Throughput.FILES)
        for lanes in (self.LANES, None):  # a grant in a full lane; the same with the variable unset
            rc, _, spy = self.inproc([100.0] * 4, lanes=lanes)
            self.assertEqual((rc, spy.call_count), (0, 1))

    def test_each_gh_call_of_the_recount_gets_what_is_left_of_the_budget(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        web = [self.WEB, self.WEB]  # `api` has room
        # ticks: the hook's start, the check before the compare, the compare after its base lookup, the check before the recount
        self.assertEqual(self.inproc([100.0, 101.0, 102.0, 104.0], web)[0], 0)
        (first, t1, _), (compare, t2, cwd), (recount, t3, _) = self.calls
        self.assertEqual((t1, t2, t3), (10, 13.0, 11.0))  # the first read keeps its 10 s; each recount call gets what is left of 15 s
        self.assertEqual((compare[0], cwd), ("api", str(self.repo)))  # gh resolves {owner}/{repo} where the command runs
        self.assertEqual((first[first.index("--limit") + 1], recount[recount.index("--limit") + 1]), ("100", "500"))
        self.assertEqual(first[-1], "isDraft,statusCheckRollup,headRefName")  # the first call stays light
        self.assertEqual(recount[-1], "isDraft,statusCheckRollup,headRefName,files,changedFiles")  # the same fields, and the files
        self.assertEqual(self.inproc([100.0, 113.0, 113.0, 113.0], web)[0], 0)  # 2 s left: both calls are made
        self.assertEqual([t for _, t, _ in self.calls], [10, 2.0, 2.0])
        rc, err, _ = self.inproc([100.0, 113.5, 113.5], web)  # under 2 s left for the compare: no lane, no recount, the deny stands
        self.assertEqual((rc, len(self.calls), self.last()), (2, 1, (None, None)))
        self.assertIn("Blocked `gh pr create`", err)
        rc, _, _ = self.inproc([100.0, 101.0, 113.5, 113.5], web)  # under 2 s left after the base lookup: the compare is skipped too
        self.assertEqual((rc, len(self.calls), self.last()), (2, 1, (None, None)))
        rc, _, _ = self.inproc([100.0, 101.0, 101.0, 113.5], web)  # under 2 s left for the recount: the lane is known, not counted
        self.assertEqual((rc, len(self.calls), self.last()), (2, 2, ("api", None)))
        for slow in ({"compare": subprocess.TimeoutExpired("gh", 14)}, {"recount": subprocess.TimeoutExpired("gh", 12)}):
            rc, err, _ = self.inproc([100.0, 101.0, 101.0, 103.0], web, **slow)  # a slow call: a deny, not the fail-open exit of a slow first read
            self.assertEqual(rc, 2)
            self.assertNotIn("skipped this call", err)
        self.assertEqual(self.last(), ("api", None))

    def test_the_compare_gets_what_is_left_after_a_slow_base_lookup(self):
        now, seen = [100.0], []

        def compare(lag, base=None):
            """`_compare` with t0 100.0 when the lookup of origin/HEAD's branch takes `lag` s; `seen` holds the timeout it passed."""
            now[0], seen[:] = 100.0, []

            def lookup(cwd, *a):
                now[0] += lag
                return "refs/remotes/origin/main\n"

            def gh(*a, timeout=60, cwd=None):
                seen.append(timeout)
                return listing("api/x.py")
            with mock.patch.object(self.fa, "_git", lookup), mock.patch.object(self.fa, "gh_json", gh), \
                    mock.patch.object(self.fa, "time", mock.Mock(monotonic=lambda: now[0])):
                return self.fa._compare(None, ("a1", ["api/x.py"], base), 100.0)
        for lag, left in ((0.0, 15.0), (4.0, 11.0), (13.0, 2.0)):  # the lookup uses some of the budget: the call gets the rest of it
            self.assertEqual((compare(lag), seen), (["api/x.py"], [left]))
        self.assertEqual((compare(13.5), seen), (None, []))  # under 2 s left after the lookup: the call is skipped
        self.assertEqual((compare(13.5, base="rel"), seen), (["api/x.py"], [15.0]))  # a `--base` value needs no lookup

    def test_the_compare_names_the_base_and_the_url_quoted_branch(self):
        branch(self.repo, "feat/a#1", {"api/x.py": "x\n"})
        self.inproc([100.0] * 4)
        self.assertEqual(self.calls[1][0], ("api", "repos/{owner}/{repo}/compare/main...feat/a%231?per_page=1"))  # origin/HEAD's branch
        git(self.repo, "update-ref", "refs/remotes/origin/rel/1#a", "origin/main")
        self.inproc([100.0] * 4, command="gh pr create --title x --base rel/1#a")
        self.assertEqual(self.calls[1][0], ("api", "repos/{owner}/{repo}/compare/rel/1%23a...feat/a%231?per_page=1"))  # `--base`: `/` kept
        git(self.repo, "symbolic-ref", "refs/remotes/origin/HEAD", "refs/remotes/origin/rel/1#a")  # a default branch other than `main`
        self.inproc([100.0] * 4)
        self.assertEqual(self.calls[1][0], ("api", "repos/{owner}/{repo}/compare/rel/1%23a...feat/a%231?per_page=1"))

    def test_a_test_only_branch_of_a_full_lane_still_gets_the_throughput_grant(self):
        branch(self.repo, "t1", Throughput.FILES)  # test and CI paths only: in `api`, the fallback
        self.passes([self.WEB, self.WEB])  # `api` has room: through the lane check, no ledger entry
        p = self.go([self.API, self.API])  # `api` is full: the throughput judgement goes on
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertEqual(self.lines(LEDGER), [{"branch": "t1", "at": NOW}])
        self.assertEqual(self.lines(DENIALS), [])

    def test_with_the_variable_unset_or_blank_nothing_changes(self):
        branch(self.repo, "a1", {"api/x.py": "x\n"})
        for lanes in (None, "", "  "):
            p = self.go([self.WEB, self.WEB], lanes=lanes)
            self.assertEqual(p.returncode, 2)  # no per-lane cap: the global count denies
            self.assertNotIn("Lane `", p.stderr)
        self.assertEqual(self.lines(DENIALS), [{"at": NOW, "class": "work", "ready": 2, "cap": 2}] * 3)  # the old keys, no more


class WideRead(unittest.TestCase):
    """The hook's first read is the newest 100 open PRs. When it holds 100 and its ready count is under the cap, a second read of up to 500
    (`--limit 500`, the same fields, no files) replaces its list and count, so ready PRs beyond the first 100 count too; a failed or slow
    second read keeps the first and prints one stderr line. Throughput's repo (HEAD at `origin/main`: an empty diff, so a deny is class `work`). `create` runs the
    hook as a process whose fake gh answers the two reads with different lists, at the default cap of 5; `inproc` (Lanes') runs it in this
    process at a cap of 2, logging the gh calls and on a clock the test sets; `FIRST` is a first read of 100 PRs with one ready."""
    setUp, lines, seed = Throughput.setUp, Throughput.lines, Throughput.seed
    setUpClass = classmethod(Throughput.setUpClass.__func__)
    inproc = Lanes.inproc
    FIRST = [GREEN] + [DRAFT] * 99

    def create(self, first, wide, **kw):
        """The hook on a lone `gh pr create` in the repo: the first read (`--limit 100`) lists `first`, the wide read lists `wide`."""
        stdin = json.dumps({"tool_name": "Bash", "tool_input": {"command": "gh pr create --title x"}, "cwd": str(self.repo)})
        return run([], first, stdin=stdin, wide=wide, **kw)

    def test_ready_prs_beyond_the_first_100_are_counted(self):
        first = [GREEN] * 3 + [DRAFT] * 97  # 100 PRs, 3 ready: under the cap of 5
        p = self.create(first, [GREEN] * 6 + [DRAFT] * 124)  # 130 PRs, 6 ready: three of them were behind the first 100
        self.assertEqual(p.returncode, 2, p.stderr)
        self.assertIn("6 ready-but-unmerged PRs (cap 5)", p.stderr)
        self.assertEqual(self.lines(DENIALS), [{"at": NOW, "class": "work", "ready": 6, "cap": 5}])  # the wide count is the one recorded
        p = self.create(first, [GREEN] * 4 + [DRAFT] * 126)  # the wide count decides: 4 is under the cap; a read that worked prints nothing
        self.assertEqual((p.returncode, p.stderr), (0, ""))
        self.assertEqual(self.create(first, [GREEN] * 5 + [DRAFT] * 125).returncode, 2)  # and 5 is the cap

    def test_a_wide_read_that_fails_or_is_slow_keeps_the_first_read(self):
        first, wide = [GREEN] * 3 + [DRAFT] * 97, [GREEN] * 6 + [DRAFT] * 124
        p = self.create(first, wide, fail_wide=True)  # only the wide read fails: the first read's 3 are under the cap, as before
        self.assertEqual((p.returncode, p.stderr), (0, WIDE_FAILED))  # one stderr line says the count is on the newest 100
        # a failed call, one that outlasted its timeout, a reply that is no list of PRs: the same
        for bad in (RuntimeError("gh failed"), subprocess.TimeoutExpired("gh", 11.0), "oops", [GREEN, "oops"]):
            self.assertEqual(self.inproc([100.0, 104.0], self.FIRST, wide=bad, lanes=None)[:2], (0, WIDE_FAILED))
            self.assertEqual(len(self.calls), 2)  # the wide read was made
        self.assertEqual(self.lines(DENIALS), [])

    def test_one_list_call_unless_the_first_read_is_a_full_page_under_the_cap(self):
        for prs, limits, rc in (([GREEN] + [DRAFT] * 98, ["100"], 0),  # 99 PRs: nothing can be behind them
                                ([GREEN] * 2 + [DRAFT] * 98, ["100"], 2),  # 100 PRs, already at the cap of 2
                                (self.FIRST, ["100", "500"], 0)):  # 100 PRs under it: the wide read, which here agrees
            self.assertEqual(self.inproc([100.0, 100.0], prs, lanes=None)[0], rc)
            self.assertEqual([a[a.index("--limit") + 1] for a, _, _ in self.calls], limits)

    def test_the_wide_read_asks_for_the_same_fields_in_what_is_left_of_the_budget(self):
        wide = [GREEN] * 3 + [DRAFT] * 97
        self.assertEqual(self.inproc([100.0, 104.0], self.FIRST, wide=wide, lanes=None)[0], 2)
        (first, t1, _), (second, t2, _) = self.calls
        self.assertEqual((t1, t2), (10, 11.0))  # the first read keeps its 10 s; the second gets what is left of 15 s
        self.assertEqual((first[first.index("--limit") + 1], second[second.index("--limit") + 1]), ("100", "500"))
        self.assertEqual((first[-1], second[-1]), ("isDraft,statusCheckRollup,headRefName",) * 2)  # the same fields, no files
        self.assertEqual(self.inproc([100.0, 113.0], self.FIRST, wide=wide, lanes=None)[0], 2)  # 2 s left: the read is made
        self.assertEqual([t for _, t, _ in self.calls], [10, 2.0])
        self.assertEqual(self.inproc([100.0, 113.5], self.FIRST, wide=wide, lanes=None)[0], 0)  # under 2 s left: skipped, 1 ready passes
        self.assertEqual(len(self.calls), 1)

    def test_the_wide_list_is_the_one_the_throughput_judgement_reads(self):
        branch(self.repo, "t1", Throughput.FILES)  # test and CI paths only: it passes while fewer than 2 exempt PRs are open
        self.seed("ex1", "ex2")
        wide = [{**GREEN, "headRefName": "ex1"}, {**GREEN, "headRefName": "ex2"}, GREEN] + [DRAFT] * 97  # both exempt PRs are behind the first 100
        self.assertEqual(self.inproc([100.0, 100.0], self.FIRST, wide=wide, lanes=None)[0], 2)
        self.assertEqual(self.lines(DENIALS), [{"at": NOW, "class": "throughput-cap", "ready": 3, "cap": 2}])
        self.assertEqual(len(self.lines(LEDGER)), 2)  # no new grant

    def test_symptom_counts_ready_prs_beyond_the_first_100(self):
        stale = [{"mergedAt": "2027-01-15T05:00:00Z"}]
        r = run(["symptom"], [DRAFT] * 100, stale, wide=[DRAFT] * 100 + [GREEN])  # the one ready PR is the 101st
        self.assertEqual((r.returncode, r.stdout), (1, "ALARM flow: 1 ready PR(s) and nothing merged in 3.0h\n"))


if __name__ == "__main__":
    unittest.main()
