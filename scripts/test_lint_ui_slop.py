#!/usr/bin/env python3
"""Bench + contract tests for lint_ui_slop.py over scripts/ui-slop-fixtures (bad-<rule>-N.* seeded, ok-*.* clean).

Asserts recall >= 0.8 over seeded files (the named rule fires), 0 findings on clean files, every rule seeded,
each call under 1 s, exit codes 0/2/1, --json shape, --hook, and tokens handling. Prints "Tests: P/N".
"""
import json
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LINT = ROOT / ".claude/skills/deep-code-review/scripts/lint_ui_slop.py"
FIX = ROOT / "scripts/ui-slop-fixtures"
RULES = re.findall(r"^  ([a-z-]+) {2,}\S", LINT.read_text().split("RULES")[1].split("TOKENS.")[0], re.M)
results = []


def run(*args, stdin=None, cwd=None):
    t = time.monotonic()
    p = subprocess.run([sys.executable, str(LINT), *map(str, args)], capture_output=True, text=True, input=stdin, cwd=cwd)
    return p, time.monotonic() - t


def check(ok, name):
    results.append(bool(ok))
    print(("PASS  " if ok else "FAIL  ") + name)


seeded = sorted(FIX.rglob("bad-*"))
clean = sorted(p for p in FIX.rglob("ok-*"))
hit, fp, slow = 0, [], []
for p in seeded:
    rule = re.match(r"bad-(.+)-\d+\.", p.name).group(1)
    proc, dt = run("--json", p)
    slow += [p.name] if dt >= 1 else []
    hit += rule in {x["rule"] for x in json.loads(proc.stdout)}
for p in clean:
    proc, dt = run("--json", p)
    slow += [p.name] if dt >= 1 else []
    fp += [(p.name, x["rule"]) for x in json.loads(proc.stdout)]
recall = hit / len(seeded)
print(f"BENCH seeded={len(seeded)} clean={len(clean)} recall={recall:.3f} false_positives={len(fp)}")
check(len(seeded) + len(clean) >= 40 and len(clean) >= 20, "fixture corpus has >= 40 files, half clean")
check(recall >= 0.8, f"recall {recall:.3f} >= 0.8")
check(not fp, f"0 false positives on clean files {fp}")
check(not slow, f"every call under 1 s {slow}")
check(len(RULES) == 15 and all(any(f"bad-{r}-" in p.name for p in seeded) for r in RULES), "15 rules, each seeded")

proc, _ = run(FIX / "ok-plain-2.html")
check(proc.returncode == 0 and not proc.stdout, "clean file exits 0")
proc, _ = run(FIX / "bad-img-alt-1.html")
check(proc.returncode == 2 and "img-alt" in proc.stdout and re.search(r":\d+: img-alt:", proc.stdout), "findings exit 2, path:line: rule")
proc, _ = run("--json", FIX / "bad-heading-skip-1.html")
rows = json.loads(proc.stdout)
check(proc.returncode == 2 and set(rows[0]) == {"path", "line", "rule", "message"} and rows[0]["line"] == 3, "--json rows have path/line/rule/message, line 3")
check(run(FIX / "missing-file.css")[0].returncode == 1, "missing path exits 1")
check(run()[0].returncode == 1 and run("--nope")[0].returncode == 1, "no args and unknown option exit 1")
check(run("--tokens")[0].returncode == 1, "--tokens without a value exits 1")
check(run(LINT)[0].returncode == 0, "non-UI extension is ignored")
proc, _ = run("--json", FIX / "tokens/bad-off-token-hex-1.css")
check(proc.returncode == 2 and [x["rule"] for x in json.loads(proc.stdout)] == ["off-token-hex"], "tokens file auto-found next to file")
proc, _ = run("--tokens", FIX / "tokens/tokens.css", "--json", FIX / "bad-low-contrast-1.css")
check(proc.returncode == 2 and any(x["rule"] == "off-token-hex" for x in json.loads(proc.stdout)), "--tokens explicit enables off-token-hex")
with tempfile.TemporaryDirectory() as td:
    tmp = Path(td).resolve()
    (tmp / "tokens.css").write_text(".x { color: #999999; background: #ffffff; }\n")  # would trip low-contrast if linted
    proc, _ = run("--json", tmp / "tokens.css", cwd=tmp)
    check(proc.returncode == 0, "tokens file itself is never linted (discriminates: its own content has a finding)")

    # find_tokens: bounded at the nearest .git; with no .git, at the cwd; outside the cwd, the file's own dir only.
    (tmp / "tokens.css").write_text(":root { --a: #111111; }\n")
    (tmp / "proj/src").mkdir(parents=True)
    (tmp / "proj/src/x.css").write_text(".c { color: #123456; }\n")
    proc, _ = run("--json", "src/x.css", cwd=tmp / "proj")
    check(proc.returncode == 0, "no .git: token search stops at the cwd (tokens file above it is ignored)")
    proc, _ = run("--json", tmp / "proj/src/x.css", cwd=ROOT)
    check(proc.returncode == 0, "file outside the cwd: only its own directory is searched")
    (tmp / "proj/src/tokens.css").write_text(":root { --a: #111111; }\n")
    proc, _ = run("--json", tmp / "proj/src/x.css", cwd=ROOT)
    check(proc.returncode == 2, "file outside the cwd still finds a tokens file in its own directory")
    (tmp / "proj/src/tokens.css").unlink()
    (tmp / "repo/.git").mkdir(parents=True)
    (tmp / "repo/sub").mkdir()
    (tmp / "repo/tokens.css").write_text(":root { --a: #111111; }\n")
    (tmp / "repo/sub/a.css").write_text(".c { color: #123456; }\n")
    proc, _ = run("--json", "a.css", cwd=tmp / "repo/sub")
    check(proc.returncode == 2 and [x["rule"] for x in json.loads(proc.stdout)] == ["off-token-hex"],
          "repo-root tokens file found from a subdir cwd (bounded at .git, not the cwd)")
    (tmp / "tokens.css").write_text(":root { --a: #123456; }\n")  # above .git: must stay out of reach
    (tmp / "repo/tokens.css").unlink()
    proc, _ = run("--json", "a.css", cwd=tmp / "repo/sub")
    check(proc.returncode == 0, "token search never climbs above the nearest .git")

    # 1.5 MB file must stay far below the 5 s hook timeout (line lookup was O(n) per match).
    big = tmp / "big.html"
    big.write_text('<html lang="en"><head><style>\n' + "p { margin: 0; }\n" * 5000 + "</style></head><body>\n"
                   + '<div><h2>t</h2><img src="a.png" alt="x"></div>\n' * 30000 + "</body></html>\n")
    proc, dt = run(big, cwd=tmp)
    check(big.stat().st_size > 1_400_000 and proc.returncode == 0 and dt < 5, f"1.5 MB file lints clean in {dt:.1f}s (< 5 s)")
    # 60k :focus-visible mentions in 1.2 MB with no braces: the ring scan must stay linear (hook timeout is 5 s).
    ring = tmp / "ring.tsx"
    ring.write_text('const s = ":focus-visible :focus-visible :focus-visible";\n' * 20000)
    proc, dt = run(ring, cwd=tmp)
    check(ring.stat().st_size > 1_100_000 and proc.returncode == 0 and dt < 3, f"60k :focus-visible mentions lint in {dt:.1f}s (< 3 s)")
def rows(name):
    return [(x["line"], x["rule"], x["message"]) for x in json.loads(run("--json", FIX / name)[0].stdout)]


check([r[0] for r in rows("bad-outline-removed-3.css")] == [1, 4],
      "outline:none inside :focus-visible is not a ring, so it never exempts another outline:none")
check([r[0] for r in rows("bad-outline-removed-4.css")] == [4],
      "a :focus-visible ring on one selector base never exempts outline:none on another")
check([r[0] for r in rows("bad-outline-removed-5.css")] == [4],
      "a bare :focus-visible ring does not exempt button:focus (higher specificity wins)")
check([(r[0], r[2]) for r in rows("bad-low-contrast-4.css")] == [(1, "contrast 3.95:1 is under 4.5:1"), (6, "contrast 2.32:1 is under 3:1")],
      "contrast: body text needs 4.5:1, text >= 24px needs 3:1 (still flagged below it)")
check(not rows("ok-contrast-3.css"), "large text (24px+, or 18.66px+ bold) passes at 3:1")
check([r[0] for r in rows("bad-no-reduced-motion-3.css")] == [2], "animation list with any non-none entry is motion")
proc, _ = run(FIX)
check(proc.returncode == 2 and "bad-img-alt-1.html" in proc.stdout, "directory walk lints every UI file")
bad = FIX / "bad-dead-link-1.html"
proc, _ = run("--hook", stdin=json.dumps({"tool_input": {"file_path": str(bad)}}))
check(proc.returncode == 2 and not proc.stdout and "dead-link" in proc.stderr, "--hook reads the event, writes findings to stderr, exits 2")
proc, _ = run("--hook", stdin=json.dumps({"tool_input": {"file_path": str(FIX / "gone.html")}}))
check(proc.returncode == 0, "--hook ignores a missing file")
proc, _ = run("--hook", stdin="not json")
check(proc.returncode == 1, "--hook with bad JSON exits 1")

print(f"Tests: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
