#!/usr/bin/env python3
"""perun_doctor "stale local skills" row: a repo-local .claude/skills/<perun skill> older than the global copy WARNs (it shadows
the newer one); equal or newer local is OK; plugin copies are never compared (namespaced); a missing side, unparsable or hostile
version, repo == home, or a symlinked skills dir is INFO n/a. Hermetic: HOME and repo are temp dirs."""
import os, shutil, sys, tempfile
from pathlib import Path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import perun_doctor

os.environ["DCR_NO_PROBE"] = "1"
tmp = Path(tempfile.mkdtemp(prefix="dcr-doctor-stale."))
try:
    repo, home = tmp / "repo", tmp / "home"
    os.environ["HOME"] = str(home)
    N = "idea-critic"  # a Perun skill shipped by this checkout


    def put(root, v, rel=f".claude/skills/{N}/SKILL.md"):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("---\nname: x\nmetadata:\n  version: " + v + "\n---\nbody\n" if v is not None else "no frontmatter\n")


    def clear():
        for r in (repo, home):
            shutil.rmtree(r, ignore_errors=True)
        repo.mkdir(); home.mkdir()


    def row(local, glob, plugin=None):
        clear()
        if local is not None: put(repo, local)
        if glob is not None: put(home, glob)
        if plugin is not None: put(home, plugin, f".claude/plugins/cache/mk/perun/{plugin.strip(chr(34))}/.claude/skills/{N}/SKILL.md")
        got = perun_doctor.shadowed_skills(repo, home)
        assert got == [r[::2] for r in perun_doctor.check(repo, home) if r[1] == "stale local skills"][0], got  # check() carries the same row
        return got

    st, d = row('"1.2.3"', '"1.10.0"')  # numeric, not lexical: 1.10 > 1.2
    assert st == "WARN" and "1.2.3" in d and "1.10.0" in d and str(repo) in d and str(home) in d and "remove or update repo-local copy" in d, (st, d)
    assert row('"1.2.3"', '"1.2.3"')[0] == "OK"
    assert row('"2.0.0"', '"1.9.9"')[0] == "OK"
    assert row(None, '"9.0.0"')[0] == "INFO" and row(None, '"9.0.0"')[1].startswith("n/a")
    assert row('"1.0.0"', None)[0] == "INFO"
    for bad in ('"banana"', '"1.2.x"', "", None):  # garbage on either side compares nothing
        assert row(bad, '"9.0.0"')[0] == "INFO", bad
        assert row('"1.0.0"', bad)[0] == "INFO", bad
    st, d = row('"1.0.0"', None, '"3.0.0"')  # plugin skills are namespaced, never compared
    assert st == "INFO", (st, d)
    st, d = row('"1.0.0"', '"2.0.0"', '"3.0.0"')  # newer plugin copy does not make the local one stale vs a newer-or-equal global
    assert st == "WARN" and "2.0.0" in d and "3.0.0" not in d, (st, d)
    assert row('"1.2"', '"1.2.0"')[0] == "OK" and row('"1.2.0"', '"1.2"')[0] == "OK"  # trailing zeros are not a difference
    assert row('"1.2"', '"1.2.1"')[0] == "WARN"
    huge = "9" * 5000  # int() of 5000 digits raises; the 9-digit cap rejects it first
    assert row(huge, '"1.0.0"')[0] == "INFO" and row('"1.0.0"', huge)[0] == "INFO"
    assert row('"1.2.3.4.5"', '"9.0.0"')[0] == "INFO"  # more than 4 parts

    clear()  # repo == home: the repo's skills dir is the global one
    put(home, '"1.0.0"')
    assert perun_doctor.shadowed_skills(home, home)[0] == "INFO"

    clear()  # repo skills dir is a symlink to the global one: same file, nothing to compare
    put(home, '"2.0.0"')
    (repo / ".claude").mkdir()
    os.symlink(home / ".claude/skills", repo / ".claude/skills")
    st, d = perun_doctor.shadowed_skills(repo, home)
    assert st == "INFO" and d.startswith("n/a"), (st, d)

    for body in ("no frontmatter\n", "intro\n---\nversion: 1.0.0\n---\n"):  # file really written, but frontmatter must lead
        clear()
        put(home, '"2.0.0"')
        (repo / f".claude/skills/{N}").mkdir(parents=True)
        (repo / f".claude/skills/{N}/SKILL.md").write_text(body)
        assert (repo / f".claude/skills/{N}/SKILL.md").read_text() == body
        assert perun_doctor.shadowed_skills(repo, home)[0] == "INFO", body
    clear()  # version past the 8 KB read window is not seen
    (repo / f".claude/skills/{N}").mkdir(parents=True)
    (repo / f".claude/skills/{N}/SKILL.md").write_text("---\nname: x\n" + "#" * 9000 + "\nversion: 1.0.0\n---\n")
    put(home, '"2.0.0"')
    assert perun_doctor.shadowed_skills(repo, home)[0] == "INFO"

    shipped = [d.parent.name for d in sorted((perun_doctor.SRC / ".claude/skills").glob("*/SKILL.md"))]
    assert len(shipped) > 3, shipped
    clear()  # every shipped skill stale: count is all, only 3 named, rest truncated with " ..."
    for n in shipped:
        put(repo, '"1.0.0"', f".claude/skills/{n}/SKILL.md")
        put(home, '"2.0.0"', f".claude/skills/{n}/SKILL.md")
    st, d = perun_doctor.shadowed_skills(repo, home)
    assert st == "WARN" and d.startswith(f"{len(shipped)} repo-local skill(s)") and d.count("is older than") == 3 and " ..." in d, (st, d)
    clear()  # exactly 3 stale: all named, no truncation marker
    for n in shipped[:3]:
        put(repo, '"1.0.0"', f".claude/skills/{n}/SKILL.md")
        put(home, '"2.0.0"', f".claude/skills/{n}/SKILL.md")
    st, d = perun_doctor.shadowed_skills(repo, home)
    assert st == "WARN" and d.startswith("3 repo-local skill(s)") and d.count("is older than") == 3 and " ..." not in d, (st, d)
finally:
    shutil.rmtree(tmp, ignore_errors=True)
print("ok: stale local skill WARNs; equal/newer OK; plugin ignored; missing, garbage, hostile, same-file version n/a")
