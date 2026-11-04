#!/usr/bin/env python3
"""G6 scorer: data/API-call detection on set1 (blind truth written by another author; never edited here).

Usage: run_and_score.py [--out DIR] [--detector REPO] [--set DIR] [--rows FILE]   (DIR under this folder, default set1)
  Arm (a), default: builds set1/build.py into a $TMPDIR target, runs `review_checks.sh --repo FIXTURE --full` per
  fixture (same invocation as docs/bench/g10-iac/run_and_score.py, branch lane/g10-set), parses stdout rows into (file, line, tool, rule),
  maps each row to a G6 class (RULE_CLASS below), scores.
  Arm (b), --rows FILE: FILE is a JSON list of agentic report rows {"file", "line", "class"[, "fixture"]} (class in the
  truth vocabulary; "fixture" optional but needed when two fixtures share a path). No detector runs; the same
  scoring code applies. A row with class "route_inventory" is an inventory claim, not a finding.
  Writes results-<UTC>/score.json (refuses an existing --out). The run is the ONE scored attempt: the self-test
  (test_run_and_score.py) uses synthetic truth only and never touches set1.

PARTS (gate frozen in security-ready-1103/PREREGISTERED.md, G6):
  routes    truth classes missing_authn, missing_authz, missing_object_check   need 30 pos + 30 decoy  recall>=0.85 prec>=0.80
  outbound  tls_off, ssrf, no_timeout, secret_in_url, secret_in_log            need 30 pos + 15 decoy  recall>=0.85 prec>=0.80
  rate_limit, csrf, cookie_flags, pii_log, pii_data, prompt_injection          need 12 pos +  8 decoy  recall>=0.75 prec>=0.75
  (each of the six is its own part). A part whose truth set is short of the need is "size_ok": false and fails.

SCORING RULES (fixed before any scored run):
  1. Part of a class: the three route classes are one part "routes", the five outbound classes one part "outbound",
     every other class its own part. A row counts toward a truth row only if both are in the same part (inside a part
     the exact class does not matter: a missing_authn row hits a missing_authz truth row).
  2. Positive hit: a row of the same part on the same file (and same fixture, if the row names one) within +-3 lines of
     the truth line; a file-level row (line <= 0) matches any truth row of that part on that file.
  3. Decoy false positive: a row of the same part within +-3 lines of a decoy truth row (file-level rows included).
     One FP per distinct decoy flagged. Rows that match no truth row are ignored: only truth rows count.
  4. `not-checked` rows are never findings. Rows from a tool listed under "NOT RUN:" on stderr are ignored (never a
     hit), so the positives they would have covered are misses. Rows whose tool/rule/text match no RULE_CLASS
     pattern are ignored (arm a only).
  5. recall = hits/positives; precision = hits/(hits+FP) (1.0 if hits+FP == 0); Wilson 95% lower bounds reported.
     A rate passes only if point >= threshold AND Wilson lower bound >= threshold - 0.2. A part passes if size_ok and
     both rates pass. G6 PASS = all 8 parts pass; per-part and per-class verdicts are in score.json.
  6. Route-inventory completeness (feeds G9, not a G6 gate): arm a runs route_auth_map.py per fixture and compares its
     handler count to routes.json (count only, capped per fixture); arm b matches "route_inventory" rows to routes.json
     entries by file +-3 lines. found/listed is reported.
  7. Unlisted findings (PREREGISTERED: a finding outside the truth set is checked by the adjudicator; if verified it
     counts as a true positive and joins the truth set). A row of a part that matches no truth row of that part is
     "unmatched" and listed per part in score.json. --adjudicated FILE (JSON list of {fixture, file, line, class,
     verdict: "tp"|"fp"}) settles them: a tp is added to the part's positives and hits, an fp counts as an FP. Any
     unmatched row without a verdict makes that part "pending_adjudication": true and its pass false.
  8. Paths are normalized on rows and truth: backslashes -> "/", leading "./" and the fixture-name prefix stripped.
     score.json "warnings" notes a run where no row path matches any truth file. A file-level row (line <= 0) credits
     at most ONE positive (the first unmatched one in truth order, after line-located rows are settled) but flags
     every decoy of its part in that file. A line like "12-14" is read as 12. NOT RUN is per fixture, and only a
     whole-tool entry ("semgrep (why)") drops that tool's rows; "semgrep p/x (why)" names a pack and drops nothing.
  9. An invalid run is loud: score.json "errors" lists every fixture that timed out, printed non-JSON, or exited other
     than 0, and forces pass false. A rate over n == 0 reports point 1.0 and never passes.
  A build failure aborts before scoring.
"""
import datetime, json, math, os, re, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = ".claude/skills/deep-code-review/scripts"
RC = SCRIPTS + "/review_checks.sh"
WINDOW = 3
OK_EXIT = (0,)
ROUTE = ("missing_authn", "missing_authz", "missing_object_check")
OUTBOUND = ("tls_off", "ssrf", "no_timeout", "secret_in_url", "secret_in_log")
SIX = ("rate_limit", "csrf", "cookie_flags", "pii_log", "pii_data", "prompt_injection")
CLASSES = ROUTE + OUTBOUND + SIX
# part -> (positives, decoys, recall thr, precision thr)
GATE = {"routes": (30, 30, .85, .80), "outbound": (30, 15, .85, .80), **{c: (12, 8, .75, .75) for c in SIX}}
LOG = r"\blog(s|ged|ging|ger)?\b"
# Arm a: first matching pattern on "tool rule text" (lowercased) gives the class; none -> row ignored.
RULE_CLASS = [
    (r"route-auth|missing-auth|tenant-scope", "missing_authn"),
    (r"attempt-limit|rate.?limit|throttl", "rate_limit"),
    (r"csrf|xsrf", "csrf"),
    (r"httponly|samesite|cookie.*(secure|flag)|secure.?cookie|session.?cookie", "cookie_flags"),
    (r"committed-personal-data", "pii_data"),
    (r"pii.*%s|%s.*(email|ssn|personal|pii)" % (LOG, LOG), "pii_log"),
    (r"pii.*(data|fixture|seed|dump)", "pii_data"),
    (r"prompt.?inj|llm.*(inject|untrusted)", "prompt_injection"),
    (r"verify\s*=\s*false|insecureskipverify|tls.*(verif|off|disabl)|reject.?unauthorized|ssl.*(verif|disabl)|cert.*(verif|disabl)", "tls_off"),
    (r"ssrf|server-side.?request", "ssrf"),
    (r"timeout", "no_timeout"),
    (r"(secret|token|key|password).*(url|query)|(url|query).*(secret|token|key|password)", "secret_in_url"),
    (r"(secret|token|key|password).*%s|%s.*(secret|token|key|password)" % (LOG, LOG), "secret_in_log"),
]


def wilson_lower(k, n, z=1.959964):
    """Wilson score 95% lower bound for k successes of n; 0.0 when n == 0."""
    if n == 0:
        return 0.0
    p = k / n
    d = 1 + z * z / n
    return max(0.0, (p + z * z / (2 * n) - z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))) / d)


def part_of(cls):
    """Class -> part name (rule 1)."""
    return "routes" if cls in ROUTE else "outbound" if cls in OUTBOUND else cls


def norm(path, fixture=None):
    """Rule 8: backslashes -> '/', strip leading './' and the '<fixture>/' prefix."""
    p = str(path).replace("\\", "/")
    while p.startswith("./"):
        p = p[2:]
    return p[len(fixture) + 1:] if fixture and p.startswith(fixture + "/") else p


def to_line(x):
    """Line cell -> int; '12-14' -> 12; missing/unparseable -> 0 (file-level)."""
    m = re.match(r"\d+", str(x or "").strip())
    return int(m[0]) if m else 0


def classify(tool, rule, text):
    """Arm a: row -> truth-vocabulary class, or None when no RULE_CLASS pattern matches."""
    hay = ("%s %s %s" % (tool, rule, text)).lower()
    return next((c for rx, c in RULE_CLASS if re.search(rx, hay)), None)


def parse_rows(stdout):
    """review_checks stdout JSON -> deduped [(file, line, tool, class)]; unmapped and not-checked rows dropped; bad JSON -> []."""
    try:
        rows = json.loads(stdout)
    except ValueError:
        return []
    out = []
    for r in rows:
        tool, rule = r.get("tool", ""), r.get("rule", "")
        cls = None if rule == "not-checked" else classify(tool, rule, r.get("text", r.get("message", "")))
        k = (r.get("file", ""), to_line(r.get("line")), tool, cls)
        if cls and k not in out:
            out.append(k)
    return out


def parse_not_run(stderr):
    """'NOT RUN: a (why), b p/x (why)' -> {'a'}: only an entry that is a bare tool name (rule 8); 'b p/x' is a pack."""
    m = re.search(r"NOT RUN: (.*)", stderr)
    if not m or m[1].strip() == "none":
        return set()
    names = [e.split("(")[0].split() for e in re.split(r"\)\s*,\s*", m[1])]
    return {n[0] for n in names if len(n) == 1}


def fixture_rows(fx, stdout, stderr):
    """One fixture's review_checks output -> rows [(file, line, tool, class, fx)] minus that fixture's own NOT RUN tools."""
    nr = parse_not_run(stderr)
    return [r + (fx,) for r in parse_rows(stdout) if r[2] not in nr]


def run_errors(fx, stdout, status):
    """Rule 9: [error strings] for a timeout, non-JSON-list stdout or an exit outside OK_EXIT."""
    if status == "timeout":
        return ["%s: timeout" % fx]
    errs = [] if status in OK_EXIT else ["%s: exit %s" % (fx, status)]
    try:
        ok = isinstance(json.loads(stdout), list)
    except ValueError:
        ok = False
    return errs + ([] if ok else ["%s: stdout is not a JSON list" % fx])


def _cls(c):
    if c not in CLASSES + ("route_inventory",):
        raise ValueError("unknown class %r" % (c,))
    return c


def load_rows(path):
    """Arm b: JSON list of {file,line,class[,fixture]} -> [(file, line, 'agent', class, fixture|None)]; bad class/row raises ValueError."""
    return [(r["file"], to_line(r.get("line")), "agent", _cls(r["class"]), r.get("fixture")) for r in json.load(open(path))]


def load_adjudicated(path):
    """--adjudicated FILE -> [{fixture, file, line, class, verdict}] (file/line normalized); bad verdict/class raises ValueError."""
    out = []
    for r in json.load(open(path)):
        if r["verdict"] not in ("tp", "fp"):
            raise ValueError("verdict must be tp|fp: %r" % (r["verdict"],))
        out.append({"fixture": r.get("fixture"), "file": norm(r["file"], r.get("fixture")), "line": to_line(r.get("line")),
                    "class": _cls(r["class"]), "verdict": r["verdict"]})
    return out


def hit(row, t):
    """Rules 1-3: same part, same file (and fixture if the row names one), within the window or file-level."""
    return (part_of(row[3]) == part_of(t["class"]) and row[0] == t["file"] and list(row[4:5]) in ([], [None], [t["fixture"]])
            and (row[1] <= 0 or abs(row[1] - t["line"]) <= WINDOW))


def verdict(k, n, thr):
    """Rule 5: point >= thr and Wilson LB >= thr - 0.2; n == 0 reports point 1.0 and never passes (rule 9)."""
    p = k / n if n else 1.0
    lb = wilson_lower(k, n)
    return {"k": k, "n": n, "point": p, "wilson95_lower": lb, "pass": n > 0 and p >= thr and lb >= thr - 0.2}


def adjudged(adjudicated, fx, f, ln, part):
    """Verdict ('tp'|'fp'|None) for an unmatched row; an adjudication without a fixture, or a row without one, matches any."""
    return next((a["verdict"] for a in adjudicated if a["file"] == f and a["line"] == ln and part_of(a["class"]) == part
                 and (fx is None or a["fixture"] in (fx, None))), None)


def score(truth, rows, adjudicated=()):
    """truth: set1 rows (all fixtures); rows: [(file, line, tool, class[, fixture])] already minus NOT RUN tools;
    adjudicated: load_adjudicated output. -> (parts {part: verdict dict}, warnings [str]). 'route_inventory' rows are dropped."""
    truth = [dict(t, file=norm(t["file"], t["fixture"])) for t in truth]
    rows = [(norm(r[0], r[4] if len(r) > 4 else None),) + tuple(r[1:]) for r in rows if r[3] != "route_inventory"]
    tfiles = {t["file"] for t in truth}
    warns = ["no row path matches any truth file"] if rows and not any(r[0] in tfiles for r in rows) else []
    res = {}
    for part, (npos, ndec, rthr, pthr) in GATE.items():
        prs = [r for r in rows if part_of(r[3]) == part]
        ts = [t for t in truth if part_of(t["class"]) == part]
        pos, dec = [t for t in ts if t["kind"] == "positive"], [t for t in ts if t["kind"] == "decoy"]
        got = {i for i, t in enumerate(pos) if any(r[1] > 0 and hit(r, t) for r in prs)}
        for r in prs:  # file-level rows credit one still-unmatched positive each
            if r[1] <= 0:
                i = next((i for i, t in enumerate(pos) if i not in got and hit(r, t)), None)
                if i is not None:
                    got.add(i)
        fps = [t for t in dec if any(hit(r, t) for r in prs)]
        unmatched = sorted({(r[4] if len(r) > 4 else None, r[0], r[1]) for r in prs if not any(hit(r, t) for t in ts)},
                           key=lambda u: (str(u[0]), u[1], u[2]))
        tp = fp = 0
        pending = []
        for fx, f, ln in unmatched:
            v = adjudged(adjudicated, fx, f, ln, part)
            if v == "tp":
                tp += 1
            elif v == "fp":
                fp += 1
            else:
                pending.append([fx, f, ln])
        rec = verdict(len(got) + tp, len(pos) + tp, rthr)
        prec = verdict(len(got) + tp, len(got) + tp + len(fps) + fp, pthr)
        size_ok = len(pos) + tp >= npos and len(dec) >= ndec
        res[part] = {"positives": len(pos) + tp, "decoys": len(dec), "size_ok": size_ok, "recall": rec, "precision": prec,
                     "fp_decoy": [[t["fixture"], t["file"], t["line"]] for t in fps], "adjudicated_tp": tp, "adjudicated_fp": fp,
                     "unmatched": [list(u) for u in unmatched], "pending_adjudication": bool(pending),
                     "missed": [[t["fixture"], t["file"], t["line"]] for i, t in enumerate(pos) if i not in got],
                     "pass": size_ok and rec["pass"] and prec["pass"] and not pending}
    return res, warns


def inventory_rows(routes, claims):
    """Arm b: routes.json {fixture: [{file,line,...}]} vs route_inventory claims -> {found, listed, basis}."""
    found = sum(any(c[3] == "route_inventory" and norm(c[0], fx) == norm(r["file"]) and abs(c[1] - r["line"]) <= WINDOW
                    and list(c[4:5]) in ([], [None], [fx]) for c in claims) for fx, rs in routes.items() for r in rs)
    return {"found": found, "listed": sum(map(len, routes.values())), "basis": "route_inventory rows"}


def inventory_counts(routes, handlers):
    """Arm a: routes.json vs {fixture: route_auth_map handler count}; per-fixture capped count. -> {found, listed, basis}."""
    return {"found": sum(min(handlers.get(fx, 0), len(rs)) for fx, rs in routes.items()),
            "listed": sum(map(len, routes.values())), "basis": "route_auth_map handler count (count only)"}


def sh(cmd, cwd=None):
    """-> (stdout, stderr, status): status is the exit code, or "timeout" (stdout/stderr empty)."""
    try:
        p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=900)
    except subprocess.TimeoutExpired:
        return "", "", "timeout"
    return p.stdout, p.stderr, p.returncode


def run(out, detector, sset="set1", rows_file=None, adj_file=None):
    if os.path.exists(out):  # refuses to overwrite an earlier run
        raise FileExistsError(out)
    claims = load_rows(rows_file) if rows_file else None
    adj = load_adjudicated(adj_file) if adj_file else []
    os.makedirs(out)
    errors, rows, handlers, statuses = [], [], {}, {}
    with tempfile.TemporaryDirectory() as tmp:
        target, tf = os.path.join(tmp, sset), os.path.join(tmp, "truth.json")
        _, e, st = sh([sys.executable, os.path.join(HERE, sset, "build.py"), target, "--truth", tf])
        if st != 0:
            sys.exit("build.py failed (%s): %s" % (st, e.strip()[-500:]))
        truth, routes = json.load(open(tf)), json.load(open(os.path.join(tmp, "routes.json")))
        if claims is not None:
            rows = claims
        else:
            for fx in sorted({t["fixture"] for t in truth}):
                repo = os.path.join(target, fx)
                o, e, st = sh(["bash", os.path.join(detector, RC), "--repo", repo, "--full"], repo)
                errs = run_errors(fx, o, st)
                errors += errs
                statuses[fx] = {"exit": st, "timeout": st == "timeout", "json_ok": not any("JSON" in x for x in errs)}
                open(os.path.join(out, fx + ".json"), "w").write(o)
                open(os.path.join(out, fx + ".stderr"), "w").write(e)
                rows += fixture_rows(fx, o, e)
                ho, _, _ = sh([sys.executable, "-I", os.path.join(detector, SCRIPTS, "route_auth_map.py"), repo])
                try:
                    handlers[fx] = int(json.loads(ho[ho.index("{"):]).get("handlers", 0))
                except ValueError:  # no JSON line: count unknown, treated as 0
                    handlers[fx] = 0
    parts, warns = score(truth, rows, adj)
    inv = inventory_rows(routes, rows) if claims is not None else inventory_counts(routes, handlers)
    res = {"arm": "rows" if claims is not None else "deterministic",
           "pass": not errors and all(p["pass"] for p in parts.values()),
           "parts": parts, "route_inventory": inv, "errors": errors, "warnings": warns, "fixture_status": statuses}
    json.dump(res, open(os.path.join(out, "score.json"), "w"), indent=1)
    print(json.dumps({"arm": res["arm"], "pass": res["pass"], "errors": errors, "warnings": warns, "route_inventory": inv,
                      "parts": {k: v["pass"] for k, v in parts.items()},
                      "pending": [k for k, v in parts.items() if v["pending_adjudication"]]}))
    return res["pass"]


if __name__ == "__main__":
    a = sys.argv[1:]
    # unknown flags (e.g. --help) must not start the ONE scored attempt
    bad = [x for x in a if x.startswith("-") and x not in ("--out", "--detector", "--set", "--rows", "--adjudicated")]
    if bad:
        sys.exit(__doc__.split("PARTS")[0] + "unknown argument(s): %s" % bad)

    def opt(f, d):
        if f not in a:
            return d
        i = a.index(f) + 1
        if i >= len(a):
            sys.exit("%s needs a value" % f)
        return a[i]
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    det = os.path.abspath(opt("--detector", os.path.join(HERE, "..", "..", "..")))
    sys.exit(0 if run(opt("--out", os.path.join(HERE, "results-" + stamp)), det, opt("--set", "set1"),
                      opt("--rows", None), opt("--adjudicated", None)) else 1)
