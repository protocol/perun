"""Self-test for run_and_score.py on synthetic truth (never set1). Run: python3 test_run_and_score.py"""
import json, os, sys, tempfile
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import run_and_score as R

CLASSES = {"routes": "missing_authn", "outbound": "ssrf", **{c: c for c in R.SIX}}


def synth():
    """Full-size synthetic truth: per part, positives at lines 10*i, decoys 7 lines after each of the first few, file p.x."""
    t = []
    for part, (npos, ndec, _, _) in R.GATE.items():
        for i in range(npos):
            t.append(dict(fixture="f", file=part + ".x", line=100 + 20 * i, kind="positive", **{"class": CLASSES[part]}))
        for i in range(ndec):
            t.append(dict(fixture="f", file=part + ".x", line=110 + 20 * i, kind="decoy", **{"class": CLASSES[part]}))
    return t


def rows_for(truth, kind, part=None, n=None, cls=None, off=0):
    ts = [t for t in truth if t["kind"] == kind and (part is None or R.part_of(t["class"]) == part)][:n]
    return [(t["file"], t["line"] + off, "agent", cls or t["class"], "f") for t in ts]


T = synth()
S = lambda t, r, adj=(): R.score(t, r, adj)[0]


def test_perfect_passes_and_size():
    s = S(T, rows_for(T, "positive"))
    assert all(p["pass"] and p["size_ok"] for p in s.values()), s
    short = S([t for t in T if not (t["class"] == "csrf" and t["kind"] == "decoy")], rows_for(T, "positive"))
    assert not short["csrf"]["size_ok"] and not short["csrf"]["pass"] and short["routes"]["pass"]


def test_wilson_gate_not_just_point():
    # 12 positives: 9/12 = .75 point passes threshold but Wilson LB ~.47 < .55 -> fail; 11/12 passes
    assert not S(T, rows_for(T, "positive", "csrf", 9))["csrf"]["pass"]
    assert S(T, rows_for(T, "positive", "csrf", 11))["csrf"]["pass"]
    assert R.verdict(9, 12, .75)["point"] == .75 and not R.verdict(9, 12, .75)["pass"]


def test_precision_from_decoys_only():
    r = rows_for(T, "positive", "csrf") + rows_for(T, "decoy", "csrf", 6) + [("elsewhere.x", 1, "agent", "csrf", "f")]
    p = S(T, r)["csrf"]
    assert len(p["fp_decoy"]) == 6 and p["precision"]["n"] == 18 and not p["precision"]["pass"], p
    assert S(T, rows_for(T, "positive", "csrf") + [("elsewhere.x", 1, "agent", "csrf", "f")])["csrf"]["precision"]["pass"]  # unmatched row is not a decoy FP


def test_window_part_and_fixture():
    assert S(T, rows_for(T, "positive", "csrf", off=3))["csrf"]["recall"]["k"] == 12
    assert S(T, rows_for(T, "positive", "csrf", off=4))["csrf"]["recall"]["k"] == 0
    # route family: any route class hits; other part or other fixture does not
    assert S(T, rows_for(T, "positive", "routes", cls="missing_object_check"))["routes"]["recall"]["k"] == 30
    assert S(T, rows_for(T, "positive", "routes", cls="ssrf"))["routes"]["recall"]["k"] == 0
    other = [r[:4] + ("g",) for r in rows_for(T, "positive", "routes")]
    assert S(T, other)["routes"]["recall"]["k"] == 0
    assert S(T, [r[:4] for r in rows_for(T, "positive", "routes")])["routes"]["recall"]["k"] == 30  # no fixture named
    assert S(T, [("csrf.x", 0, "agent", "csrf", "f")])["csrf"]["recall"]["k"] == 1  # file-level row credits one


def test_one_fp_per_decoy_and_not_run():
    r = rows_for(T, "decoy", "csrf", 1) + rows_for(T, "decoy", "csrf", 1, off=1)
    assert len(S(T, r)["csrf"]["fp_decoy"]) == 1


def test_classify_and_parse():
    assert R.classify("route-auth", "missing-auth", "x") == "missing_authn"
    assert R.classify("attempt-limit", "missing-attempt-limit", "") == "rate_limit"
    assert R.classify("semgrep", "r", "requests.get(url, verify=False)") == "tls_off"
    assert R.classify("semgrep", "r", "unrelated") is None
    out = json.dumps([{"file": "a", "line": 3, "tool": "route-auth", "rule": "missing-auth", "text": "t"},
                      {"file": "a", "line": 3, "tool": "route-auth", "rule": "missing-auth", "text": "t"},
                      {"file": "b", "line": 1, "tool": "route-auth", "rule": "not-checked", "text": "csrf"}])
    assert R.parse_rows(out) == [("a", 3, "route-auth", "missing_authn")] and R.parse_rows("junk") == []
    assert R.parse_not_run("review_checks: NOT RUN: gosec (x), tenant-scope (SKIPPED: y)") == {"gosec", "tenant-scope"}
    assert R.parse_not_run("NOT RUN: none") == set()
    assert R.parse_rows(json.dumps([{"file": "a", "line": "12-14", "tool": "route-auth", "rule": "missing-auth"}])) == [("a", 12, "route-auth", "missing_authn")]


def test_inventory_and_rows_file():
    routes = {"f": [dict(file="a", line=10), dict(file="a", line=50), dict(file="b", line=1)]}
    claims = [("a", 12, "agent", "route_inventory", "f"), ("a", 80, "agent", "route_inventory", "f")]
    assert R.inventory_rows(routes, claims) == {"found": 1, "listed": 3, "basis": "route_inventory rows"}
    assert R.inventory_counts(routes, {"f": 9})["found"] == 3 and R.inventory_counts(routes, {})["found"] == 0
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump([{"file": "a", "line": 2, "class": "csrf", "fixture": "f"}, {"file": "b", "class": "pii_log"}], f)
    json.dump([{"file": "a", "line": 1, "class": "bogus"}], open(f.name, "w"))
    try:
        R.load_rows(f.name)
        raise AssertionError("bad class accepted")
    except ValueError:
        pass
    json.dump([{"file": "a", "line": 2, "class": "csrf", "fixture": "f"}, {"file": "b", "class": "pii_log"}], open(f.name, "w"))
    assert R.load_rows(f.name) == [("a", 2, "agent", "csrf", "f"), ("b", 0, "agent", "pii_log", None)]
    os.unlink(f.name)


def test_refuses_existing_out():
    with tempfile.TemporaryDirectory() as d:
        try:
            R.run(d, ".")
        except FileExistsError:
            return
    raise AssertionError("existing --out accepted")


SEMGREP = json.dumps([{"file": "csrf.x", "line": 100, "tool": "semgrep", "rule": "csrf-missing", "text": ""}])


def test_not_run_is_per_fixture_and_whole_tool_only():
    nr = "review_checks: NOT RUN: semgrep (missing)"
    assert R.fixture_rows("A", SEMGREP, nr) == []
    assert R.fixture_rows("B", SEMGREP, "review_checks: NOT RUN: gosec (x)") == [("csrf.x", 100, "semgrep", "csrf", "B")]
    assert R.parse_not_run("NOT RUN: semgrep p/default (why), gosec (x)") == {"gosec"}
    assert R.fixture_rows("A", SEMGREP, "NOT RUN: semgrep p/default (why)") != []


def test_path_normalization_and_warning():
    r = [("./csrf.x", 100, "agent", "csrf", None), ("f\\csrf.x", 120, "agent", "csrf", "f")]
    assert S(T, r)["csrf"]["recall"]["k"] == 2
    assert R.score(T, r)[1] == []
    assert R.score(T, [("nowhere.x", 5, "agent", "csrf", "f")])[1] == ["no row path matches any truth file"]


def test_file_level_row_credits_one_positive_but_flags_all_decoys():
    p = S(T, [("csrf.x", 0, "agent", "csrf", "f")])["csrf"]
    assert p["recall"]["k"] == 1 and len(p["fp_decoy"]) == 8, p
    two = S(T, [("csrf.x", 0, "agent", "csrf", "f"), ("csrf.x", 0, "agent", "csrf", "f")])["csrf"]
    assert two["recall"]["k"] == 2
    located = S(T, [("csrf.x", 100, "agent", "csrf", "f"), ("csrf.x", 0, "agent", "csrf", "f")])["csrf"]
    assert located["recall"]["k"] == 2  # file-level row skips the already-matched first positive


def test_rule_class_anchors():
    assert R.classify("semgrep", "r", "password in login handler") is None
    assert R.classify("semgrep", "r", "password written to log") == "secret_in_log"
    assert R.classify("semgrep", "r", "personal data catalog") is None
    assert R.classify("semgrep", "r", "PII written to log with user data") == "pii_log"
    assert R.classify("committed-personal-data", "r", "emails in dump.csv") == "pii_data"
    assert R.classify("semgrep", "r", "PII in seed data") == "pii_data"


def test_adjudication_and_pending():
    extra = [("csrf.x", 5000, "agent", "csrf", "f")]
    base = rows_for(T, "positive", "csrf")
    p, _ = R.score(T, base + extra)
    assert p["csrf"]["unmatched"] == [["f", "csrf.x", 5000]] and p["csrf"]["pending_adjudication"] and not p["csrf"]["pass"]
    adj = lambda v: [{"fixture": "f", "file": "csrf.x", "line": 5000, "class": "csrf", "verdict": v}]
    tp = S(T, base + extra, adj("tp"))["csrf"]
    assert tp["positives"] == 13 and tp["recall"]["k"] == 13 and tp["pass"] and not tp["pending_adjudication"]
    fp = S(T, base + extra, adj("fp"))["csrf"]
    assert fp["precision"]["n"] == 13 and fp["recall"]["k"] == 12 and not fp["pending_adjudication"]
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump([{"fixture": "f", "file": "./csrf.x", "line": "5-6", "class": "csrf", "verdict": "maybe"}], f)
    try:
        R.load_adjudicated(f.name)
        raise AssertionError("bad verdict accepted")
    except ValueError:
        pass
    os.unlink(f.name)


def test_run_errors_are_loud():
    assert R.run_errors("A", "[]", 0) == []
    assert R.run_errors("A", "", "timeout") == ["A: timeout"]
    assert R.run_errors("A", "oops", 0) == ["A: stdout is not a JSON list"]
    assert R.run_errors("A", "[]", 3) == ["A: exit 3"]
    assert R.run_errors("A", "{}", 0) == ["A: stdout is not a JSON list"]


def test_nits():
    assert R.to_line("12-14") == 12 and R.to_line(None) == 0 and R.to_line("x") == 0
    v = R.verdict(0, 0, .8)
    assert v["point"] == 1.0 and not v["pass"]
    import subprocess
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_and_score.py"), "--rows"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "IndexError" not in r.stderr and "needs a value" in r.stderr, r.stderr
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_and_score.py"), "--help"],
                       capture_output=True, text=True, timeout=10)  # must exit before any scored run starts
    assert r.returncode != 0 and "unknown argument" in r.stderr, r.stderr
    for argv in ([], ["set1"], ["--rows", "x.json", "extra"]):  # bare call and stray positionals never start a run
        r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_and_score.py"), *argv],
                           capture_output=True, text=True, timeout=10)
        assert r.returncode != 0 and ("unknown argument" in r.stderr or "no arguments" in r.stderr), (argv, r.stderr)


def test_strict_missing_path_is_fp_and_tp_adds_no_positive():
    have = lambda fx, f: f != "ghost.x"
    ghost = [("ghost.x", 5, "agent", "csrf", "f")]
    adj = [{"fixture": "f", "file": "ghost.x", "line": 5, "class": "csrf", "verdict": "tp"}]
    assert S(T, ghost, adj)["csrf"]["adjudicated_tp"] == 1  # legacy: adjudicated tp joins positives
    s = R.score(T, ghost, adj, have)[0]["csrf"]  # strict: missing path = FP before adjudication
    assert s["adjudicated_fp"] == 1 and s["adjudicated_tp"] == 0 and not s["pending_adjudication"]
    real = [("elsewhere.x", 5, "agent", "csrf", "f")]
    adj2 = [{"fixture": "f", "file": "elsewhere.x", "line": 5, "class": "csrf", "verdict": "tp"}]
    hits = rows_for(T, "positive", "csrf", 6)
    legacy, strict = S(T, hits + real, adj2)["csrf"], R.score(T, hits + real, adj2, have)[0]["csrf"]
    assert legacy["positives"] == 13 and legacy["recall"]["n"] == 13
    assert strict["positives"] == 12 and strict["recall"]["k"] == 6 and strict["recall"]["n"] == 12
    assert strict["adjudicated_tp"] == 1 and strict["precision"]["k"] == 7 and strict["precision"]["n"] == 7  # tp is a correct claim


def test_legacy_sets_keep_old_scoring():
    assert R.LEGACY_SETS == ("set1", "set2", "set3")


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
    print("%d/%d tests passed" % (len(fns), len(fns)))
