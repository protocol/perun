"""Self-test for agentic_arm.py: canned report + stub `claude` on PATH. No paid call, never touches set1. Run: python3 test_agentic_arm.py"""
import json, os, stat, sys, tempfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import agentic_arm as A

REPORT = """# Security audit: demo
## Per-standard table
| Item | Status | Basis | Files | Negative |
|---|---|---|---|---|
| Missing authentication on admin export | fail | guided:x | app.py:12, lib/h.py:40-44 | |
| Outbound TLS verification disabled | Fail (confirmed) | tool:t | app.py:30 | |
| Weird thing nobody maps | fail | guided:y | app.py:50 | |
| Rate limiting | pass | tool:t | app.py:5 | `limiter()` |
## Routes
- GET /export app.py:12
## NOT CHECKED
- cookie flags app.py:99: no runtime
## Notes
- **High** `app.py:60` SSRF in fetch_url
"""
INIT = {"type": "system", "subtype": "init", "skills": ["perun:deep-code-review", "update-config"]}
USE = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "@DET@/.claude/skills/deep-code-review/references/security-review-mode.md"}}]}}
RL = {"type": "rate_limit_event", "rate_limit_info": {"unifiedWindows": {"5h": {"utilization": 0.1}}}}


def result(body, cost=0.4, subtype="success", err=False, denials=()):
    return {"type": "result", "subtype": subtype, "result": body, "total_cost_usd": cost, "is_error": err, "permission_denials": list(denials)}


def stub(d, events, sleep=0):
    (Path(d) / "out.jsonl").write_text(("\n".join(json.dumps(e) for e in events) + "\n").replace("@DET@", str(Path(d).resolve().parent)))
    p = Path(d) / "claude"
    p.write_text('#!/bin/sh\necho call >> "$STUB_LOG"\ncat >/dev/null\ncat "%s/out.jsonl"\nsleep %d\n' % (d, sleep))
    p.chmod(p.stat().st_mode | stat.S_IEXEC)


def env(events, n=3, sleep=0):
    tmp = Path(tempfile.mkdtemp()); (tmp / "bin").mkdir()
    stub(tmp / "bin", events, sleep)
    for i in range(n):
        (tmp / "fx" / ("fx%d" % i) / ".git").mkdir(parents=True)
    os.environ.update(PATH=str(tmp / "bin") + os.pathsep + os.environ["PATH"], STUB_LOG=str(tmp / "log"))
    return tmp


def go(events, cap=15.0, per_call=3.0, n=3, parser=A.parse_report):
    tmp = env(events, n)
    rows, unm, errs = A.run(tmp, tmp / "out", tmp / "fx", cap, per_call, parser)
    return tmp, rows, unm, errs


def calls(tmp):
    return len(Path(tmp, "log").read_text().split()) if Path(tmp, "log").exists() else 0


def key(rows):
    return {(r["file"], r["line"], r["class"]) for r in rows}


def test_parse_basic():
    rows, unm = A.parse_report(REPORT, "fx")
    k = key(rows)
    assert {("app.py", 12, "missing_authn"), ("lib/h.py", 40, "missing_authn"), ("app.py", 30, "tls_off"),
            ("app.py", 60, "ssrf"), ("app.py", 12, "route_inventory")} <= k
    assert [(u["line"], u["class"]) for u in unm] == [(50, "unmapped")] and unm[0]["text"]
    assert not any(r["line"] in (5, 99) for r in rows)


def test_cite_forms():
    t = "## Findings\n- Missing authentication at src/a.py#L12\n- SSRF in src/b.py#L7-L9\n- tls verify off, src/c.py lines 40-44\n" \
        "- tls verify off at app/[id]/route.ts:8\n- ssrf at /tmp/x/fx/src/d.py:3\n"
    k = key(A.parse_report(t, "fx", "/tmp/x/fx")[0])
    assert {("src/a.py", 12, "missing_authn"), ("src/b.py", 7, "ssrf"), ("src/c.py", 40, "tls_off"),
            ("app/[id]/route.ts", 8, "tls_off"), ("src/d.py", 3, "ssrf")} <= k


def test_no_cite_or_no_line_goes_unmapped():
    rows, unm = A.parse_report("## Findings\n- Missing authentication somewhere in the app\n- ssrf in src/e.py\n", "fx")
    assert rows == [] and len(unm) == 2 and all(u["line"] == 0 and u["class"] == "unmapped" for u in unm)


def test_route_heading_scope():
    t = "## Route inventory\n- GET /a a.py:3\n## Routes missing auth\n- POST /b b.py:4 unauthenticated\n## Findings\n- c.py:5 note\n"
    rows, _ = A.parse_report(t, "fx")
    assert ("a.py", 3, "route_inventory") in key(rows) and ("b.py", 4, "route_inventory") not in key(rows)
    assert ("b.py", 4, "missing_authn") in key(rows)


def test_columns_from_header_and_head_skip():
    t = "## Table\n| Item | Basis | Where | Files | Status |\n|--|--|--|--|--|\n| ssrf thing | tool:t | n/a | a.py:9 | fail |\n" \
        "## Dependencies of note\n- ssrf a.py:1\n## Other static findings\n- ssrf a.py:2\n"
    k = key(A.parse_report(t, "fx")[0])
    assert ("a.py", 9, "ssrf") in k and ("a.py", 2, "ssrf") in k and ("a.py", 1, "ssrf") not in k


def test_agent_class_tightened():
    assert A.classify("unauthorized access to the dashboard from the web") != "missing_authz"
    assert A.classify("missing authorization check") == "missing_authz"
    assert A.classify("tenants are listed here") is None and A.classify("cross-tenant read") == "missing_object_check"


def test_ok_flags_and_scorer_accepts():
    tmp, rows, unm, errs = go([INIT, USE, RL, result(REPORT, denials=[{"tool_name": "Bash"}])])
    import run_and_score as R
    assert not errs and calls(tmp) == 3 and len(R.load_rows(tmp / "out" / "rows.json")) == len(rows) == 15
    m = json.load(open(tmp / "out" / "meta.json"))
    assert m["model"] == "claude-sonnet-5-5" and "Skill" in m["allowed"] and "Agent" in m["allowed"] and "Write" in m["disallowed"]
    assert json.loads((tmp / "out" / "ledger.jsonl").read_text().splitlines()[0])["denials"] == [{"tool_name": "Bash"}]


def test_budget_hit_is_invalid_but_keeps_text():
    tmp, rows, unm, errs = go([INIT, USE, RL, result("partial text", cost=3.0, subtype="error_max_budget_usd", err=True)], n=1)
    e = json.load(open(tmp / "out" / "errors.json"))
    assert e["complete"] is False and errs[0]["subtype"] == "error_max_budget_usd" and errs[0]["returncode"] == 0
    assert (tmp / "out" / "reports" / "fx0.md").read_text() == "partial text"


def test_total_cap_stops_loud():
    tmp, rows, unm, errs = go([INIT, USE, RL, result(REPORT, cost=0.9)], cap=1.0)
    assert any("cap" in e.get("stop", "") for e in errs) and calls(tmp) < 3


def test_quota_stop_and_unknown_util_continues():
    assert any("quota" in e.get("stop", "") for e in go([INIT, {**RL, "rate_limit_info": {"unifiedWindows": {"5h": {"utilization": 0.85}}}}, result(REPORT)])[3])
    tmp, rows, unm, errs = go([INIT, USE, result(REPORT)])
    assert not errs and calls(tmp) == 3 and json.loads((tmp / "out" / "ledger.jsonl").read_text().splitlines()[0])["util_known"] is False


def test_empty_report_is_error():
    assert any(e.get("error") == "empty report" for e in go([INIT, USE, RL, result("  ")])[3])


def test_timeout_keeps_partial_and_kills():
    tmp = env([INIT, {"type": "assistant", "message": {"content": [{"type": "text", "text": "half a report"}]}}], sleep=30)
    r = A.sh_claude("p", str(tmp), tmp, 1.0, timeout=1)
    assert "timeout" in r["err"] and r["text"] == "half a report" and r["cost"] == 1.0


def test_no_result_event_books_whole_call_cap():
    tmp = env([INIT, {"type": "assistant", "message": {"content": [{"type": "text", "text": "crashed mid-run"}]}}])
    r = A.sh_claude("p", str(tmp), tmp, 2.5)
    assert "no result event" in r["err"] and r["text"] == "crashed mid-run" and r["cost"] == 2.5, r


def test_answer_key_gone_before_run():
    tmp = Path(tempfile.mkdtemp()); (tmp / "set").mkdir()
    (tmp / "set" / "build.py").write_text("import os, sys\nos.makedirs(sys.argv[1], exist_ok=True)\nopen(sys.argv[3], 'w').write('[]')\n"
                                          "open(%r, 'w').write(sys.argv[3])\n" % str(tmp / "where"))
    seen, orig = [], A.run
    A.run = lambda *a: seen.append(os.path.exists((tmp / "where").read_text())) or ([], [], [])
    try:
        A.main(["--detector", str(tmp), "--out", str(tmp / "o"), "--set", str(tmp / "set")])
    finally:
        A.run = orig
    assert seen == [False]  # truth.json deleted before the paid agent could Read it


def test_skill_not_loaded_is_error():
    tmp, rows, unm, errs = go([INIT, RL, result(REPORT)], n=1)
    assert rows == [] and errs[0]["error"] == "skill not loaded" and json.load(open(tmp / "out" / "errors.json"))["complete"] is False
    # a Read of some other repo's skill file is not evidence
    other = {**USE, "message": {"content": [{"type": "tool_use", "name": "Read", "input": {"file_path": "/elsewhere/.claude/skills/deep-code-review/x.md"}}]}}
    assert go([INIT, other, RL, result(REPORT)], n=1)[3][0]["error"] == "skill not loaded"
    sk = {"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": "perun:deep-code-review"}}]}}
    assert not go([INIT, sk, RL, result(REPORT)], n=1)[3]


def test_raw_stream_saved_and_prompt_pinned():
    tmp, *_ = go([INIT, USE, RL, result(REPORT)], n=1)
    assert INIT["subtype"] in (tmp / "out" / "raw" / "fx0.jsonl").read_text()
    assert A.PROMPT.startswith("/perun:deep-code-review Security audit of this whole project (FULL scope).")
    assert json.load(open(tmp / "out" / "meta.json"))["prompt"] == A.PROMPT


def test_live_rate_limit_shape():
    tmp, *_ = go([INIT, USE, {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning", "utilization": 0.85}}, result(REPORT)])
    assert any("quota" in e.get("stop", "") for e in json.load(open(tmp / "out" / "errors.json"))["errors"])


def test_table_without_status_and_multicite_and_fix_heading():
    t = "## Findings\n| # | Severity | Location | Issue |\n|---|---|---|---|\n| 1 | High | `server.js:8-12`, `server.js:18` | **SSRF.** bad |\n" \
        "## Fix order\n1. ssrf in server.js:99\n## Remediation plan\n- ssrf server.js:98\n"
    rows, unm = A.parse_report(t, "fx")
    assert key(rows) == {("server.js", 8, "ssrf"), ("server.js", 18, "ssrf")} and unm == []


def test_calibration_report():
    rows, unm = A.parse_report((HERE / "calib_notes_app_report.md").read_text(), "notes-app")
    k = key(rows)
    assert {("server.js", 21, "missing_authn"), ("server.js", 27, "ssrf"), ("server.js", 28, "tls_off"), ("server.js", 22, "missing_object_check"),
            ("server.js", 15, "secret_in_log"), ("server.js", 19, "cookie_flags"), ("server.js", 13, "rate_limit"), ("server.js", 21, "route_inventory")} <= k
    assert ("server.js", 99, "ssrf") not in k and not any(r["class"] == "route_inventory" and r["line"] in (99,) for r in rows)


def test_init_check_aborts_before_next_call():
    for skills in (["deep-code-review"], ["update-config"], [{"name": "perun:deep-code-review"}, {"name": "x", "path": os.path.expanduser("~/.claude/skills/x")}]):
        tmp, rows, unm, errs = go([{**INIT, "skills": skills}, USE, RL, result(REPORT)])
        assert calls(tmp) == 1 and rows == [] and any("isolation" in e.get("stop", "") for e in errs), skills
    assert A.init_ok(["perun:deep-code-review", "update-config"]) and not A.init_ok(None)


def test_leading_paren_stripped_but_group_kept():
    assert A.cites("(`server.js:21`)")[0] == [("server.js", 21)] and A.cites("see app/(auth)/x.ts:3")[0] == [("app/(auth)/x.ts", 3)]


def test_log_in_is_not_logging():
    assert A.classify("Set the cookie, or log in with the leaked password, to act as admin") is None
    assert A.classify("anyone logged in can read it") is None and A.classify("password is logged") == "secret_in_log"


def test_credentials_logged_fallback():
    assert A.classify("Medium: plaintext credentials are logged") == "secret_in_log"


def test_subbullet_inherits_parent_cites():
    t = "## Findings\n1. **High: stuff** (`a.js:5`).\n   - Any anonymous request, no authentication, leaks data.\n   - Nothing classifiable here.\n"
    rows, unm = A.parse_report(t, "fx")
    assert key(rows) == {("a.js", 5, "missing_authn")} and [u["file"] for u in unm] == ["a.js", ""]


def test_attack_chain_heading_skipped():
    assert A.parse_report("## Attack chains\n- ssrf at `a.js:9`\n", "fx") == ([], [])


def test_subbullet_multi_cite_parent_goes_unmapped():
    t = "## Findings\n1. **Medium: weak storage** (`db.js:1`, `server.js:16`).\n   - There is no rate limiting on /login.\n"
    rows, unm = A.parse_report(t, "fx")
    assert not any(r["class"] == "rate_limit" for r in rows) and unm[-1]["file"] == "" and "rate limiting" in unm[-1]["text"]


V2 = """# Audit
## Routes
- GET /x a.py:3
## Findings
- [missing-authn] a.py:10 admin export open; evidence: b.py:20
- [object-level-authz] c.py:5 other users' notes
- [pii-in-log] d.py:7
- [hardcoded-secret] e.py:1 key in source
- [xss] f.py:2
- [ssrf] no line given here
- no label but g.py:9
  - [csrf] h.py:4 sub-bullet, not scored
## Attack chains
- [ssrf] i.py:1
"""


def test_v2_scores_only_labelled_primary_cites():
    rows, unm, oov = A.parse_report_v2(V2, "fx")
    assert key(rows) == {("a.py", 3, "route_inventory"), ("a.py", 10, "missing_authn"), ("c.py", 5, "missing_object_check"),
                         ("d.py", 7, "pii_log")}  # b.py evidence cite, sub-bullet, attack chain, out-of-vocab: none scored
    assert [o["label"] for o in oov] == ["hardcoded-secret", "xss"]
    assert [u["text"][:8] for u in unm] == ["no line ", "no label"] and all(u["line"] == 0 for u in unm)


def test_v2_label_map_covers_every_class():
    assert set(A.LABEL_CLASS.values()) == set(A.R.CLASSES)


def test_v2_is_arm_b_default_and_v1_stays_callable():
    rep = "## Findings\n- [other] a.js:1 odd\n- [rate-limit] a.js:2\n"
    assert len(A.parse_report(rep, "fx")) == 2 and A.parse_report_v2(rep, "fx")[0][0]["class"] == "rate_limit"
    tmp, rows, unm, errs = go([INIT, USE, RL, result(rep)], n=1, parser=A.parse_report_v2)
    assert key(rows) == {("a.js", 2, "rate_limit")} and json.load(open(tmp / "out" / "out_of_vocab.json"))[0]["label"] == "other"
    assert A.run.__defaults__[-1] is A.parse_report_v2


def test_v2_numbered_top_level_items():
    t = "## Findings\n1. [ssrf] a.py:3 high: x\n2) [csrf] b.py:4\n3. no label c.py:5\n   1. [tls-off] d.py:6 nested\n"
    rows, unm, oov = A.parse_report_v2(t, "fx")
    assert key(rows) == {("a.py", 3, "ssrf"), ("b.py", 4, "csrf")} and len(unm) == 1 and not oov


if __name__ == "__main__":
    n = 0
    for k, f in list(globals().items()):
        if k.startswith("test_"):
            f(); n += 1
    print("Tests: %d/%d" % (n, n))
