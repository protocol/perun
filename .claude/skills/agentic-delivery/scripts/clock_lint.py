#!/usr/bin/env python3
"""clock_lint.py [--base REF] [--root DIR] [FILES...] | --selftest -- flag tests that read the real clock.

WHY: tests that read the real clock or timezone pass for weeks, then turn the development branch red at a
week, month or DST rollover. A test is flagged when it reads the real clock (py `datetime.now/today/utcnow`,
`date.today`, `time.time`; js/ts `Date.now()`, `new Date()` with no args; go `time.Now()`; sh `date` with no
-d/-r/--date input) AND the file has no fake-clock marker (freezegun, time_machine, libfaketime, jest/vi
`useFakeTimers`/`setSystemTime`, sinon, MockDate, a `clock=`/`now=`/`now_fn` injection, a patched
time/datetime/Date, a Clock type). Marker detection is per file, not per call.
Files: explicit FILES, else those changed vs `--base REF` (git diff REF...HEAD, added/modified), else every
tracked file. Test files only: test_*.py, *_test.py, *.test.*, *.spec.*, __tests__/, tests/, *_test.go,
test*.sh, *.bats.
Output: `file:line: real clock in test; pin a fake clock or inject now`. Escape: put `clock-lint: allow` in a
comment on the same line or on a comment-only line above. Exit 0 clean, 1 findings, 2 COULD_NOT_CHECK (unreadable file or git
failure; printed, never silent; 2 only when there are no findings).
Limits: line regexes, a marker anywhere in a file exempts it (a half-pinned file is missed); a clock read
built by string concatenation is not seen. Side effects: none (read-only).
"""
import os
import re
import subprocess
import sys

TEST_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.(py|go)|[^/]*\.(test|spec)\.[jt]sx?|test[^/]*\.sh|[^/]*\.bats"
                     r"|(__tests__|tests?)/[^/]*\.(py|[jt]sx?|go|sh))$")
READS = {  # extension -> real-clock reads
    "py": r"\bdatetime\.(now|today|utcnow)\s*\(|\bdate\.today\s*\(|\btime\.time(_ns)?\s*\(",
    "js": r"\bDate\.now\s*\(\s*\)|\bnew\s+Date\s*\(\s*\)",
    "go": r"\btime\.Now\s*\(\s*\)",
    "sh": r"(^|[\s$(`;|&])date(\s*$|\s+(?!-[dr]\b|--date|--reference)[^@]*$|\s*[)`;|&])",
}
EXT = {"py": "py", "js": "js", "jsx": "js", "ts": "js", "tsx": "js", "go": "go", "sh": "sh", "bats": "sh"}
MARK = re.compile(
    r"freezegun|freeze_time|time_machine|time-machine|libfaketime|faketime|useFakeTimers|setSystemTime|sinon|"
    r"[Mm]ock[Dd]ate|FakeClock|fake_clock|clockwork|\bclock\s*[=:]|\bnow_fn\b|\bnowFn\b|\bnow\s*=|\bnow\s*:|"
    r"\b(patch|monkeypatch\.setattr|mock\.patch)\w*\(.*(datetime|time\b|Date)|\bClock\b")
ALLOW = "clock-lint: allow"
COMMENT = re.compile(r"^\s*(#|//|\*|/\*)")
MSG = "real clock in test; pin a fake clock or inject now"


def scan(path, text):
    """Return [(line_no, line)] of real-clock reads in `text`, [] when a fake-clock marker is present."""
    rx = re.compile(READS[EXT[path.rsplit(".", 1)[-1]]])
    if MARK.search(text):
        return []
    lines = text.split("\n")
    return [(i + 1, l) for i, l in enumerate(lines)
            if not COMMENT.match(l) and rx.search(l) and ALLOW not in l and not (i and ALLOW in lines[i - 1] and COMMENT.match(lines[i - 1]))]


def files(root, base, args):
    if args:
        return args
    cmd = ["diff", "--name-only", "--diff-filter=AM", base + "...HEAD"] if base else ["ls-files"]
    p = subprocess.run(["git", "-C", root, *cmd], capture_output=True, text=True)
    if p.returncode:
        raise OSError("git %s failed: %s" % (cmd[0], p.stderr.strip()))
    return [os.path.join(root, f) for f in p.stdout.split("\n") if f]


def run(root, base, args):
    bad = cant = 0
    try:
        paths = files(root, base, args)
    except OSError as e:
        print("COULD_NOT_CHECK %s" % e)
        return 2
    for f in paths:
        rel = os.path.relpath(f, root) if not args else f
        if not TEST_RE.search(f.replace(os.sep, "/")) or f.rsplit(".", 1)[-1] not in EXT:
            continue
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            print("COULD_NOT_CHECK %s: %s" % (rel, e.strerror or e))
            cant += 1
            continue
        for n, _ in scan(f, text):
            print("%s:%d: %s" % (rel, n, MSG))
            bad += 1
    return 1 if bad else 2 if cant else 0


def selftest():
    import tempfile
    d = tempfile.mkdtemp(dir=os.environ.get("TMPDIR"))
    case = {
        "test_a.py": ("import datetime\nx = datetime.datetime.now()\n", 1),
        "test_b.py": ("from freezegun import freeze_time\nx = datetime.now()\n", 0),
        "test_c.py": ("x = time.time()  # clock-lint: allow\ny = time.time()\n", 1),
        "a.test.ts": ("const t = Date.now();\nconst u = new Date('2020-01-01');\nconst v = new Date();\n", 2),
        "b.spec.js": ("jest.useFakeTimers();\nDate.now();\n", 0),
        "x_test.go": ("n := time.Now()\n// time.Now()\n", 1),
        "test-r.sh": ("d=$(date +%F)\ne=$(date -d @0 +%F)\nf=$(date)\n", 2),
        "app.py": ("datetime.now()\n", 0),  # not a test file
    }
    for name, (src, _) in case.items():
        with open(os.path.join(d, name), "w", encoding="utf-8") as fh:
            fh.write(src)
    for name, (_, want) in case.items():
        got = len(scan(name, case[name][0])) if TEST_RE.search(name) else 0
        assert got == want, (name, got, want)
    open(os.path.join(d, "test_bad.py"), "w").close()
    os.chmod(os.path.join(d, "test_bad.py"), 0)
    assert run(d, None, [os.path.join(d, "test_a.py")]) == 1
    assert run(d, None, [os.path.join(d, "test_b.py")]) == 0
    if os.getuid():  # root reads mode-0 files
        assert run(d, None, [os.path.join(d, "test_bad.py")]) == 2
    assert run(d, None, [os.path.join(d, "test_missing.py")]) == 2
    print("clock_lint selftest ok")


def main(argv):
    if argv == ["--selftest"]:
        return selftest()
    root, base = ".", None
    for opt in ("--root", "--base"):
        if opt in argv:
            i = argv.index(opt)
            if i + 1 >= len(argv):
                sys.exit("usage: clock_lint.py [--base REF] [--root DIR] [FILES...] | --selftest")
            v = argv[i + 1]
            del argv[i:i + 2]
            root, base = (v, base) if opt == "--root" else (root, v)
    return run(root, base, argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
