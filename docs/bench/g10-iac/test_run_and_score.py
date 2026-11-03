"""Self-test for run_and_score.py on a tiny synthetic truth (never set1). Run: python3 -m pytest or python3 test_run_and_score.py"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_and_score as R

T = [dict(fixture="f", file="a.yml", line=10, kind="positive", history=False),
     dict(fixture="f", file="a.yml", line=30, kind="positive", history=False),
     dict(fixture="f", file="b.yml", line=5, kind="decoy", history=False),
     dict(fixture="f", file="h.ini", line=2, kind="positive", history=True),
     dict(fixture="f", file="old.txt", line=1, kind="decoy", history=True)]
row = lambda f, l, tool="zizmor", rule="x", text="": (f, l, tool, rule, text)
SHA = "abcdef1234567890abcdef1234567890abcdef12"


def test_window_edges():
    s = R.score_fixture(T, [row("a.yml", 13), row("a.yml", 34)], commits={"h.ini": SHA})
    assert s["hits"] == 1 and s["missed"] == [["a.yml", 30], ["h.ini", 2]], s


def test_history_by_path_or_commit():
    assert R.score_fixture(T, [row("x", 0, text="leak in h.ini")], commits={"h.ini": SHA})["hits"] == 1
    assert R.score_fixture(T, [row("x", 0, text="commit abcdef1 leaks")], commits={"h.ini": SHA})["hits"] == 1
    assert R.score_fixture(T, [row("x", 0, text="commit abcdef")], commits={"h.ini": SHA})["hits"] == 0


def test_decoy_fp_per_decoy():
    s = R.score_fixture(T, [row("b.yml", 8), row("b.yml", 7, rule="y"), row("b.yml", 20), row("old.txt", 99, text="old.txt")])
    assert s["fp_decoy"] == [["b.yml", 5], ["old.txt", 1]], s  # two rows on b.yml = one FP; b.yml:20 alone would be none


def test_file_level_row_matches_file():
    s = R.score_fixture(T, [row("a.yml", 0, tool="hadolint"), row("b.yml", 0)])
    assert s["hits"] == 2 and s["fp_decoy"] == [["b.yml", 5]], s
    assert R.score_fixture(T, [row("b.yml", 20)])["fp_decoy"] == []


def test_sh_timeout_and_status():
    import subprocess
    orig = subprocess.run
    def boom(*a, **k): raise subprocess.TimeoutExpired("x", 1)
    subprocess.run = boom
    try:
        assert R.sh(["x"]) == ("", "", "timeout")
    finally:
        subprocess.run = orig
    assert R.sh(["false"])[2] == 1 and R.sh(["true"])[2] == 0


def test_not_run_rows_are_misses():
    nr = R.parse_not_run("x\nreview_checks: NOT RUN: checkov (timeout), semgrep p/default pack (cold)\n")
    assert nr == {"checkov", "semgrep"}
    assert R.score_fixture(T, [row("a.yml", 10, tool="checkov")], nr)["hits"] == 0
    assert R.parse_not_run("review_checks: NOT RUN: none") == set()


def test_parse_rows_drops_not_checked_and_dups():
    j = '[{"file":"a","line":1,"tool":"t","rule":"r","text":"r: m"},{"file":"a","line":1,"tool":"t","rule":"r"},' \
        '{"file":"a","line":0,"tool":"t","rule":"not-checked"}]'
    assert R.parse_rows(j) == [("a", 1, "t", "r", "r: m")] and R.parse_rows("garbage") == []


def test_control_only_iac_tools():
    rs = [row("Dockerfile", 1, tool="hadolint"), row("a", 1, tool="trivy-secret"), row("a.py", 1, tool="ruff"),
          row("a", 1, tool="checkov")]
    assert R.score_control(rs, {"checkov"}) == [("Dockerfile", 1), ("a", 1)]
    assert R.score_control(rs + [row("a", 1, tool="gitleaks")], {"checkov"}) == [("Dockerfile", 1), ("a", 1)]  # per (file, line)


def test_wilson_and_pass():
    assert R.wilson_lower(0, 0) == 0.0 and abs(R.wilson_lower(8, 10) - 0.4902) < 1e-3
    s = R.summarize({"f": {"positives": 10, "hits": 8, "fp_decoy": [["x"]] * 2}}, [])
    assert s["recall"] == 0.8 and s["precision"] == 0.8 and s["pass"]
    s = R.summarize({"f": {"positives": 10, "hits": 8, "fp_decoy": [["x"]] * 2}}, [("c", 1)])
    assert not s["pass"]
    assert not R.summarize({"f": {"positives": 10, "hits": 7, "fp_decoy": []}}, [])["pass"]


def test_set_option_selects_build():
    """run(..., sset=DIR) builds DIR/build.py (not set1) and scores its truth with a stub detector."""
    import json, tempfile
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "s", "x")); os.makedirs(os.path.join(d, "det", os.path.dirname(R.RC)))
        open(os.path.join(d, "s", "build.py"), "w").write(
            "import sys, os, json\nt = sys.argv[1]\nfor f in ('fx', 'control'): os.makedirs(os.path.join(t, f))\n"
            "json.dump([dict(fixture='fx', file='a.yml', line=1, kind='decoy', history=False)], open(sys.argv[3], 'w'))\n")
        open(os.path.join(d, "det", R.RC), "w").write("exit 0\n")
        res = R.run(os.path.join(d, "out"), os.path.join(d, "det"), os.path.join(d, "s"))
        assert "fx" in json.load(open(os.path.join(d, "out", "score.json")))["fixtures"], res


if __name__ == "__main__":
    fs = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for f in fs:
        f()
    print("tests: %d/%d" % (len(fs), len(fs)))
