#!/usr/bin/env python3
"""perun_doctor.orphan_dbs: a DB server whose data dir is gone (its worktree was removed) is reported; live dirs, other
processes and relative paths are not. The doctor only reports; it never kills."""
import os, sys, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
import perun_doctor

live = tempfile.mkdtemp(prefix="dcr-doctor-db.")
gone = os.path.join(live, "worktrees", "wt-gone", "pgdata")
ps = "\n".join([
    f"101 /usr/lib/postgresql/16/bin/postgres -D {gone} -p 5433",
    f"102 /usr/bin/postgres -D {live}",
    f"103 mongod --dbpath {gone}",
    f"104 redis-server --dir {gone}",
    f"105 vim -D {gone}",
    "106 postgres -D relative/dir",
])
got = perun_doctor.orphan_dbs(ps)
assert got == [(101, gone), (103, gone), (104, gone)], got

assert perun_doctor.orphan_dbs("") == []
# a live data dir whose path holds a space is not an orphan; a gone one still is
sp = os.path.join(live, "My Projects", "pgdata"); os.makedirs(sp)
assert perun_doctor.orphan_dbs(f"201 postgres -D {sp} -p 1\n202 postgres -D {gone} -p 1") == [(202, gone)]
# ps failure -> INFO row; DCR_NO_PROBE skips the row. Fake ps first on PATH.
import pathlib, stat
fake = tempfile.mkdtemp(prefix="dcr-fake-ps."); ps_bin = pathlib.Path(fake, "ps")
def rows(script, probe_off):
    ps_bin.write_text(script); ps_bin.chmod(0o755)
    os.environ["PATH"] = fake + os.pathsep + os.environ["PATH"]
    os.environ["DCR_NO_PROBE"] = "1" if probe_off else ""
    return [r for r in perun_doctor.check(pathlib.Path(live), pathlib.Path(live)) if r[1] == "orphan dev DBs"]
r = rows("#!/bin/sh\nexit 1\n", False); assert r and r[0][0] == "INFO" and "ps unreadable" in r[0][2], r
r = rows(f"#!/bin/sh\necho '301 postgres -D {gone}'\n", False); assert r[0][0] == "WARN" and "kill -TERM 301" in r[0][2], r
assert rows("#!/bin/sh\nexit 1\n", True) == []
print("ok: orphan dev DBs reported, live and unrelated processes ignored")
