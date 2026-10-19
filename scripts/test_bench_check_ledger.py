#!/usr/bin/env python3
"""Offline tests for bench_check ledger_errs scaling and for an unreadable --against ref (one-line error, no traceback)."""
import contextlib, hashlib, io, json, shutil, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bench_check as bc

sha = lambda b: hashlib.sha256(b).hexdigest()


def test_ledger_scales_linearly_and_keeps_verdicts(tmp):
    d = tmp / "b"
    d.mkdir()
    frozen = "".join(f"{sha(str(i).encode())}  f{i}.py\n" for i in range(4000)).encode()
    lines = frozen.splitlines(keepends=True)
    (d / "SHA256-frozen.txt").write_bytes(frozen)
    covered = [{"event": "amendment", "sha": l.split()[0].decode()[:16], "ts": 3} for l in lines[1:]]
    ev = [{"event": "preregistered", "sha256": sha(lines[0])[:16], "ts": 1}, {"model": "m", "ts": 2}] + covered
    (d / "ledger.jsonl").write_text("\n".join(map(json.dumps, ev)) + "\n")
    t = time.time()
    assert bc.ledger_errs(d) == []
    assert time.time() - t < 2, "ledger_errs is no longer single-pass"
    (d / "ledger.jsonl").write_text("\n".join(map(json.dumps, ev[:-1])) + "\n")  # last line uncovered
    errs = bc.ledger_errs(d)
    assert len(errs) == 1 and lines[-1].decode().strip() in errs[0], errs


def test_unsafe_ref_is_one_line_error(tmp):
    g = lambda *a: subprocess.run(["git", "-c", "user.name=t", "-c", "user.email=t@example.com", "-C", str(tmp), *a],
                                  check=True, capture_output=True)
    g("init", "-q", "-b", "main")
    (tmp / "docs/bench/x").mkdir(parents=True)
    (tmp / "docs/bench/x/link").symlink_to("/etc/passwd")
    g("add", "-A")
    g("commit", "-qm", "link")
    try:
        bc.main(["--against", "main"])
        raise AssertionError("expected SystemExit")
    except SystemExit as e:
        msg = str(e)
    assert msg.startswith("bench_check: docs/bench at main cannot be read safely") and "\n" not in msg, msg


TESTS = [test_ledger_scales_linearly_and_keeps_verdicts, test_unsafe_ref_is_one_line_error]
for t in TESTS:
    tmp = Path(tempfile.mkdtemp()).resolve()
    (tmp / "docs/bench").mkdir(parents=True, exist_ok=True)
    old, bc.REPO = bc.REPO, tmp
    try:
        t(tmp)
    finally:
        bc.REPO = old
        shutil.rmtree(tmp)
print(f"test_bench_check_ledger: Tests: {len(TESTS)}/{len(TESTS)} ok")
