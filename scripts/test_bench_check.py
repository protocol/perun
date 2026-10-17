#!/usr/bin/env python3
"""Offline tests for scripts/bench_check.py: one fixture bench, then one defect at a time."""
import hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import bench_check as bc

W = lambda n, k: " ".join(f"{k}{i}" for i in range(n))  # n distinct words


def bench(root, name, tune_text, held_text):
    d = root / name
    (d / "outputs").mkdir(parents=True)
    (d / "SHA256-frozen.txt").write_text(f"{'0' * 64}  PREREGISTERED.md\n")
    (d / "PREREGISTERED.md").write_text("Hashed in SHA256-frozen.txt before any call.\n")
    h = hashlib.sha256((d / "SHA256-frozen.txt").read_bytes()).hexdigest()
    ev = [{"event": "preregistered", "sha256": h[:16], "ts": 1}, {"model": "m", "ts": 2}]
    (d / "ledger.jsonl").write_text("\n".join(json.dumps(e) for e in ev) + "\n")
    (d / "scenarios_tune.json").write_text(json.dumps([{"id": "t1", "prompt": tune_text}]))
    (d / "scenarios_held.json").write_text(json.dumps([{"id": "h1", "prompt": held_text}]))
    return d


def errs(root, d, **kw):
    return bc.check(d, [x for x in root.iterdir() if x.is_dir() and x != d], **kw)


root = Path(tempfile.mkdtemp())
try:
    old = bench(root, "old", W(30, "a"), W(30, "b"))
    (old / "outputs" / "t1.txt").write_text("x")
    new = bench(root, "new", W(30, "c"), W(30, "d"))
    assert errs(root, new) == [], errs(root, new)
    # b. accepted aliases: event "prereg_frozen" with key "sha"
    lj = (new / "ledger.jsonl").read_text()
    aliased = lj.replace('"event": "preregistered", "sha256"', '"event": "prereg_frozen", "sha"')
    assert aliased != lj
    (new / "ledger.jsonl").write_text(aliased)
    assert errs(root, new) == [], errs(root, new)
    (new / "ledger.jsonl").write_text(aliased.replace('"sha": "', '"sha": "f'))  # alias with a wrong hash
    assert any("no preregistered event" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(lj)

    # a. tune/held id collision
    (new / "scenarios_held.json").write_text(json.dumps([{"id": "t1", "prompt": W(30, "d")}]))
    assert any("both tune and held" in e for e in errs(root, new))
    (new / "scenarios_held.json").write_text(json.dumps([{"id": "h1", "prompt": W(30, "d")}]))
    # a. byte-identical output reuse, and its allowlist
    (new / "outputs" / "t1.txt").write_text("x")
    assert any("byte-identical" in e for e in errs(root, new))
    (new / "reuse-allow.txt").write_text("outputs/t1\n")  # not a whole path or a directory: no match
    assert any("byte-identical" in e for e in errs(root, new))
    (new / "reuse-allow.txt").write_text("outputs/t1.txt\n")
    assert errs(root, new) == []
    (new / "reuse-allow.txt").write_text("outputs/sub/\n")
    (new / "outputs" / "sub").mkdir()
    (old / "outputs" / "sub").mkdir()
    for b_ in (new, old):
        (b_ / "outputs" / "sub" / "a.txt").write_text("z")
    assert any("t1.txt" in e for e in errs(root, new)) and not any("outputs/sub" in e for e in errs(root, new))
    (new / "reuse-allow.txt").write_text("outputs/t1.txt\noutputs/sub\n")
    assert errs(root, new) == []
    (new / "outputs" / "t1.txt").write_text("")  # 0-byte files are never reuse
    (old / "outputs" / "t1.txt").write_text("")
    (new / "reuse-allow.txt").unlink()
    (new / "outputs" / "sub" / "a.txt").write_text("q")
    assert errs(root, new) == []
    (old / "outputs" / "t1.txt").write_text("x")
    (new / "outputs" / "t1.txt").write_text("y")  # same name, new content is fine
    assert errs(root, new) == []

    # a. fail closed on tune/held files that yield no scenarios; {"scenarios": [...]} unwraps
    for bad in ("[]", "{}", '{"a": 1}', "not json", '[{"prompt": "no id"}]'):
        (new / "scenarios_held.json").write_text(bad)
        assert any("scenarios_held.json is not" in e for e in errs(root, new)), bad
    (new / "scenarios_held.json").write_text(json.dumps({"scenarios": [{"id": "h1", "prompt": W(30, "d")}]}))
    assert errs(root, new) == []
    (new / "scenarios_held.json").write_text(json.dumps({"scenarios": [{"id": "t1", "prompt": W(30, "d")}]}))
    assert any("both tune and held" in e for e in errs(root, new))
    (new / "scenarios_held.json").write_text(json.dumps([{"id": "h1", "prompt": W(30, "d")}]))

    # b. ledger: missing, hash rewritten after prereg, hash after generation, prefix too short
    led = (new / "ledger.jsonl").read_text()
    (new / "ledger.jsonl").unlink()
    assert any("both required" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(led)
    (new / "SHA256-frozen.txt").write_text("rewritten after the ledger hash\n")
    assert any("no preregistered event" in e for e in errs(root, new))
    (new / "SHA256-frozen.txt").write_text(f"{'0' * 64}  PREREGISTERED.md\n")
    lines = led.splitlines()
    (new / "ledger.jsonl").write_text("\n".join(lines[::-1]) + "\n")
    assert any("not earlier" in e for e in errs(root, new))
    h = json.loads(lines[0])["sha256"]
    (new / "ledger.jsonl").write_text(json.dumps({"event": "preregistered", "sha256": h[:6]}) + "\n" + lines[1] + "\n")
    assert any("no preregistered event" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(led)
    assert errs(root, new) == []
    # b. late append: lines added to SHA256-frozen.txt after the prereg hash was logged
    appended = f"{'0' * 64}  PREREGISTERED.md\n{'1' * 64}  amended.txt\n"
    (new / "SHA256-frozen.txt").write_text(appended)
    assert any("not in any later ledger event" in e for e in errs(root, new))  # appended line is uncovered
    cover = json.dumps({"event": "frozen", "files": {"amended.txt": "1" * 64}})
    (new / "ledger.jsonl").write_text(led + cover + "\n")  # later event carries the line's hash
    assert errs(root, new) == []
    (new / "ledger.jsonl").write_text(lines[0] + "\n" + cover + "\n" + lines[1] + "\n")
    assert errs(root, new) == []  # any event after the prereg counts, in or after generation
    (new / "ledger.jsonl").write_text(cover + "\n" + led)  # covering event before the prereg does not
    assert any("not in any later" in e or "not earlier" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(led)
    (new / "SHA256-frozen.txt").write_text(f"{'1' * 64}  amended.txt\n{'0' * 64}  PREREGISTERED.md\n")  # first line changed
    assert any("no preregistered event" in e for e in errs(root, new))
    (new / "SHA256-frozen.txt").write_text(f"{'0' * 64}  PREREGISTERED.md\n")
    # b. accepted hash keys
    for k in ("preregistered_sha256", "frozen_list_sha256", "sha256_of_SHA256-frozen.txt"):
        (new / "ledger.jsonl").write_text(led.replace('"sha256"', f'"{k}"'))
        assert errs(root, new) == [], k
    (new / "ledger.jsonl").write_text(led.replace('"sha256"', '"other_sha256"'))
    assert any("no preregistered event" in e for e in errs(root, new))
    # b. timestamps: ISO-8601 compares, unparseable fails, missing falls back to line order
    iso = lambda a, b: "\n".join([json.dumps({**json.loads(lines[0]), "ts": a}), json.dumps({"model": "m", "iso": b})]) + "\n"
    (new / "ledger.jsonl").write_text(iso("2026-10-17T10:00:00Z", "2026-10-17T10:00:01+00:00"))
    assert errs(root, new) == []
    (new / "ledger.jsonl").write_text(iso("2026-10-17T10:00:02Z", "2026-10-17T10:00:01Z"))
    assert any("not earlier" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(iso(1, "2026-10-17T10:00:01Z"))  # epoch vs ISO
    assert errs(root, new) == []
    (new / "ledger.jsonl").write_text(iso("yesterday", "2026-10-17T10:00:01Z"))
    assert any("comparable" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(led + "{broken\n")
    assert any("comparable" in e for e in errs(root, new))
    (new / "ledger.jsonl").write_text(led)
    assert errs(root, new) == []

    # a. scenario files: results files are not scenario files; a prereg-named file is
    (new / "per_scenario_results.json").write_text(json.dumps({"tune": 1}))
    (new / "scenarios_notes.json").write_text("[]")
    assert any("scenarios_notes.json is not" in e for e in errs(root, new))
    (new / "scenarios_notes.json").unlink()
    assert errs(root, new) == []
    (new / "PREREGISTERED.md").write_text("Scenarios file: cases.json\nSee SHA256-frozen.txt.\n")
    (new / "cases.json").write_text("{}")
    assert any("cases.json is not" in e for e in errs(root, new))
    (new / "cases.json").write_text(json.dumps([{"id": "tune-9", "prompt": W(30, "e")}, {"id": "held-9", "prompt": W(30, "f")}]))
    assert errs(root, new) == []  # one file, split by id
    (new / "cases.json").write_text(json.dumps([{"id": "x", "split": "tune", "prompt": W(30, "e")}, {"id": "x", "split": "held", "prompt": W(30, "f")}]))
    es = errs(root, new)
    assert any("both tune and held" in e for e in es) and any("cases.json repeats scenario id x" in e for e in es)
    (new / "cases.json").write_text(json.dumps([{"id": "d1", "prompt": W(30, "e")}, {"id": "d1", "prompt": W(30, "f")}]))
    assert any("repeats scenario id d1" in e for e in errs(root, new))
    (new / "cases.json").unlink()
    (new / "PREREGISTERED.md").write_text("See SHA256-frozen.txt.\n")
    # d. held scenario copied from the bench's own tune set
    (new / "scenarios_held.json").write_text(json.dumps([{"id": "h1", "prompt": W(30, "c")}]))
    assert any("its own tune set" in e for e in errs(root, new))
    (new / "overlap-allow.txt").write_text(W(30, "c") + "\n")
    assert errs(root, new) == []
    (new / "overlap-allow.txt").unlink()
    (new / "scenarios_held.json").write_text(json.dumps([{"id": "h1", "prompt": W(30, "d")}]))
    assert errs(root, new) == []

    # c. prereg doc naming a missing hash file
    (new / "PREREGISTERED.md").write_text("See SHA256-frozen.txt and SHA256-amend.txt.\n")
    assert any("SHA256-amend.txt" in e for e in errs(root, new))
    (new / "PREREGISTERED.md").write_text("See SHA256-frozen.txt.\n")

    # d. 10-word shingle overlap, and the template allowlist
    shared = W(12, "tpl")
    (new / "scenarios_tune.json").write_text(json.dumps([{"id": "t1", "prompt": shared + " " + W(8, "n")}]))
    (old / "scenarios_tune.json").write_text(json.dumps([{"id": "t1", "prompt": shared + " " + W(8, "o")}]))
    assert any("shingles" in e for e in errs(root, new))
    (new / "overlap-allow.txt").write_text(shared + "\n")
    assert errs(root, new) == [], errs(root, new)
    # 9 shared words never form a 10-word shingle, so a short template is not flagged
    (old / "scenarios_tune.json").write_text(json.dumps([{"id": "t1", "prompt": W(9, "tpl") + " " + W(20, "o")}]))
    (new / "overlap-allow.txt").unlink()
    (new / "scenarios_tune.json").write_text(json.dumps([{"id": "t1", "prompt": W(9, "tpl") + " " + W(20, "n")}]))
    assert errs(root, new) == []

    # --changed: only dirs absent from the base ref are checked; CLI exit codes
    r = Path(tempfile.mkdtemp())
    try:
        g = lambda *a: subprocess.run(["git", "-C", str(r), "-c", "user.name=t", "-c", "user.email=t@example.com", *a],
                                      check=True, capture_output=True)
        g("init", "-q", "-b", "main")
        (r / "scripts").mkdir()
        shutil.copy(bc.__file__, r / "scripts" / "bench_check.py")
        shutil.copytree(old, r / "docs/bench/old")
        (r / "docs/bench/old/ledger.jsonl").unlink()  # legacy bench: no ledger
        g("add", "-A"); g("commit", "-qm", "base")
        shutil.copytree(new, r / "docs/bench/new")
        g("add", "-A"); g("commit", "-qm", "pr")
        run = lambda *a, c=r: subprocess.run([sys.executable, str(r / "scripts" / "bench_check.py"), *a], cwd=c, capture_output=True, text=True)
        p = run("--changed", "HEAD~1")
        assert p.returncode == 0 and "1 dir(s) clean" in p.stdout, p.stdout
        assert run("docs/bench/old").returncode == 1  # explicit dir is checked even if legacy
        assert run("--changed", "HEAD~1", c=r / "docs").returncode == 0  # root comes from the script, not the cwd
        p = run("--changed", "no-such-ref")
        assert p.returncode != 0 and "not found" in (p.stdout + p.stderr)  # missing base is an error
        (r / "docs/bench/new/ledger.jsonl").unlink()
        assert run("--changed", "HEAD~1").returncode == 1
    finally:
        shutil.rmtree(r)
finally:
    shutil.rmtree(root)
print("test_bench_check: ok")
