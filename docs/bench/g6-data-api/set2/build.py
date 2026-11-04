#!/usr/bin/env python3
"""Build the G6 set2 fixtures (part A plus part iii).

Usage: build.py TARGET --truth FILE

Copies each app under src/ into TARGET/<fixture> as its own git repo with the
answer-key markers (`@@R ...` route, `@@T ...` truth) stripped, then writes the
truth rows to FILE and the full route inventory to routes.json beside FILE.
Marker grammar, after `@@`, segments split on " ; ":
  R METHOD PATH PROTECTED(0|1)   route inventory entry (line = the marked line)
  T KIND CLASS NOTE...           truth row, KIND positive|decoy
Side effects: creates TARGET/<fixture> dirs and runs git there (TARGET must not
already hold a fixture repo). Fails (assert) if a marker is malformed, a
positive and a decoy sit < 7 lines apart, a route-class truth row is not on a
route line with matching protection, or a Django handler is missing from urls.py.
"""
import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src"
STRIP = re.compile(r"\s*(?:(?:#|//)\s*)?@@.*$")
ROUTE_CLASSES = {"missing_authn", "missing_authz", "missing_object_check"}
MIN_GAP = 7
# app -> (file holding the /web gate, regex proving it reads the session cookie)
WEB_GATE = {
    "booking-express": ("sessions.js", r"function webGate[\s\S]*?req\.cookies\.sid"),
    "gallery-next": ("lib/session.ts", r"async function webSession[\s\S]*?cookies\(\)\)\.get\('sid'\)"),
    "roster-flask": ("auth.py", r'def cookie_login[\s\S]*?request\.cookies\.get\("sid"'),
    "survey-django": ("surveys/access.py", r'def web_member[\s\S]*?request\.session\.get\("uid"\)'),
    "library-spring": ("src/main/java/example/library/SessionInterceptor.java", r"getSession\(false\)"),
    "garage-go": ("main.go", r'func cookieAuth[\s\S]*?r\.Cookie\("sid"\)'),
}
NEW = ("rate_limit", "csrf", "cookie_flags", "pii_log", "pii_data", "prompt_injection")
# (class, kind) -> exact truth-row count across all apps
EXPECT = {
    ("missing_authn", "positive"): 12, ("missing_authn", "decoy"): 6,
    ("missing_authz", "positive"): 6, ("missing_authz", "decoy"): 12,
    ("missing_object_check", "positive"): 12, ("missing_object_check", "decoy"): 12,
    ("ssrf", "positive"): 6, ("ssrf", "decoy"): 6,
    ("no_timeout", "positive"): 6, ("tls_off", "positive"): 6,
    ("secret_in_url", "positive"): 6, ("secret_in_url", "decoy"): 6,
    ("secret_in_log", "positive"): 6, ("secret_in_log", "decoy"): 3,
    **{(c, k): n for c in NEW for k, n in (("positive", 12), ("decoy", 8))},
}
GIT_ENV = {
    "GIT_AUTHOR_NAME": "Bench Author",
    "GIT_AUTHOR_EMAIL": "bench@example.com",
    "GIT_AUTHOR_DATE": "2026-11-03T00:00:00+00:00",
}
GIT_ENV.update(
    GIT_COMMITTER_NAME=GIT_ENV["GIT_AUTHOR_NAME"],
    GIT_COMMITTER_EMAIL=GIT_ENV["GIT_AUTHOR_EMAIL"],
    GIT_COMMITTER_DATE=GIT_ENV["GIT_AUTHOR_DATE"],
)


def build_app(app: Path, target: Path):
    out = target / app.name
    truth, routes = [], []
    for f in sorted(p for p in app.rglob("*") if p.is_file()):
        rel = f.relative_to(app).as_posix()
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for n, line in enumerate(f.read_text().split("\n"), 1):
            if "@@" in line:
                body = line.split("@@", 1)[1]
                for seg in body.split(" ; "):
                    kind, _, rest = seg.strip().partition(" ")
                    if kind == "R":
                        m, p, prot, *flag = rest.split(" ")
                        assert prot in ("0", "1") and flag in ([], ["public"]), (rel, n)
                        routes.append(dict(method=m, path=p, file=rel, line=n, protected=prot == "1", **({"public": True} if flag else {})))
                    elif kind == "T":
                        k, c, note = rest.split(" ", 2)
                        assert k in ("positive", "decoy"), (rel, n)
                        truth.append({"fixture": app.name, "file": rel, "line": n, "kind": k, "class": c, "note": note})
                    else:
                        raise AssertionError(f"bad marker {rel}:{n}")
                line = STRIP.sub("", line)
            lines.append(line)
        dest.write_text("\n".join(lines))
    return out, truth, routes


def check(app: Path, truth, routes):
    for a in truth:
        for b in truth:
            if a["kind"] == "positive" and b["kind"] == "decoy" and a["file"] == b["file"]:
                assert abs(a["line"] - b["line"]) >= MIN_GAP, (app.name, a["file"], a["line"], b["line"])
    rkeys = {(r["file"], r["line"]): r for r in routes}
    for t in truth:
        if t["class"] in ROUTE_CLASSES:
            r = rkeys[(t["file"], t["line"])]
            assert r["protected"] == (t["kind"] == "decoy"), t
    # reachability: a file holding truth rows is a route file, or another file of the app references its module
    srcs = {f: f.read_text() for f in app.rglob("*") if f.is_file()}
    for rel in {t["file"] for t in truth}:
        stem = Path(rel).stem
        if stem.lower().endswith("extras"):
            hit = "@RestController" in srcs[app / rel] if rel.endswith(".java") else any(
                re.search("extras", txt, re.I) for f, txt in srcs.items() if f != app / rel and f.suffix != ".json")
            assert hit, ("unreachable", app.name, rel)
        else:
            assert any(r["file"] == rel for r in routes), ("no route in", app.name, rel)
    # csrf / session-cookie rows sit on a /web route gated by reading the session cookie, never an Authorization header
    web = [r for r in routes if r["path"].startswith("/web/ext/")]
    assert len(web) == sum(t["class"] in ("csrf", "cookie_flags") for t in truth), app.name
    assert all(r["protected"] and "public" not in r for r in web), app.name
    f, rx = WEB_GATE[app.name]
    assert re.search(rx, (app / f).read_text()), ("web gate does not read the session cookie", app.name)
    new = [(r["method"], r["path"]) for r in routes if r["path"].startswith(("/api/ext/", "/auth/"))]
    assert len(set(new)) == len(new), app.name
    urls = app / "desk" / "urls.py"
    if urls.exists():
        text = urls.read_text()
        for r in routes:
            src = (app / r["file"]).read_text().split("\n")[r["line"] - 1]
            assert re.search(r"def (\w+)\(", src).group(1) in text, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("target")
    ap.add_argument("--truth", required=True)
    a = ap.parse_args()
    target = Path(a.target).resolve()
    all_truth, inventory = [], {}
    for app in sorted(p for p in SRC.iterdir() if p.is_dir()):
        out, truth, routes = build_app(app, target)
        check(app, truth, routes)
        all_truth += truth
        inventory[app.name] = routes
        env = {**os.environ, **GIT_ENV}
        for cmd in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-q", "-m", f"{app.name} fixture"]):
            subprocess.run(["git", *cmd], cwd=out, env=env, check=True)
    got = {}
    for t in all_truth:
        got[(t["class"], t["kind"])] = got.get((t["class"], t["kind"]), 0) + 1
    assert got == EXPECT, (got, EXPECT)
    for c in NEW:  # every new class spans all six apps: 2 positives, 1-2 decoys each
        for k in ("positive", "decoy"):
            for app in inventory:
                n = sum(t["fixture"] == app and t["class"] == c and t["kind"] == k for t in all_truth)
                assert n in ((1, 2) if k == "decoy" else (2,)), (app, c, k, n)
    truth_path = Path(a.truth)
    truth_path.write_text(json.dumps(all_truth, indent=1) + "\n")
    (truth_path.parent / "routes.json").write_text(json.dumps(inventory, indent=1) + "\n")
    print(f"truth rows {len(all_truth)}, routes {sum(map(len, inventory.values()))}")


if __name__ == "__main__":
    sys.exit(main())
