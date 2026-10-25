#!/usr/bin/env python3
"""Wave-4 destructive_guard regressions: sqlite3 dot-commands and ATTACH, `kubectl run|debug`/`oc debug|rsh` commands,
the /private alias for rm, and `$VAR/../..` write targets. Offline."""
import importlib.util, pathlib, time

G = pathlib.Path(__file__).resolve().parent.parent / ".claude/skills/agentic-delivery/scripts/destructive_guard.py"
spec = importlib.util.spec_from_file_location("dg", G)
dg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dg)

BAD = [
    "sqlite3 :memory: '.shell rm -rf /'", "sqlite3 app.db '.system rm -rf $X'", "sqlite3 app.db '.sh rm -rf ~'",
    "sqlite3 app.db -cmd '.shell rm -rf /' ''", "sqlite3 :memory: '.read |rm -rf /'", "sqlite3 app.db <<< '.shell rm -rf /'",
    "sqlite3 :memory: \"ATTACH '/etc/passwd' AS a\"", "sqlite3 app.db \"attach database '/var/db/x' as a\"", "sqlite3 app.db '.open /etc/x'",
    "sqlite3 app.db <<'EOF'\n.shell rm -rf /\nEOF",
    "kubectl run x --image=a -- rm -rf /data", "kubectl -n p debug pod -it --image=a -- sh -c 'rm -rf $X'", "oc debug dc/x -- rm -rf /",
    "oc rsh pod rm -rf /data", "oc -n p rsh -c ctr pod rm -rf /",
    "rm -rf /private/var/db/x", "rm -rf /private/var/root/a/b", "rm -rf /private/etc/ssh/x/y", "find /private/var/db -delete",
    "echo x >> $HOME/../../etc/hosts", "echo x | tee -a ${HOME}/../../etc/x", "echo x > ~/../../etc/x", "echo x >> \"$D\"/../etc/x",
]
GOOD = [
    "sqlite3 app.db '.tables'", "sqlite3 :memory: 'select 1'", "sqlite3 app.db '.shell ls'", "sqlite3 app.db \"attach 'other.db' as o\"",
    "kubectl run x --image=a -- ls", "oc debug dc/x -- ls /", "oc rsh pod ls", "kubectl run x --image=a",
    "rm -rf /private/var/folders/ab/T/x", "rm -rf /private/tmp/x/y", "echo x >> $HOME/notes", "echo x >> $HOME/../shared/log.txt",
    "echo x >> $HOME/../../var/log/x", "echo x >> $TMPDIR/a",
]
for c in BAD:
    assert dg.check(c), f"missed: {c}"
for c in GOOD:
    assert not dg.check(c), f"false positive: {c}"
for c in ("sqlite3 :memory: '" + ".shell x\n" * 800 + "'", "sqlite3 x " + "attach 'a' as b; " * 600, "echo x >> $H" + "/.." * 3300 + "/etc/x",
          "kubectl run " + "-- " * 3000, "oc rsh " + "p " * 5000):
    t = time.perf_counter()
    dg.check(c)
    assert time.perf_counter() - t < 2.0, f"slow: {c[:30]}"
print("guard wave-4 regressions: ok")
