#!/usr/bin/env python3
"""Wave-10 destructive_guard regressions (written against held-out-13 misses and the wave-9 review leads): ssh-add -D, git update-ref -d, rm of .git,
compose down -v/--rmi, Remove-Item fed from a pipeline, cipher /w, `--help`/`-h` allowed on any verb, a payload piped to or written then run by a shell
(pipe, heredoc, echo > file, tee >(sh), eval "$(cat)", ssh/docker/kubectl heredoc), gh/git aliases and git config values that run commands, more credential
deletes, `gpg --delete-secret-keys=X`, `tee key </dev/null`, and the wave-9 false positive on a bare `rm credentials`. Data payloads stay allowed.
Offline; commands are only classified."""
import importlib.util, pathlib, time

G = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", G)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

BAD = [
    "ssh-add -D", "ssh-add --delete-all", "git update-ref -d refs/heads/main", "git update-ref --delete refs/tags/v1", "rm -rf .git", "rm -rf ./.git/", "rm -r build/.git",
    "rm -rf .git/objects", "rm -rf .git/*", "sudo docker compose down -v --rmi all", "docker compose down --volumes", "docker-compose down -v", "docker compose down --rmi local",
    'pwsh -c "Get-ChildItem C:\\acme -Recurse | Remove-Item -Force"', "powershell -Command \"gci . | Remove-Item\"", "cipher /w:C:\\acme", "cipher /W:D:",
    "git commit -m x | bash", "git commit -F script.sh | sh", "gh issue create --body x | sh", "git log | sh", "echo 'rm -rf /' | tee x.sh | sh",
    "xargs <<EOF\nrm -rf /\nEOF", "tee x.sh <<EOF\nrm -rf /\nEOF\nsh x.sh", "cat > a.sh <<EOF\nrm -rf /\nEOF\nbash a.sh", "cat <<EOF > a.sh\nrm -rf /\nEOF\nchmod +x a.sh && ./a.sh",
    "echo 'rm -rf /' > x.sh && sh x.sh", "printf 'rm -rf /\\n' > x.sh; bash < x.sh", "echo 'rm -rf /' | tee x.sh; sh x.sh", "tee >(sh) <<EOF\nrm -rf /\nEOF",
    'eval "$(cat)" <<EOF\nrm -rf /\nEOF', "eval \"$(cat)\" <<< 'rm -rf /'", "echo 'rm -rf /' | eval \"$(cat)\"", 'bash -c "$(cat)" <<EOF\nrm -rf /\nEOF',
    "ssh host <<EOF\nrm -rf /\nEOF", "ssh -p 22 host sh <<EOF\nrm -rf /\nEOF", "docker exec -i c sh <<EOF\nrm -rf /\nEOF", "kubectl exec -i p -- bash <<EOF\nrm -rf /\nEOF",
    "gh alias set -s x 'rm -rf /'", "gh alias set x 'api -X DELETE repos/o/r'", "git config alias.c '!rm -rf /'", "git config --global alias.c '!rm -rf /'",
    "git -c alias.c='!rm -rf /' c", "git -c core.sshCommand='rm -rf /' commit", "git config core.pager 'rm -rf /'", "git -c core.editor='sh -c \"rm -rf /\"' commit",
    "unlink ~/.netrc", "rm key.pem", "rm ~/.npmrc", "rm ~/.pypirc", "rm ~/.config/gh/hosts.yml", "rm ~/.ssh/config", "rm $HOME/.ssh/*", "rm ~/.aws/sso/cache/x.json",
    "gpg --delete-secret-keys=X", "gpg --delete-keys=X", "tee server.key </dev/null", "cat /dev/null | tee ~/.ssh/id_rsa",
    "rsync -a --delete empty/ /data/ -h", "docker exec c bash -c 'rm -rf /' -h", "kubectl exec p -- sh -c 'rm -rf /' -h", "docker system prune -af -h", "terraform destroy -auto-approve -h",
    "shutdown now -h", "git -c core.pager='rm -rf /' log", "git config diff.external 'rm -rf /'", "git config pager.log 'rm -rf /'", "git config core.hooksPath /tmp/h", "git -c include.path=/tmp/x status",
    "ssh host 'bash -s' <<EOF\nrm -rf /\nEOF", "eval \"$(cat <<'X'\nrm -rf /\nX\n)\"", "printf '%s' 'rm -rf ~' > r.sh; sh r.sh", "csh -c 'rm -rf /'", "tcsh -c 'rm -rf $X'", "pwsh -c 'rm -rf /'",
]
GOOD = [
    "git filter-branch --help", "git filter-branch -h", "git reset -h", "git clean --help", "terraform destroy --help", "terraform destroy -h", "kubectl delete ns --help",
    "ssh-add -l", "ssh-add ~/.ssh/id_ed25519", "ssh-add -d ~/.ssh/id_old", "git update-ref refs/heads/x HEAD", "git update-ref -m msg refs/heads/x HEAD",
    "rm .git/index.lock", "rm -rf /tmp/w/.git", "rm -rf build/gitx", "docker compose down", "docker compose up -d", "docker-compose stop", "docker compose logs -f",
    'pwsh -c "Remove-Item -Path .\\build\\a.txt -Force"', 'pwsh -c "Get-ChildItem *.tmp | Remove-Item -WhatIf"', "cipher /e secret.txt",
    "git commit -m 'git log | sh'", "gh issue create --body 'x | bash'", "gh pr comment 3 --body 'ssh-add -D'", "git commit -m 'rm -rf .git'", "gh pr comment 3 --body 'git update-ref -d refs/heads/main'",
    "git commit -m 'docker compose down -v'", "git commit -m 'git config alias.c \"!rm -rf /\"'", "gh pr create --body 'gh alias set -s x \"rm -rf /\"'",
    "git commit -m 'x' -m 'rm -rf /'", "cat a.txt | python3 -m json.tool", "git log --oneline | head -3",
    "xargs <<EOF\na b c\nEOF", "cat > a.sh <<EOF\nrm -rf /\nEOF", "cat > a.sh <<EOF\necho hi\nEOF\nbash a.sh", "cat <<EOF > notes.md\nrm -rf /\nEOF",
    "echo 'rm -rf /' > notes.txt", "echo 'echo hi' > x.sh && sh x.sh", "tee x.log <<EOF\nrm -rf /\nEOF\nsh y.sh",
    'eval "$(cat)" <<EOF\necho hi\nEOF', "echo 'echo hi' | eval \"$(cat)\"", "ssh host <<EOF\nls\nEOF", "ssh host 'cat > /tmp/x' <<EOF\nrm -rf /\nEOF",
    "docker exec -i c sh <<EOF\nls /\nEOF", "docker exec -i c tee /f <<EOF\nrm -rf /\nEOF",
    "gh alias set co 'pr checkout'", "gh alias set -s x 'echo hi'", "git config alias.st status", "git config --global user.name x", "git -c core.sshCommand='ssh -i k' fetch",
    "git -c core.editor=vim commit", "rm -rf src/secrets", "rm -f dist/key", ": > token", "cp /dev/null key", "tee key </dev/null", "git config core.hooksPath .githooks", "git config pager.log less", "rsync -h", "ls -h", "df -h", "du -sh .",
    "rm credentials", "rm -f credentials", "rm /tmp/credentials", "rm ~/.ssh/known_hosts", "rm -f build/out.json", "tee out.log </dev/null",
    "gpg --list-keys", "gpg --export-secret-keys X",
]
for c in BAD:
    assert dg.check(c), f"missed: {c!r}"
for c in GOOD:
    assert not dg.check(c), f"false positive: {c!r}: {dg.check(c)}"
for c in ("echo x > f; " * 2000 + "sh f", "cat > a.sh <<EOF\n" + "x\n" * 5000 + "EOF\nbash a.sh", "git -c a=b " * 2000 + "status", "tee >(x) " * 2000):
    t = time.perf_counter()
    dg.check(c)
    assert time.perf_counter() - t < 2.0, f"slow ({time.perf_counter() - t:.2f}s): {c[:30]}"
print("guard wave-10 regressions: ok")
