#!/usr/bin/env python3
"""clock_lint.py [--base REF [--head REF]] [--root DIR] [--deadline SECS] [FILES...] | --selftest -- flag tests that read the real clock.

WHY: tests that read the real clock or timezone pass for weeks, then turn the development branch red at a
week, month or DST rollover. Flagged reads: py `datetime/dt/timezone/arrow/pendulum .now/.utcnow/.today`,
`date.today`, `time.time` (and `import ... as` aliases); js/ts `Date.now()`, `new Date()` with no args,
`moment()`/`dayjs()` with no args, `DateTime.now()`; go `time.Now()` (and an aliased time import); sh `date`
(any flags then a `-d`/`-r` date that is not relative to now is deterministic and allowed). Always flagged,
whatever surrounds the read (`datetime.now() - delta`, `deadline = Date.now()`). Not flagged: `perf_counter`/
`monotonic`/`process_time` (not wall clock), text in strings or comments.
A read is exempt only where a REAL fake clock is in scope: freezegun/freeze_time, time_machine, libfaketime/
faketime, jest/vi `useFakeTimers`/`setSystemTime`, MockDate, or a `now=`/`clock=` keyword argument that is not
itself a real read. Scope is the enclosing test function/block; a marker in the file preamble (not a bare
import), a fixture/setUp/beforeEach/describe block, or `TestMain` covers the whole file.
Files: explicit FILES (a non-test path prints `SKIP file: not a test file`), else changed vs `--base REF`
(git diff REF...HEAD or REF...--head, added/modified, paths resolved from the repo top), else every tracked
file. Test files: test_*.py, *_test.py, *.test.*/*.spec.* (js/ts/mjs/cjs), __tests__/, tests/, *_test.go,
test*.sh, *.bats.
Also (py/js, any file, test or not): `file:line: date literal compared with real clock; expires <date>` for a hard-coded
date (`SUNSET = date(2026, 10, 14)`, `"2026-10-14"`) compared with a real-clock read on its line or via the constant it is
assigned to; within 30 days of `--today` (default: real today) it is tagged `(URGENT: Nd)`, past it `(EXPIRED)`. These
count toward the exit code only with `--strict`; a pinned fake clock anywhere in the file or the allow escape exempts.
Output: `file:line: real clock in test; pin a fake clock or inject now`. Escape: `clock-lint: allow` in a comment
on the same line or on a comment-only line above. Exit 0 clean, 1 findings, 2 COULD_NOT_CHECK (unreadable file,
git failure or `--deadline` exceeded (checked per file; the pre-push hook passes 5); printed, never silent; 2 only when there are no findings).
Limits: line regexes and indentation/keyword block detection, not a parser; a clock read built by string
concatenation is not seen; a fake clock anywhere in a test block exempts that whole block. Read-only.
"""
import datetime
import os
import re
import subprocess
import sys
import time

TEST_RE = re.compile(r"(^|/)(test_[^/]*\.py|[^/]*_test\.(py|go)|[^/]*\.(test|spec)\.[cm]?[jt]sx?|test[^/]*\.sh|[^/]*\.bats"
                     r"|(__tests__|tests?)/[^/]*\.(py|[cm]?[jt]sx?|go|sh))$")
EXT = {"py": "py", "js": "js", "jsx": "js", "ts": "js", "tsx": "js", "mjs": "js", "cjs": "js", "mts": "js",
       "cts": "js", "go": "go", "sh": "sh", "bats": "sh"}
READS = {
    "py": r"\b(datetime|dt|timezone|arrow|pendulum)\.(now|utcnow|today)\s*\(|\bdate\.today\s*\(|\btime\.time(_ns)?\s*\(",
    "js": r"\bDate\.now\s*\(\s*\)|\bnew\s+Date\s*\(\s*\)|\b(moment|dayjs)\s*\(\s*\)|\bDateTime\.(now|local)\s*\(",
    "go": r"\btime\.Now\s*\(\s*\)",
    "sh": r"(^|[\s$(`;|&])date(?![\w-])(?!(?:\s+-[a-zA-Z]+|\s+--utc)*\s+(-d|--date=?|-r|--reference=?)\s*(?!now|yesterday|tomorrow|next|last|[+-]\d|\S*ago\b)\S)",
}
FAKE = re.compile(r"freezegun|freeze_time|time_machine|time-machine|libfaketime|faketime|useFakeTimers|setSystemTime|"
                  r"[Mm]ock[Dd]ate|[(,]\s*(now|clock|now_fn|nowFn)\s*=(?!=)(?!\s*\w*\.?(datetime\.|dt\.)?(now|utcnow|today)\b)"
                  r"(?!\s*(time\.|Date\.now|new Date\(\s*\)))")
BLOCK = {  # block start (a decorator line also starts one for py)
    "py": r"^\s*(@|(async\s+)?def\s|class\s)", "js": r"^\s*(it|test|describe|beforeEach|beforeAll|afterEach|afterAll)\b",
    "go": r"^func\s", "sh": r"^\s*(function\s+\w+|\w+\s*\(\)\s*\{|@test\b)"}
GLOBAL = {  # block headers whose fake clock covers the file (matched per line, never a test's own name)
    "py": r"^\s*(@(pytest\.)?fixture\b|(async\s+)?def\s+(setUp\w*|setup_(module|class|method|function)|teardown_\w+)\b)",
    "js": r"^\s*(describe|beforeEach|beforeAll)\b", "go": r"^func\s+TestMain\b", "sh": r"^\s*setup\s*\(\)"}
IMPORT = re.compile(r"^\s*(import\b|from\s+\S+\s+import\b|.*\brequire\()")
ALLOW = "clock-lint: allow"
COMMENT = re.compile(r"^\s*(#|//|\*|/\*)")
MSG = "real clock in test; pin a fake clock or inject now"
ISO = re.compile(r"(?<![\d-])(20\d\d)-(\d\d)-(\d\d)(?!\d)|\b(?:datetime|date)\(\s*(20\d\d)\s*,\s*(\d\d?)\s*,\s*(\d\d?)\b")
NAME = re.compile(r"^\s*(?:export\s+)?(?:const\s+|let\s+|var\s+)?([A-Za-z_]\w*)\s*(?::[^=]+)?=(?!=)")
URGENT_DAYS = 30


def code(lang, line, st):
    """`line` without string literals and trailing comments; st = [in_triple_quote] for py docstrings."""
    if lang == "py":
        if line.count('"""') % 2 or line.count("'''") % 2:
            st[0] = not st[0]
            return ""
        if st[0]:
            return ""
    if lang == "sh":
        line = re.sub(r"(-d|--date=?|-r)\s*(['\"])([^'\"]*)\2", lambda m: m.group(1) + " " + m.group(3).replace(" ", "~"), line)
        line = re.sub(r"'[^']*'|\"(?![^\"]*(\$\(|`))[^\"]*\"", "''", line)
    else:
        line = re.sub(r"'(\\.|[^'\\])*'|\"(\\.|[^\"\\])*\"", "''", line)
    return re.split(r"\s#.*|^#.*" if lang in ("py", "sh") else r"\s//.*|^//.*", line)[0]


def aliases(lang, text):
    """Extra read regex for `import time as t` / `from datetime import datetime as d` (py) and `import t "time"` (go)."""
    if lang == "py":
        a = re.findall(r"import\s+time\s+as\s+(\w+)", text)
        b = re.findall(r"import\s+(?:datetime|date)\s+as\s+(\w+)", text)
        return [r"\b%s\.time(_ns)?\s*\(" % x for x in a] + [r"\b%s\.(now|utcnow|today)\s*\(" % x for x in b]
    if lang == "go":
        return [r"\b%s\.Now\s*\(\s*\)" % x for x in re.findall(r"^\s*import\s+(\w+)\s+\"time\"|^\s*(\w+)\s+\"time\"", text, re.M)
                for x in x if x]
    return []


def scan(path, text):
    """Return [(line_no, line)] of unpinned real-clock reads in `text`."""
    lang = EXT[path.rsplit(".", 1)[-1]]
    rx = re.compile("|".join([READS[lang]] + aliases(lang, text)))
    lines, st = text.split("\n"), [False]
    cl = [code(lang, l, st) for l in lines]
    starts = [i for i, l in enumerate(lines) if re.search(BLOCK[lang], l)]
    if lang == "py":  # a decorator run belongs to the def below it: drop starts that continue a decorator run
        starts = [i for i in starts if not (i and re.match(r"^\s*@", lines[i - 1]))]
    bounds = sorted(set([0] + starts + [len(lines)]))
    spans = list(zip(bounds, bounds[1:]))
    first = starts[0] if starts else len(lines)
    glob, ok = False, set()
    for k, (a, b) in enumerate(spans):
        if any(FAKE.search(cl[i]) and not IMPORT.match(lines[i]) for i in range(a, b)):
            ok.add(k)
            glob = glob or b <= first or bool(re.search(GLOBAL[lang], "\n".join(lines[a:min(b, a + 4)]), re.M))
    if glob:
        return []
    out = []
    for k, (a, b) in enumerate(spans):
        if k in ok:
            continue
        for i in range(a, b):
            if not rx.search(cl[i]) or COMMENT.match(lines[i]) or ALLOW in lines[i] \
                    or (i and ALLOW in lines[i - 1] and COMMENT.match(lines[i - 1])):
                continue
            out.append((i + 1, lines[i]))
    return out


def bombs(path, text, today):
    """[(line_no, date, days_left)] of date literals (SUNSET = date(2026,10,14), "2026-10-14") compared with a real-clock
    read, on the literal's own line or on another line using the constant it is assigned to. py/js only; any file
    (test or not); a pinned fake clock anywhere in the file, comment-only lines and `clock-lint: allow` exempt.
    Sorted soonest first; days_left <= URGENT_DAYS is urgent. `today` is injected."""
    lang = EXT.get(path.rsplit(".", 1)[-1])
    if lang not in ("py", "js"):
        return []
    rx = re.compile("|".join([READS[lang]] + aliases(lang, text)))
    lines, st = text.split("\n"), [False]
    cl = [code(lang, l, st) for l in lines]
    if any(FAKE.search(c) and not IMPORT.match(l) for c, l in zip(cl, lines)):
        return []
    out = []
    for i, l in enumerate(lines):
        if COMMENT.match(l) or ALLOW in l or (i and ALLOW in lines[i - 1] and COMMENT.match(lines[i - 1])):
            continue
        for m in ISO.finditer(l):
            try:
                d = datetime.date(*map(int, [g for g in m.groups() if g]))
            except ValueError:
                continue
            nm = NAME.match(l)
            if rx.search(cl[i]) or (nm and any(j != i and re.search(r"\b%s\b" % nm.group(1), cl[j]) and rx.search(cl[j])
                                               for j in range(len(lines)))):
                out.append((i + 1, d, (d - today).days))
                break
    return sorted(out, key=lambda t: t[2])


def files(root, base, head, args):
    if args:
        return args
    top = root
    if base:
        p = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        top = p.stdout.strip() if not p.returncode else root
    cmd = ["diff", "--name-only", "--diff-filter=AM", "%s...%s" % (base, head)] if base else ["ls-files"]
    p = subprocess.run(["git", "-C", root, *cmd], capture_output=True, text=True)
    if p.returncode:
        raise OSError("git %s failed: %s" % (cmd[0], p.stderr.strip()))
    return [os.path.join(top, f) for f in p.stdout.split("\n") if f]


def run(root, base, args, head="HEAD", deadline=None, today=None, strict=False):
    bad = cant = 0
    today = today or datetime.date.today()
    end = time.monotonic() + deadline if deadline is not None else None
    try:
        paths = files(root, base, head, args)
    except OSError as e:
        print("COULD_NOT_CHECK %s" % e)
        return 2
    for f in paths:
        if end is not None and time.monotonic() > end:
            print("COULD_NOT_CHECK deadline exceeded before %s" % f)
            return 1 if bad else 2
        rel = f if args else os.path.relpath(os.path.realpath(f), os.path.realpath(root))
        is_test = TEST_RE.search(f.replace(os.sep, "/")) and f.rsplit(".", 1)[-1] in EXT
        if not is_test and args:
            print("SKIP %s: not a test file" % f)
        if not is_test and EXT.get(f.rsplit(".", 1)[-1]) not in ("py", "js"):
            continue
        try:
            with open(f, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError as e:
            print("COULD_NOT_CHECK %s: %s" % (rel, e.strerror or e))
            cant += 1
            continue
        for n, d, left in bombs(f, text, today):
            print("%s:%d: date literal compared with real clock; expires %s%s" % (
                rel, n, d, " (URGENT: %dd)" % left if 0 <= left <= URGENT_DAYS else " (EXPIRED)" if left < 0 else ""))
            bad += strict
        if not is_test:
            continue
        for n, _ in scan(f, text):
            print("%s:%d: %s" % (rel, n, MSG))
            bad += 1
    return 1 if bad else 2 if cant else 0


def selftest():
    cases = [
        ("test_a.py", "import datetime\nx = datetime.datetime.now()\n", 1),
        ("test_a.py", "now = datetime.now()\n", 1),
        ("test_a.py", "def test_x():\n    t = dt.now()\n", 1),
        ("test_a.py", "def test_x():\n    t = timezone.now()\n", 1),
        ("test_a.py", "import time as tm\ndef test_x():\n    a = tm.time()\n", 1),
        ("test_a.py", "from freezegun import freeze_time\nx = datetime.now()\n", 1),  # bare import is no marker
        ("test_a.py", "@freeze_time('2020-01-01')\ndef test_x():\n    datetime.now()\n", 0),
        ("test_a.py", "@freeze_time('2020-01-01')\ndef test_x():\n    datetime.now()\ndef test_y():\n    datetime.now()\n", 1),
        ("test_a.py", "pytestmark = freeze_time('2020-01-01')\ndef test_x():\n    datetime.now()\n", 0),
        ("test_a.py", "@pytest.fixture(autouse=True)\ndef clock():\n    with freeze_time('2020-01-01'):\n        yield\ndef test_x():\n    datetime.now()\n", 0),
        ("test_a.py", "@mock.patch('time.sleep')\ndef test_x(s):\n    datetime.now()\n", 1),
        ("test_a.py", "def test_x():\n    f(now=datetime.now())\n", 1),
        ("test_a.py", "def test_x():\n    f(now=FIXED)\n    datetime.now()\n", 0),
        ("test_a.py", "def test_x():\n    start = time.time()\n    e = time.time() - start\n", 2),
        ("test_a.py", "def test_x():\n    p = time.perf_counter() + time.monotonic() + time.process_time()\n", 0),
        ("test_a.py", "def test_x():\n    d = datetime.now() - timedelta(days=1)\n    deadline = datetime.now()\n", 2),
        ("test_a.py", "@freeze_time('2020-01-01')\ndef test_fixture_x():\n    datetime.now()\ndef test_y():\n    datetime.now()\n", 1),
        ("test_a.py", "@pytest.fixture\ndef c():\n    with freeze_time('2020-01-01'):\n        yield\ndef test_y():\n    datetime.now()\n", 0),
        ("test_a.py", "def test_x():\n    s = 'datetime.now()'  # datetime.now()\n    \"\"\"\n    time.time()\n    \"\"\"\n", 0),
        ("test_c.py", "x = time.time()  # clock-lint: allow\ny = time.time()\n", 1),
        ("test_c.py", "# clock-lint: allow\ny = time.time()\n", 0),
        ("a.test.ts", "const t = Date.now();\nconst u = new Date('2020-01-01');\nconst v = new Date();\n", 2),
        ("a.test.mjs", "it('a', () => { moment(); });\n", 1),
        ("a.test.ts", "it('a', () => {\n  const start = Date.now();\n  const d = Date.now() - start;\n});\n", 2),
        ("b.spec.js", "beforeEach(() => { jest.useFakeTimers(); });\nit('a', () => { Date.now(); });\n", 0),
        ("b.spec.js", "it('a', () => { vi.setSystemTime(1); Date.now(); });\nit('b', () => { Date.now(); });\n", 1),
        ("b.spec.js", "it('a', () => { jest.advanceTimersByTime(1); Date.now(); });\n", 1),
        ("x_test.go", "func TestA(t *testing.T) {\n\tn := time.Now()\n\t// time.Now()\n}\n", 1),
        ("x_test.go", "import t \"time\"\nfunc TestA() {\n\tn := t.Now()\n}\n", 1),
        ("x_test.go", "func TestA() {\n\tstart := time.Now()\n\td := time.Since(start)\n}\n", 1),
        ("test-r.sh", "d=$(date +%F)\ne=$(date -d @0 +%F)\nf=$(date)\n", 2),
        ("test-r.sh", "e=$(date -d '2020-01-01' +%F)\ng=$(date -d 'yesterday' +%F)\necho \"date is fixed\"\n", 1),
        ("test-r.sh", "a=$(date -u -d '2020-01-01' +%F)\nb=$(date -u -r 5 +%F)\nc=$(date --utc --date='2020-01-01')\n", 0),
        ("test-r.sh", "a=$(date -u +%F)\nb=$(date -u -d 'yesterday' +%F)\n", 2),
        ("test-r.sh", "g=$(date -d '3 days ago' +%F)\nh=$(date -r 5 +%F)\n", 1),
        ("app.py", "datetime.now()\n", 0),
    ]
    for name, src, want in cases:
        got = len(scan(name, src)) if TEST_RE.search(name) else 0
        assert got == want, (name, src, got, want)
    t = datetime.date(2026, 10, 14)  # injected "today": the self-check never reads the real clock
    bomb = [
        ("g.py", "SUNSET = date(2026, 10, 20)\ndef ok():\n    return date.today() < SUNSET\n", [(1, 6)]),
        ("g.py", 'if datetime.now() > datetime(2027, 3, 1):\n    pass\n', [(1, 138)]),
        ("g.ts", 'const SUNSET = "2026-09-01";\nexport const live = () => Date.now() < Date.parse(SUNSET);\n', [(1, -43)]),
        ("g.py", 'x = "2026-10-20"\n', []),  # literal never compared with a clock
        ("g.py", "SUNSET = date(2026, 10, 20)\nOTHER = date.today()\n", []),
        ("g.py", "SUNSET = date(2026, 10, 20)  # clock-lint: allow\nok = date.today() < SUNSET\n", []),
        ("g.py", "# SUNSET = date(2026, 10, 20) date.today()\n", []),
        ("test_g.py", "@freeze_time('2026-10-14')\ndef test_x():\n    assert date.today() < date(2026, 10, 20)\n", []),
        ("g.py", "SUNSET = date(2026, 13, 45)\nok = date.today() < SUNSET\n", []),
        ("g.go", 'S = "2026-10-20"\nt := time.Now()\n', []),
    ]
    for name, src, want in bomb:
        got = [(n, left) for n, _, left in bombs(name, src, t)]
        assert got == want, (name, src, got, want)
    print("clock_lint selftest ok")


def main(argv):
    if argv == ["--selftest"]:
        return selftest()
    root, base, head, deadline, today = ".", None, "HEAD", None, None
    strict = "--strict" in argv
    if strict:
        argv.remove("--strict")
    for opt in ("--root", "--base", "--head", "--deadline", "--today"):
        if opt in argv:
            i = argv.index(opt)
            if i + 1 >= len(argv):
                sys.exit("usage: clock_lint.py [--base REF [--head REF]] [--root DIR] [FILES...] | --selftest")
            v = argv[i + 1]
            del argv[i:i + 2]
            if opt == "--root": root = v
            elif opt == "--base": base = v
            elif opt == "--deadline": deadline = float(v)
            elif opt == "--today": today = datetime.date.fromisoformat(v)
            else: head = v
    return run(root, base, argv, head, deadline, today, strict)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
