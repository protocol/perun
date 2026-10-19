#!/usr/bin/env python3
"""Offline tests for bench_check rule e: SHA256-frozen.txt entries must still hash to their frozen bytes.

Each test drives the CLI entry point main() on a fixture bench, so they fail on a checker without rule e.
"""
import contextlib, hashlib, io, json, shutil, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bench_check as bc


def sha(b):
    return hashlib.sha256(b).hexdigest()


def run(*dirs):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = bc.main([str(x) for x in dirs])
    return code, out.getvalue()


def freeze(d, entries):
    """Write SHA256-frozen.txt hashing entries {listed path: bytes frozen} and a ledger whose prereg line hashes it."""
    d.mkdir(parents=True, exist_ok=True)
    frozen = "".join(f"{sha(b)}  {p}\n" for p, b in entries.items()).encode()
    (d / "SHA256-frozen.txt").write_bytes(frozen)
    ev = [{"event": "preregistered", "sha256": sha(frozen)[:16], "ts": 1}, {"model": "m", "ts": 2}]
    (d / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")


def test_untouched_passes(tmp):
    d, B, P, X = tmp / "bench", b"print(1)\n", b"hi\n", b"{}\n"
    d.mkdir()
    (d / "driver.py").write_bytes(B)
    (d / "prompts").mkdir()
    (d / "prompts" / "p.txt").write_bytes(P)
    (tmp / "sib").mkdir()
    (tmp / "sib" / "x.json").write_bytes(X)
    freeze(d, {"driver.py": B, "prompts/p.txt": P, "../sib/x.json": X})  # bench-relative, nested, ../sibling
    code, out = run(d)
    assert code == 0 and "clean" in out, out


def test_edited_frozen_file_fails(tmp):
    d, B = tmp / "bench", b"print(1)\n"
    d.mkdir()
    freeze(d, {"driver.py": B})
    (d / "driver.py").write_bytes(b"print(2)  # edited after the freeze\n")
    code, out = run(d)
    assert code == 1 and "driver.py changed after the freeze" in out, out


def test_missing_frozen_file_fails(tmp):
    d = tmp / "bench"
    freeze(d, {"driver.py": b"print(1)\n"})  # listed, never written
    code, out = run(d)
    assert code == 1 and "driver.py is missing" in out, out


def test_malformed_line_fails(tmp):
    d = tmp / "bench"
    freeze(d, {})
    (d / "SHA256-frozen.txt").write_text("not-a-hash  driver.py\n")  # fail closed, never silently skipped
    code, out = run(d)
    assert code == 1 and "is not '<sha256>  <path>'" in out, out


def test_root_relative_entry(tmp):
    repo, T = tmp / "repo", b"x = 1\n"
    (repo / "docs" / "bench").mkdir(parents=True)
    (repo / "scripts").mkdir()
    tool, d = repo / "scripts" / "tool.py", repo / "docs" / "bench" / "b"
    tool.write_bytes(T)
    freeze(d, {"scripts/tool.py": T})  # root-relative: only the repo-root base holds the file
    old, bc.REPO = bc.REPO, repo
    try:
        code, out = run(d)
        assert code == 0 and "clean" in out, out
        tool.write_bytes(T + b"y = 2\n")
        code, out = run(d)
        assert code == 1 and "scripts/tool.py changed after the freeze" in out, out
    finally:
        bc.REPO = old


def git_repo(tmp):
    """Init tmp as a git repo; return a runner that commits with a fixed identity."""
    import subprocess
    g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(tmp), *a],
                                  check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    g("commit", "-qm", "base", "--allow-empty")
    return g


def test_landed_bench_frozen_inputs_immutable(tmp):
    d, T = tmp / "docs" / "bench" / "b", b"x = 1\n"
    d.mkdir(parents=True, exist_ok=True)
    (tmp / "scripts").mkdir()
    (d / "driver.py").write_bytes(T)
    (d / "README.md").write_bytes(T)
    (tmp / "scripts" / "tool.py").write_bytes(T)
    (d / "link.py").symlink_to("driver.py")
    (d / "real.py").write_bytes(T)
    (d / "alias.py").symlink_to("real.py")  # listed only through a link
    (d / "realdir").mkdir()
    (d / "realdir" / "f.txt").write_bytes(T)
    (d / "sub").symlink_to("realdir")
    (d / "realdir" / "deeper").mkdir()
    (d / "realdir" / "deeper" / "k.txt").write_bytes(T)
    (d / "realdir" / "h.txt").write_bytes(T)
    (d / "lnk").symlink_to("realdir/deeper")  # "lnk/.." is realdir, not the bench dir
    (d / "loop").symlink_to("loop")  # a link cycle must not hang the check
    (tmp / "shared").symlink_to("docs/bench/b/realdir")  # a repo-root link into the bench dir
    (tmp / "scripts" / "other.txt").write_bytes(T)
    freeze(d, {"driver.py": T, "scripts/tool.py": T, "link.py": T, "alias.py": T, "sub/f.txt": T,
                "loop/x": T, "shared/g.txt": T, "lnk/../h.txt": T})
    (d / "realdir" / "g.txt").write_bytes(T)
    c = tmp / "docs" / "bench" / "c"
    c.mkdir()
    (c / "SHA256-frozen.txt").write_text("not a hash line\n")
    (c / "README.md").write_text("notes\n")
    g = git_repo(tmp)
    g("add", "-A")
    g("commit", "-qm", "land")
    g("branch", "base")
    cases = [  # (edit after landing, expected error substrings; none means it must pass)
        (lambda: (d / "driver.py").write_bytes(b"x = 2\n"), ["driver.py touched"]),
        (lambda: (d / "README.md").write_bytes(b"notes\n") or (d / "ledger.jsonl").open("a").write("{}\n"), []),
        (lambda: (tmp / "scripts" / "tool.py").write_bytes(b"x = 2\n"), []),  # shared tools may evolve
        (lambda: g("rm", "-q", "docs/bench/b/SHA256-frozen.txt") and (d / "driver.py").write_bytes(b"x = 2\n"),
         ["SHA256-frozen.txt: touched", "driver.py touched"]),
        (lambda: g("mv", "docs/bench/b/SHA256-frozen.txt", "docs/bench/b/old.txt") and (d / "driver.py").write_bytes(b"x = 2\n"),
         ["SHA256-frozen.txt: touched", "driver.py touched"]),
        (lambda: (d / "link.py").unlink() or (d / "link.py").symlink_to("../../../scripts/tool.py"), ["link.py touched"]),
        (lambda: (d / "real.py").write_bytes(b"x = 2\n"), ["alias.py touched"]),
        (lambda: (d / "realdir" / "f.txt").write_bytes(b"x = 2\n"), ["sub/f.txt touched"]),
        (lambda: (d / "realdir" / "g.txt").write_bytes(b"x = 2\n"), ["shared/g.txt touched"]),
        (lambda: (d / "realdir" / "h.txt").write_bytes(b"x = 2\n"), ["lnk/../h.txt touched"]),
        (lambda: (tmp / "shared").unlink() or (tmp / "shared").symlink_to("scripts"), ["shared/g.txt touched"]),
        (lambda: (d / "sub").unlink() or (d / "sub").symlink_to("../../../scripts"), ["sub/f.txt touched"]),
        (lambda: (c / "README.md").write_text("n\n"), ["c/SHA256-frozen.txt: line 1 is not"]),
    ]
    for k, (edit, want) in enumerate(cases):
        edit()
        g("add", "-A")
        g("commit", "-qm", "pr", "--allow-empty")  # --changed diffs committed trees, not the worktree
        code, out = run("--changed", "base")
        assert code == (1 if want else 0) and all(w in out for w in want), (k, out)
        g("reset", "-q", "--hard", "base")


def test_outside_and_unreadable_paths_fail_closed(tmp):
    d, T = tmp / "docs" / "bench" / "b", b"x = 1\n"
    freeze(d, {})
    out = tmp.parent / f"{tmp.name}-secret.txt"
    out.write_bytes(T)
    try:
        (d / "SHA256-frozen.txt").write_text(f"{sha(T)}  ../../../{out.name}\n{sha(T)}  ./../../../{out.name}\n"
                                            f"{sha(T)}  {out}\n{sha(T)}  a\0b\n")
        code, msg = run(d)  # paths outside REPO are never read, and a NUL path is unreadable: all count as missing
        assert code == 1 and msg.count("is missing") == 4, msg
    finally:
        out.unlink()
    n = tmp / "docs" / "bench" / "n"  # a list or ledger linked to a file outside the checkout is never read
    n.mkdir()
    lst = tmp.parent / f"{tmp.name}-list.txt"
    lst.write_text(f"{'a' * 64}  OUTSIDE_LINE\n")
    try:
        (n / "SHA256-frozen.txt").symlink_to(lst)
        (n / "ledger.jsonl").symlink_to(lst)
        code, msg = run(n)
        assert code == 1 and "OUTSIDE_LINE" not in msg and "resolves outside the repo" in msg, msg
        assert "symlink leads outside the repo" in msg, msg
    finally:
        lst.unlink()
    shutil.rmtree(n)
    lb, sec = tmp / "docs" / "bench" / "l", tmp.parent / f"{tmp.name}-scen.json"  # another bench linked out
    text = "one two three four five six seven eight nine ten eleven twelve"
    sec.write_text(json.dumps([{"id": "s1", "text": text}]))
    lb.mkdir()
    (lb / "scenarios_leak.json").symlink_to(sec)
    (d / "scenarios_held.json").write_text(json.dumps([{"id": "h1", "text": text}]))
    try:
        code, msg = run(d)  # the outside file is never read, so no overlap oracle exposes it
        assert code == 1 and "not read as another bench" in msg and "shingles" not in msg, msg
    finally:
        sec.unlink()
    shutil.rmtree(lb)
    (d / "scenarios_held.json").unlink()
    (d / "a.txt").write_bytes(T)
    freeze(d, {"a.txt": T})
    with (d / "SHA256-frozen.txt").open("ab") as f:
        f.write(b"\xff\xfe  x\n")  # non-UTF-8 line after the prereg hash: reported, not a traceback
    code, msg = run(d)
    assert code == 1 and "after the preregistered hash" in msg, msg
    (d / "abs").symlink_to(d / "a.txt")  # absolute target, even back into the repo
    (d / "re").symlink_to(f"../../../../{tmp.name}/docs/bench/b/a.txt")  # leaves the checkout, re-enters
    for i in range(41):  # a chain longer than 40 hops cannot be followed
        (d / f"l{i}").symlink_to(f"l{i + 1}" if i < 40 else "a.txt")
    (d / "SHA256-frozen.txt").write_text(f"{sha(T)}  abs\n{sha(T)}  re\n{sha(T)}  l0\n{sha(T)}  {d / 'a.txt'}\n")
    code, msg = run(d)  # escaping links, over-long chains and absolute paths count as missing, so none can be frozen
    assert code == 1 and msg.count("is missing") == 4, msg
    import time
    t0 = time.monotonic()
    assert bc.aliases("a/../" * 200000 + "a.txt", {}.get)[1] == "/"  # over 1024 components fails closed
    assert bc.aliases("a/" * 400000 + "f", bc.disk_link)[1] == "/"
    assert bc.aliases("a/x\0y", {}.get)[1] == "/" and bc.aliases("l/f", {"l": "a\0b"}.get)[1] == "/"
    assert time.monotonic() - t0 < 2, "path walk is not bounded"  # an unbounded walk takes minutes here


def test_changed_catches_rename_and_space_paths(tmp):
    d, T = tmp / "docs" / "bench" / "b", b"x = 1\n"
    d.mkdir(parents=True, exist_ok=True)
    (d / "my driver.py").write_bytes(T)
    freeze(d, {"my driver.py": T})
    g = git_repo(tmp)
    g("add", "-A")
    g("commit", "-qm", "land")
    g("branch", "base")
    cr = tmp / "docs" / "bench" / "c\rd"  # git output must not be newline-translated
    (cr / "drv.py").parent.mkdir()
    (cr / "drv.py").write_bytes(T)
    freeze(cr, {"drv.py": T})
    g("add", "-A")
    g("commit", "-qm", "land cr")
    g("branch", "-f", "base")
    g("mv", "docs/bench/b/my driver.py", "docs/bench/b/moved.py")  # a rename must not hide the frozen path
    (cr / "drv.py").write_bytes(b"x = 2\n")
    g("add", "-A")
    g("commit", "-qm", "pr")
    code, out = run("--changed", "base")
    assert code == 1 and "my driver.py touched after the freeze" in out and "drv.py touched" in out, out
    g("reset", "-q", "--hard", "base")  # CRLF bytes committed, then a later eol rule hides them from a worktree diff
    (d / "my driver.py").write_bytes(T.replace(b"\n", b"\r\n"))
    g("add", "-A")
    g("commit", "-qm", "crlf")
    (tmp / ".gitattributes").write_text("docs/bench/** text eol=lf\n")
    g("add", ".gitattributes")
    g("commit", "-qm", "attrs")
    code, out = run("--changed", "base")
    assert code == 1 and "my driver.py touched after the freeze" in out, out


TESTS = [test_changed_catches_rename_and_space_paths, test_untouched_passes, test_edited_frozen_file_fails, test_missing_frozen_file_fails,
         test_malformed_line_fails, test_root_relative_entry, test_landed_bench_frozen_inputs_immutable,
         test_outside_and_unreadable_paths_fail_closed]

for t in TESTS:
    tmp = Path(tempfile.mkdtemp()).resolve()
    (tmp / "docs" / "bench").mkdir(parents=True)
    old, bc.REPO = bc.REPO, tmp  # frozen paths must resolve inside REPO
    try:
        t(tmp)
    finally:
        bc.REPO = old
        shutil.rmtree(tmp)
print(f"test_bench_check_frozen: Tests: {len(TESTS)}/{len(TESTS)} ok")
