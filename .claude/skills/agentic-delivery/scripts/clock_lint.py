#!/usr/bin/env python3
"""clock_lint.py [--base REF [--head REF] [--block-added]] [--root DIR] [--deadline SECS] [FILES...] | --selftest -- flag tests that read the real clock.

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
Also (py test files only, AST): `file:line: timing bet under load; ...` inside a `test_*` function (any function in a file
under `tests/` of the repo-relative path) for `time.sleep(<number > 0>)` (also `from time import sleep`) followed later by an
assert that is not in a sibling if/else branch, a run/call/check_call/check_output/communicate/wait/get call with
`timeout=<number <= 5>`, or `assert <X> < (or <=) <number>` where X is a name/attribute/call matching
elapsed|duration|latency|took|runtime|wall or an arithmetic expression using time/monotonic/perf_counter: wall-clock
bets that flake on a busy runner. Same `clock-lint: allow` escape (on any line of a multi-line call). `--block-added`
(needs `--base`) makes ONLY a timing bet in a file ADDED in base...head count toward exit 1; every other finding still
prints but is a warning (exit 0), so one hook call blocks new files and only warns for old ones. A crash in this rule
is COULD_NOT_CHECK (exit 2), never a finding.
Also advisory (py/js tests, prints only, exit unchanged): `file:line: advisory: day/week-relative text asserted ...` for an
line starting with expect(/assert naming "this week", "today", "3 days ago" etc. when the file has no fake clock. Playwright
`setFixedTime`/`clock.install`/`clock.pauseAt` silence only this advisory: they fix the browser clock, not the runner's, so
real-clock reads stay findings.
Output: `file:line: real clock in test; pin a fake clock or inject now`. Escape: `clock-lint: allow` in a comment
on the same line or on a comment-only line above. Exit 0 clean, 1 findings, 2 COULD_NOT_CHECK (unreadable file,
git failure or `--deadline` exceeded (checked per file; the pre-push hook passes 5); printed, never silent; 2 only when there are no findings).
Limits: line regexes and indentation/keyword block detection, not a parser; a clock read built by string
concatenation is not seen; a fake clock anywhere in a test block exempts that whole block. Read-only.
"""
import ast
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
CMP = re.compile(r"<=|>=|==|!=|(?<![-=])>|<|\b(?:isBefore|isAfter|isSameOrBefore|isSameOrAfter)\b")
URGENT_DAYS = 30
TMSG = "timing bet under load; wait on an event or inject the clock (or add `clock-lint: allow`)"
PWCLOCK = re.compile(r"\bsetFixedTime\b|\bclock\.(install|pauseAt)\b")
RELTEXT = re.compile(r"^\s*(await\s+)?(expect\s*\(|(self\.)?assert\w*[\s(])"
                     r".*?(\b(this|last|next)\s+(week|month|year)\b|\b(today|yesterday|tomorrow)\b|\b\d+\s+(minute|hour|day|week)s?\s+ago\b)", re.I)
RMSG = "advisory: day/week-relative text asserted with no fixed clock; pin it (page.clock.setFixedTime, useFakeTimers+setSystemTime, freeze_time)"
ELAPSED = re.compile(r"elapsed|duration|latency|took|runtime|wall", re.I)
WAITS = {"run", "call", "check_call", "check_output", "communicate", "wait", "get"}
CLOCKS = {"time", "time_ns", "monotonic", "monotonic_ns", "perf_counter", "perf_counter_ns"}


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


def scan(path, text, hit=None, fake=FAKE, allow=ALLOW):
    """Return [(line_no, line)] of unpinned real-clock reads in `text`. env_lint.py reuses this with its own
    `hit(lang, code_line)` read test, `fake` marker regex and `allow` escape."""
    lang = EXT[path.rsplit(".", 1)[-1]]
    rx = re.compile("|".join([READS[lang]] + aliases(lang, text)))
    hit = hit or (lambda _l, c: rx.search(c))
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
        if any(fake.search(cl[i]) and not IMPORT.match(lines[i]) for i in range(a, b)):
            ok.add(k)
            glob = glob or b <= first or bool(re.search(GLOBAL[lang], "\n".join(lines[a:min(b, a + 4)]), re.M))
    if glob:
        return []
    out = []
    for k, (a, b) in enumerate(spans):
        if k in ok:
            continue
        for i in range(a, b):
            if not hit(lang, cl[i]) or COMMENT.match(lines[i]) or allow in lines[i] \
                    or (i and allow in lines[i - 1] and COMMENT.match(lines[i - 1])):
                continue
            out.append((i + 1, lines[i]))
    return out


def reltext(path, text):
    """Line numbers asserting day/week-relative text ("No demos yet this week") in a py/js test file with no fake clock."""
    lines = text.split("\n")
    if any((FAKE.search(l) or PWCLOCK.search(l)) and not IMPORT.match(l) for l in lines):
        return []
    raw = lines
    lines = [re.sub(r"\s(//|#).*$", "", l) for l in raw]  # trailing comments never count
    return [i + 1 for i, l in enumerate(lines) if RELTEXT.search(l) and not COMMENT.match(l) and ALLOW not in raw[i]
            and not (i and ALLOW in raw[i - 1] and COMMENT.match(raw[i - 1]))]


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

    def cmp_read(c):  # a real-clock read and a comparison in the same expression (line)
        return bool(rx.search(c) and CMP.search(c))

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
            nm = nm.group(1) if nm and len(nm.group(1)) >= 3 else None
            if cmp_read(cl[i]) or (nm and any(j != i and re.search(r"\b%s\b" % nm, cl[j]) and cmp_read(cl[j])
                                              for j in range(len(lines)))):
                out.append((i + 1, d, (d - today).days))
                break
    return sorted(out, key=lambda t: t[2])


def _num(n):
    return isinstance(n, ast.Constant) and isinstance(n.value, (int, float)) and not isinstance(n.value, bool)


def _excl(fn, a, b):
    """True when a and b sit in opposite branches of one `if`, so a is never followed by b."""
    for i in ast.walk(fn):
        if isinstance(i, ast.If):
            x, y = ({id(m) for s in br for m in ast.walk(s)} for br in (i.body, i.orelse))
            if id(a) in x and id(b) in y or id(a) in y and id(b) in x:
                return True
    return False


def timing(path, text):
    """[line_no] of timing bets in py test functions (see the module docstring); `path` is repo-relative.
    Raises SyntaxError on unparseable text."""
    lines, tree = text.split("\n"), ast.parse(text)
    mods, sleeps = {"time"}, set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            mods |= {a.asname for a in n.names if a.name == "time" and a.asname}
        elif isinstance(n, ast.ImportFrom) and n.module == "time":
            sleeps |= {a.asname or a.name for a in n.names if a.name == "sleep"}
    is_sleep = lambda c: isinstance(c.func, ast.Attribute) and c.func.attr == "sleep" \
        and isinstance(c.func.value, ast.Name) and c.func.value.id in mods or isinstance(c.func, ast.Name) and c.func.id in sleeps
    is_clock = lambda c: isinstance(c, ast.Call) and getattr(c.func, "attr", getattr(c.func, "id", "")) in CLOCKS

    def elapsed(e):
        if isinstance(e, ast.BinOp):
            return any(is_clock(c) for c in ast.walk(e))
        e = e.func if isinstance(e, ast.Call) else e
        return isinstance(e, (ast.Name, ast.Attribute)) and bool(ELAPSED.search(ast.unparse(e)))

    in_tests = "tests" in path.replace(os.sep, "/").split("/")[:-1]
    hits = {}
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) or not (in_tests or fn.name.startswith("test_")):
            continue
        nodes = list(ast.walk(fn))
        asserts = [n for n in nodes if isinstance(n, ast.Assert)
                   or isinstance(n, ast.Call) and getattr(n.func, "attr", "").startswith("assert")]
        for n in nodes:
            if isinstance(n, ast.Call):
                name = getattr(n.func, "attr", getattr(n.func, "id", ""))
                if is_sleep(n) and n.args and _num(n.args[0]) and n.args[0].value > 0 and \
                        any(a.lineno > n.lineno and not _excl(fn, n, a) for a in asserts) or \
                        name in WAITS and any(k.arg == "timeout" and _num(k.value) and k.value.value <= 5 for k in n.keywords):
                    hits[n.lineno] = n.end_lineno
            elif isinstance(n, ast.Assert) and isinstance(n.test, ast.Compare) and len(n.test.ops) == 1 \
                    and isinstance(n.test.ops[0], (ast.Lt, ast.LtE)) and _num(n.test.comparators[0]) and elapsed(n.test.left):
                hits[n.lineno] = n.end_lineno
    return sorted(a for a, b in hits.items() if not any(ALLOW in lines[j - 1] for j in range(a, b + 1))
                  and not (a > 1 and ALLOW in lines[a - 2] and COMMENT.match(lines[a - 2])))


def files(root, base, head, args, filt="AM"):
    if args:
        return args
    top = root
    if base:
        p = subprocess.run(["git", "-C", root, "rev-parse", "--show-toplevel"], capture_output=True, text=True)
        top = p.stdout.strip() if not p.returncode else root
    cmd = ["diff", "--name-only", "--diff-filter=" + filt, "%s...%s" % (base, head)] if base else ["ls-files"]
    p = subprocess.run(["git", "-C", root, *cmd], capture_output=True, text=True)
    if p.returncode:
        raise OSError("git %s failed: %s" % (cmd[0], p.stderr.strip()))
    return [os.path.join(top, f) for f in p.stdout.split("\n") if f]


def run(root, base, args, head="HEAD", deadline=None, today=None, strict=False, added=False):  # added = --block-added
    bad = cant = 0
    today = today or datetime.date.today()
    end = time.monotonic() + deadline if deadline is not None else None
    try:
        paths = files(root, base, head, args)
        new = set(files(root, base, head, args, "A")) if added else ()
    except OSError as e:
        print("COULD_NOT_CHECK %s" % e)
        return 2
    for f in paths:
        if end is not None and time.monotonic() > end:
            print("COULD_NOT_CHECK deadline exceeded before %s" % f)
            return 1 if bad else 2
        rel = f if args else os.path.relpath(os.path.realpath(f), os.path.realpath(root))
        is_test = TEST_RE.search(f.replace(os.sep, "/")) and f.rsplit(".", 1)[-1] in EXT
        if not is_test and EXT.get(f.rsplit(".", 1)[-1]) not in ("py", "js"):
            if args:
                print("SKIP %s: not a test file" % f)
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
            bad += strict and not added
        if not is_test:
            continue
        for n, _ in scan(f, text):
            print("%s:%d: %s" % (rel, n, MSG))
            bad += not added
        if EXT[f.rsplit(".", 1)[-1]] in ("py", "js"):
            try:  # advisory: printed, never changes the exit code; a crash is COULD_NOT_CHECK
                for n in reltext(f, text):
                    print("%s:%d: %s" % (rel, n, RMSG))
            except Exception as e:
                print("COULD_NOT_CHECK %s: %s" % (rel, e))
                cant += 1
        if f.endswith(".py"):
            try:  # fail open: a crash here is COULD_NOT_CHECK, never a finding that blocks a push
                tb = timing(os.path.relpath(os.path.realpath(f), os.path.realpath(root)), text)
            except Exception as e:
                print("COULD_NOT_CHECK %s: %s" % (rel, e))
                cant += 1
                continue
            for n in tb:
                print("%s:%d: %s" % (rel, n, TMSG))
            bad += len(tb) if f in new or not added else 0
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
        ("g.py", 'created = "2020-01-01"\nprint(datetime.now())\n', []),  # past fixture near a read, no comparison
        ("g.py", 'row = {"created": "2020-01-01", "at": datetime.now()}\n', []),
        ("g.py", 'SUNSET = date(2026, 10, 20)\nlog(SUNSET, date.today())\n', []),  # same line, but no comparison
        ("g.py", 'DAY = date(2026, 10, 20)\nok = date.today() < DAYS\n', []),  # bare-word prefix is not the constant
        ("g.py", 'D = date(2026, 10, 20)\nok = date.today() < D\n', []),  # name shorter than 3 chars
        ("g.py", 'created = "2020-01-01"\nstale = created < datetime.now()\n', [(1, -2478)]),  # actually compared
    ]
    for name, src, want in bomb:
        got = [(n, left) for n, _, left in bombs(name, src, t)]
        assert got == want, (name, src, got, want)
    tm = [
        ("test_t.py", "def test_x():\n    time.sleep(1)\n    assert ok()\n", [2]),
        ("test_t.py", "def test_x():\n    time.sleep(1)\n    self.assertTrue(ok())\n", [2]),
        ("test_t.py", "def test_x():\n    assert ok()\n    time.sleep(1)\n", []),  # sleep with no assert after it
        ("test_t.py", "def test_x():\n    time.sleep(n)\n    assert ok()\n", []),  # not a literal
        ("test_t.py", "def test_x():\n    subprocess.run(c, timeout=5)\n    p.communicate(timeout=0.5)\n", [2, 3]),
        ("test_t.py", "def test_x():\n    subprocess.run(c, timeout=30)\n    p.wait(timeout=n)\n", []),
        ("test_t.py", "def test_x():\n    assert elapsed < 2\n    assert r.duration <= 0.5\n    assert elapsed > 2\n", [2, 3]),
        ("test_t.py", "def test_x():\n    assert count < 2\n", []),
        ("test_t.py", "def helper():\n    time.sleep(1)\n    assert ok()\n", []),  # not a test function
        ("tests/h.py", "def helper():\n    subprocess.run(c, timeout=1)\n", [2]),  # any function under tests/
        ("test_t.py", "def test_x():\n    time.sleep(1)  # clock-lint: allow\n    assert ok()\n", []),
        ("test_t.py", "def test_x():\n    # clock-lint: allow\n    assert elapsed < 2\n", []),
        ("test_t.py", "def test_x():\n    sleep(1)\n    assert ok()\n", []),  # bare sleep not imported from time
        ("test_t.py", "from time import sleep as s\ndef test_x():\n    s(1)\n    assert ok()\n", [3]),
        ("test_t.py", "import time as t\ndef test_x():\n    t.sleep(1)\n    assert ok()\n", [3]),
        ("test_t.py", "def test_x():\n    time.sleep(0)\n    assert ok()\n", []),
        ("test_t.py", "def test_x():\n    await asyncio.sleep(1)\n    assert ok()\n", []),
        ("test_t.py", "def test_x():\n    if c:\n        time.sleep(1)\n    else:\n        assert ok()\n", []),
        ("test_t.py", "def test_x():\n    t0 = time.time()\n    assert time.time() - t0 < 2\n", [3]),
        ("test_t.py", "def test_x():\n    assert timer.elapsed() < 2\n", [2]),
        ("test_t.py", "def test_x():\n    q.get(timeout=1)\n", [2]),
        ("test_t.py", "def test_x():\n    run(\n        c,  # clock-lint: allow\n        timeout=1)\n", []),
    ]
    for name, src, want in tm:
        assert timing(name, src) == want, (name, src, timing(name, src), want)
    print("clock_lint selftest ok")


def main(argv):
    if argv == ["--selftest"]:
        return selftest()
    root, base, head, deadline, today = ".", None, "HEAD", None, None
    strict = "--strict" in argv
    added = "--block-added" in argv
    if added:
        argv.remove("--block-added")
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
            elif opt == "--today":
                try:
                    today = datetime.date.fromisoformat(v)
                except ValueError:
                    print("clock_lint: --today needs YYYY-MM-DD, got %r" % v, file=sys.stderr)
                    return 2
            else: head = v
    if added and not base:
        print("clock_lint: --block-added needs --base", file=sys.stderr)
        return 2
    return run(root, base, argv, head, deadline, today, strict, added)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
