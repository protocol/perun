"""flow_alarm.py: stop-starting hook, one symptom alarm, value-stream split."""
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


def run(args, open_prs=(), merged=(), stdin="", fail=False, env=None):
    d = tempfile.mkdtemp()
    pathlib.Path(d, "open.json").write_text(json.dumps(list(open_prs)))
    pathlib.Path(d, "merged.json").write_text(json.dumps(list(merged)))
    gh = pathlib.Path(d, "gh")
    gh.write_text(f'#!/bin/sh\n[ {int(fail)} -eq 1 ] && exit 1\ncase "$*" in *"--state open"*) cat {d}/open.json;; '
                  f'*"--state merged"*) cat {d}/merged.json;; esac\n')
    gh.chmod(0o755)
    return subprocess.run([sys.executable, str(SCRIPT), *args, "--now", str(NOW)], input=stdin, capture_output=True, text=True,
                          env={**os.environ, "PERUN_GH": str(gh), **(env or {})})


def hook(cmd, ready, env=None):
    return run([], [GREEN] * ready, stdin=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}), env=env)


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
        """The hook's exit code for `cmd` with `ready` ready-but-unmerged PRs (open_ready stubbed, cap 5)."""
        stdin = io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
        with mock.patch.object(self.fa, "open_ready", lambda timeout=60: ready), mock.patch("sys.stdin", stdin), \
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


if __name__ == "__main__":
    unittest.main()
