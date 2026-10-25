#!/usr/bin/env python3
"""Wave-3 destructive_guard regressions: container/kubectl passthrough, `>>`/tee onto system files, nested decode-exec,
the decode cap only failing closed with a decoder present, and linear timing on 10k-char adversarial inputs. Offline."""
import importlib.util, pathlib, time

G = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", G)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

BAD = [
    "docker run --rm -v /:/host alpine rm -rf /host/etc", "docker exec -it web rm -rf /", "podman exec -u root ctr rm -rf $DIR",
    "nerdctl run --name x -e A=1 alpine sh -c 'rm -rf $X'", "docker compose run app rm -rf /var/lib",
    "kubectl exec -n prod pod -- rm -rf /data/*", "kubectl exec pod -- sh -c 'rm -rf $X'", "podman system reset --force",
    "echo x >> /etc/hosts", "echo x >> /root/.bashrc", "echo x | tee /etc/passwd", "echo x | tee -a /var/spool/cron/root",
    "echo x >> /private/etc/hosts", "rm -rf /root/a/b", "rm -rf /private/etc/ssh",
    "eval \"$(echo $(echo $(echo hi)) | base64 -d)\"", "eval $(echo $(date) $(id) | base64 --decode)",
    "eval $(echo aGk= | openssl enc -d -base64)", "eval $(openssl enc -base64 -d <<< x)",
    "bash -c \"$(python3 -c 'import base64;print(base64.b64decode(\"aGk=\").decode())')\"",
    "gh repo delete acme/x --yes", "mv ~/p /dev/null", "curl -X DELETE https://example.com/x", "vault kv metadata delete secret/x",
    "brew uninstall --force --ignore-dependencies git", 'eval "$(echo \'rm -rf /\')"',
]
GOOD = [
    "docker run --rm alpine ls /", "docker exec web rm -rf /tmp/cache", "kubectl exec pod -- ls /data", "kubectl exec -it pod -- bash",
    "echo x >> notes.txt", "echo x | tee out.log", "echo x >> /var/tmp/x", "echo x >> $TMPDIR/x", "tee -a ./log",
    "eval $(echo hi)", "bash -c \"$(echo $(date))\"", "find . -name '*.pyc' -delete", "mkfs.ext4 -n /dev/sdb1",
    "sqlite3 :memory: 'DROP TABLE t'", "python3 -c 'import shutil, tempfile; shutil.rmtree(tempfile.mkdtemp())'",
    "curl -X POST https://example.com/x", "gh repo view acme/x", "mv a b",
]
BAD += [
    "docker run --entrypoint sh alpine -c 'rm -rf $X'", "docker run --entrypoint=sh alpine -c 'rm -rf /'", "docker run --pull always alpine rm -rf /",
    "docker run --gpus all --ip 10.0.0.2 --runtime x alpine rm -rf /data", "docker container exec c rm -rf /", "docker-compose exec web rm -rf /",
    "docker compose -f a.yml exec web rm -rf /", "kubectl exec pod rm -rf /data/x", "oc exec pod -- rm -rf /", "podman run --pull=never alpine rm -rf /",
    "docker exec c " * 500 + "ls", "echo x >> ../../etc/hosts", "echo x > /Etc/passwd", "echo x >> /private/var/db/x", "echo x | tee /var/log/x",
    "echo x > /var/log/x", "find . -name '*.pyc' -o -name x -delete", "find . -name '*.py' -delete", "find . -type f -name '*.pyc' -delete",
    "mkfs.ext4 -L -n /dev/sdb1", "sqlite3 :memory: '.shell x; DROP TABLE t'", "sqlite3 :memory: \"ATTACH 'x' AS a; DROP TABLE a.t\"",
    "python3 -c 'import shutil; shutil.rmtree(tempfile.mkdtemp() + \"/../..\")'",
]
GOOD += ["echo x >> /var/log/app.log", "tee -a /var/log/app.log", "docker run --pull always alpine ls", "kubectl exec pod ls", "mkfs.ext4 -L lbl -n /dev/sdb1"]
for c in BAD:
    assert dg.check(c), f"missed: {c}"
for c in GOOD:
    assert not dg.check(c), f"false positive: {c}"
assert dg.check("find / -name '*.pyc' -delete") and dg.check("find .. -name '*.pyc' -delete")

# the decode cap fails closed only when a decoder is present: 9 substitutions and 70 shell words, no decoder -> allowed
assert not dg.check("eval " + "$(date) " * 9)
assert not dg.check("eval x; " * 70)
assert dg.check("eval " + "$(date) " * 9 + " base64 -d")
assert dg.check("eval x; " * 70 + "base64 -d")

# linear timing, 10k-char adversarial inputs
ADV = ["eval $(" * 1500, "eval $(echo " + "$(" * 3000 + "base64 -d" + ")" * 3000, "eval `" * 1700, "docker run " + "-e a " * 2000 + "alpine ls",
       "kubectl exec p " + "-- " * 3000, "openssl enc " * 800, "python " + "b64decode " * 1000, "echo x >> " + "/etc/" * 2000, "tee " + "-a " * 3300,
       "base64 " * 1400 + "eval $(" * 60, "docker exec " + "x " * 5000]
for c in ADV:
    t = time.perf_counter()
    dg.check(c)
    assert time.perf_counter() - t < 2.0, f"slow ({time.perf_counter() - t:.1f}s): {c[:40]}"
print("guard wave-3 regressions: ok")
