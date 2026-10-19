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
    freeze(d, {"driver.py": T, "scripts/tool.py": T, "link.py": T})
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
    ]
    for edit, want in cases:
        edit()
        code, out = run("--changed", "base")
        assert code == (1 if want else 0) and all(w in out for w in want), out
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
    (d / "a.txt").write_bytes(T)
    freeze(d, {"a.txt": T})
    with (d / "SHA256-frozen.txt").open("ab") as f:
        f.write(b"\xff\xfe  x\n")  # non-UTF-8 line after the prereg hash: reported, not a traceback
    code, msg = run(d)
    assert code == 1 and "after the preregistered hash" in msg, msg


def test_changed_catches_rename_and_space_paths(tmp):
    d, T = tmp / "docs" / "bench" / "b", b"x = 1\n"
    d.mkdir(parents=True, exist_ok=True)
    (d / "my driver.py").write_bytes(T)
    freeze(d, {"my driver.py": T})
    g = git_repo(tmp)
    g("add", "-A")
    g("commit", "-qm", "land")
    g("branch", "base")
    g("mv", "docs/bench/b/my driver.py", "docs/bench/b/moved.py")  # a rename must not hide the frozen path
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
