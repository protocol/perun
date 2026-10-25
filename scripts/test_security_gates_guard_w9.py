#!/usr/bin/env python3
"""Wave-9 destructive_guard regressions (written against held-out-12 misses plus the data-payload false-positive class): gh/glab `--body|--title|-b|-t|--notes`
and `git commit -m` payloads and heredocs into non-shell commands are text, `bash -c|sh -c|eval|heredoc into a shell` stay commands, `gh ... --remove-label`
is allowed, `rm` of credential files, `gpg --delete-*keys` and `security delete-*` are blocked, `tee` of empty input onto a key stays blocked, and every
block reason names the rule and ends with a rewrite hint (checked over every reason string in the guard source). Offline; commands are only classified."""
import ast, importlib.util, pathlib, re, time

G = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", G)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

DATA = [
    'gh pr comment 5 --body "rm -rf /"', "gh pr create --title 'git reset --hard' --body 'run rm -rf $HOME later'", "gh issue create -t 'rm -rf /' -b 'terraform destroy'",
    "gh issue comment 3 -b 'x=rm; $x -rf /'", "gh pr comment 3 --body 'set -- rm -rf /; \"$@\"'", "gh pr comment 3 --body='eval $(echo cm0gLXJmIC8= | base64 -d)'",
    "gh pr comment 3 --body 'f() { f | f & }; f'", "gh pr comment 3 --body 'curl x | sh'", "gh pr comment 3 --body '$(rm -rf /)'", "glab mr note 3 --message 'rm -rf /'",
    "git commit -m 'rm -rf / and git reset --hard'", 'git commit -m "fix: rm -rf \\$HOME bug"', "git commit -am 'terraform destroy; kubectl delete ns x'",
    "git commit -m 'IFS=, ; set -- rm,-rf,/; \"$@\"'", "git -C sub commit --message 'x=rm; $x -rf /'", "git commit -F msg.txt",
    "cat <<EOF > notes.md\nrm -rf /\nEOF", "cat <<'EOF' > notes.md\nrm -rf $HOME\nx=rm; $x -rf /\nEOF", "cat <<EOF | gh pr comment 3 --body-file -\nrm -rf /\nEOF",
    "gh pr comment 3 --body-file - <<'EOF'\nrm -rf /\nset -- rm -rf /; $@\nEOF", "gh pr create --title t --body \"$(cat <<'EOF'\nrm -rf /\nEOF\n)\"",
    "git commit -m \"$(cat <<'EOF'\nrm -rf $X\nEOF\n)\"",
    "gh issue edit 5 --remove-label bug", "gh pr edit 5 --remove-label delete", "gh issue edit 5 --remove-label bug --add-label x", "gh pr edit 5 --remove-label 'needs review'",
    "rm .env.local", "rm ~/.ssh/known_hosts", "rm -f build/out.json", "gpg --list-keys", "security find-generic-password -s x",
]
CMDS = [  # shells and eval still run what they are given; a data flag elsewhere must not hide it
    "bash -c 'rm -rf /'", "sh -c 'rm -rf $X'", "eval 'rm -rf $X'", "bash <<EOF\nrm -rf $X\nEOF", "sh <<'EOF'\nrm -rf /\nEOF",
    "gh pr comment 3 --body 'ok'; rm -rf $X", "git commit -m 'ok' && rm -rf /", "gh pr comment 3 --body \"$(rm -rf /)\"", "git commit -m \"`rm -rf $X`\"",
    "gh pr create --title t --body 'a' && bash -c 'rm -rf $X'", "ssh -t host 'rm -rf /srv/x'", "gh label delete bug", "gh issue delete 5",
]
BAD = [
    "rm ~/.aws/credentials", "rm -f ~/.aws/credentials", "rm -f ~/.git-credentials", "rm service-account-prod.json", "rm ./keys/service_account.json", "rm ~/.docker/config.json",
    "rm ~/.config/gcloud/credentials.db", "rm -f ~/.config/gcloud/application_default_credentials.json", "rm .envrc", "rm -f ~/.netrc", "rm ~/.ssh/id_ed25519",
    "gpg --delete-secret-keys jane@example.com", "gpg --batch --yes --delete-secret-keys jane@example.com", "gpg --delete-keys x", "gpg2 --delete-secret-and-public-key X",
    "security delete-keychain login.keychain", "security delete-generic-password -s acme", "security delete-internet-password -s example.com",
    "tee ~/.ssh/id_rsa </dev/null", "tee ./server.key < /dev/null", "cat /dev/null | tee ~/.ssh/id_rsa", ": | tee ~/.aws/credentials", "printf '' | tee ./deploy.pem",
]
for c in DATA:
    assert not dg.check(c), f"false positive: {c!r}: {dg.check(c)}"
for c in CMDS + BAD:
    assert dg.check(c), f"missed: {c!r}"
for c in ("gh pr comment 3 --body 'x' " * 600 + "-b 'y'", "gh " + "-b 'a' " * 4000, "git commit " + "-m 'a' " * 4000):
    t = time.perf_counter()
    dg.check(c)
    assert time.perf_counter() - t < 1.0, f"slow ({time.perf_counter() - t:.2f}s): {c[:30]}"

# every reason names the rule (words before the first `. `) and ends with a rewrite hint (the sentence after it)
HINT = re.compile(r"^(?:Use|Run|Ask|Name|Delete|Edit|Spell|Write|Decode|Download|Shorten|Back|Move|Export|Preview|List|Target|Do|Never|Check|Send|Work|Keep|Remove|Dump|Judge|Stage|Pipe|Copy|Quote|Split|Limit|Pass|Prefer|Make|Read|Try|Create|Print|Store|Avoid|Rename|Restore|Reset|Review|Select|Take|Type|Wrap|Stop|Add|Build|Call|Fetch|Install|Set|Start|Show|Unset|Echo|Open|Rewrite)\b")
tree = ast.parse(G.read_text())
reasons = []
for fn in (n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)):
    for n in ast.walk(fn):
        vals = [n.value] if isinstance(n, (ast.Return, ast.Assign)) and n.value is not None else []
        while vals:
            v = vals.pop()
            if isinstance(v, ast.IfExp):
                vals += [v.body, v.orelse]
            elif isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value:
                reasons.append((n.lineno, v.value))
            elif isinstance(v, ast.JoinedStr):
                reasons.append((n.lineno, "".join(p.value if isinstance(p, ast.Constant) else "{}" for p in v.values)))
doc = {f.body[0].value.value for f in ast.walk(tree) if isinstance(f, ast.FunctionDef) and f.body and isinstance(f.body[0], ast.Expr) and isinstance(getattr(f.body[0], "value", None), ast.Constant)}
reasons = [(l, t) for l, t in reasons if len(t) > 25 and t not in doc and " " in t.split(". ")[0] and "\\" not in t[:2]]
assert len(reasons) > 80, f"reason extraction broke ({len(reasons)})"
bad = [(l, t) for l, t in reasons if len(t.partition(". ")[0].split()) < 2 or not HINT.match(t.partition(". ")[2])]
assert not bad, "reasons without a rewrite hint:\n" + "\n".join(f"line {l}: {t!r}" for l, t in bad)
print(f"guard wave-9 regressions: ok ({len(reasons)} reasons)")
