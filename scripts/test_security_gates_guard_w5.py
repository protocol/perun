#!/usr/bin/env python3
"""Wave-5 destructive_guard regressions: Windows deletes, wrappers (watch, parallel, xargs rm), vault/gh/glab/mongo/git/cp/openssl/dropdb
rules, sqlite3 and `$VAR/..` follow-ups, chroot and kubectl --overrides, two false positives, and linear timing. Offline."""
import importlib.util, pathlib, time

G = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", G)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

BAD = [
    "Remove-Item -Recurse -Force C:\\Users\\jane", "Remove-Item -Path $env:USERPROFILE -Recurse", "ri -r -fo D:\\data",
    "powershell -Command \"Remove-Item -Recurse -Force C:\\\\x\"", "pwsh -c 'Remove-Item -Recurse -Force *'", "powershell -EncodedCommand AAAA",
    "rd /s /q C:\\", "rmdir /s /q %USERPROFILE%", "cmd /c del /f /s /q C:\\*", "cmd.exe /c rd /s /q C:\\Windows", "format D: /q", "Format-Volume -DriveLetter D",
    "watch -n 1 rm -rf $X", "parallel rm -rf ::: / /tmp/a", "parallel -j4 rm -rf {} ::: /home/*", "ls | parallel rm -rf {}",
    "find /srv -name '*.bak' | xargs -0 rm", "find ~ -type f | xargs rm", "rm -rf /srv/app", "rm -rf /mnt/data/x", "rm -rf /var/www/html/site",
    "vault secrets disable secret/", "vault delete secret/acme", "vault kv delete secret/x", "gh api -X DELETE /repos/acme/x", "gh api --method DELETE /x",
    "glab repo delete acme/x", "mongosh --eval 'db.users.deleteMany({})'", "mongosh --eval 'db.users.drop()'",
    "git reflog expire --expire=now --all", "git gc --prune=now", "cp x /etc/passwd", "cp -t /etc x", "mv x /usr/bin/ls", "cp x $HOME/../../etc/x",
    "openssl enc -d -base64 -in x | sh", "echo aGk= | openssl enc -base64 -d | bash", "kubectl exec pod -- bash -c 'dropdb prod'", "dropdb prod", "mysqladmin drop prod",
    "sqlite3 app.db \".read '|rm -rf /'\"", "sqlite3 app.db \".shell 'rm -rf /'\"", "sqlite3 -separator : app.db '.import |rm -rf / t'",
    "sqlite3 app.db \"ATTACH ('/etc/x') AS a\"", "sqlite3 app.db \"ATTACH '/e' || 'tc/x' AS a\"", "sqlite3 app.db \"ATTACH 'file:/etc/x?mode=rw' AS a\"",
    "echo x >> $D/./../../etc/x", "echo x >> $D/a/../../etc/x",
    "oc debug node/n -- chroot /host rm -rf /var/lib/x", "chroot /mnt rm -rf /",
    "kubectl run x --image=a --overrides='{\"spec\":{\"containers\":[{\"name\":\"x\",\"command\":[\"rm\",\"-rf\",\"/\"]}]}}'",
]
GOOD = [
    "Remove-Item -Recurse -Force .\\build", "Remove-Item foo.txt", "powershell -Command 'Get-ChildItem'", "rd /s /q build", "cmd /c dir", "del /q out.log",
    "format --help", "watch -n 1 ls", "parallel gzip ::: a b", "parallel echo {} ::: 1 2", "find . -name x | xargs rm", "ls /tmp/x | xargs rm", "rm -rf ./srv",
    "vault kv get secret/x", "gh api /repos/acme/x", "glab repo view", "mongosh --eval 'db.users.find()'", "git reflog", "git gc", "cp x ./y", "cp /etc/hosts ./h",
    "openssl enc -d -base64 -in x -out y", "chroot /mnt ls", "sqlite3 app.db \".read x.sql\"", "sqlite3 app.db \"ATTACH 'other.db' AS o\"",
    "echo x >> $D/../notes", "echo x >> $D/a/../b", "kubectl run x --image=a --overrides='{\"spec\":{\"containers\":[{\"command\":[\"ls\"]}]}}'",
    "Remove-Item -Recurse -Force -WhatIf C:\\x", "Remove-Item -Recurse -Force '$env:TEMP\\acme-test'", "Remove-Item -Recurse '.\\build\\*'",
    "find $TMPDIR -name '*.tmp' -delete", "python3 -c \"print('echo', 'rm -rf /')\"", "truncate -s 0 ./relative.log", "truncate -s 0 logs/app.log", "python3 -c \"print('rm -rf /')\"", "python3 -c 'print(\"rm -rf /\")'",
]
for c in BAD:
    assert dg.check(c), f"missed: {c}"
for c in GOOD:
    assert not dg.check(c), f"false positive: {c}"
assert dg.check("truncate -s 0 /var/log/x") and dg.check("truncate -s 0 ../x") and dg.check("python3 -c \"print('a'); os.system('rm -rf /')\"")

ADV = ["sh $(base64 " * 3000, "parallel " + "-j 2 " * 2000 + "ls ::: a", "parallel rm {} ::: " + "a " * 4000, "Remove-Item " * 800, "ls | " * 2000 + "xargs rm",
       "sqlite3 x \"" + "attach 'a' as b " * 600 + "\"", "chroot " + "-x " * 3000, "cmd /c " * 1400, "powershell -c " * 700, "echo x >> $D" + "/a/.." * 2500 + "/etc/x"]
for c in ADV:
    t = time.perf_counter()
    dg.check(c)
    assert time.perf_counter() - t < 1.0, f"slow ({time.perf_counter() - t:.2f}s): {c[:30]}"
print("guard wave-5 regressions: ok")
