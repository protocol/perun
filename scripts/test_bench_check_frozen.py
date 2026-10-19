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


def test_landed_bench_frozen_inputs_immutable(tmp):
    repo = tmp / "repo"
    root, T = repo / "docs" / "bench", b"x = 1\n"
    d = root / "b"
    d.mkdir(parents=True)
    (repo / "scripts").mkdir()
    (d / "driver.py").write_bytes(T)
    (repo / "scripts" / "tool.py").write_bytes(T)
    freeze(d, {"driver.py": T, "scripts/tool.py": T})
    old, bc.REPO = bc.REPO, repo
    try:
        ft = lambda *paths, new=(): bc.frozen_touched(root, list(new), set(paths))
        assert any("driver.py edited after the freeze" in e for e in ft("docs/bench/b/driver.py"))
        assert any("SHA256-frozen.txt: edited" in e for e in ft("docs/bench/b/SHA256-frozen.txt"))
        assert ft("docs/bench/b/README.md", "docs/bench/b/ledger.jsonl") == []  # notes, ledger appends
        assert ft("scripts/tool.py") == []  # shared tools outside the dir may evolve
        assert ft("docs/bench/b/driver.py", new=[d]) == []  # a new dir is gated by the full check instead
    finally:
        bc.REPO = old


TESTS = [test_untouched_passes, test_edited_frozen_file_fails, test_missing_frozen_file_fails,
         test_malformed_line_fails, test_root_relative_entry, test_landed_bench_frozen_inputs_immutable]

for t in TESTS:
    tmp = Path(tempfile.mkdtemp())
    try:
        t(tmp)
    finally:
        shutil.rmtree(tmp)
print(f"test_bench_check_frozen: Tests: {len(TESTS)}/{len(TESTS)} ok")
