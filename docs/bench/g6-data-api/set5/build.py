#!/usr/bin/env python3
"""Build the G6 set5 fixtures (six new stacks).

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
route line with matching protection, a /web gate does not read the session cookie, or a
Rails action is missing from config/routes.rb.
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
    "quarry-nest": ("src/auth.ts", r"req\.cookies\??\.sid|cookies\??\.\[?'?sid"),
    "pylon-koa": ("src/auth.js", r"ctx\.cookies\.get\('sid'\)"),
    "harrow-actix": ("src/auth.rs", r'impl FromRequest for CookieAuth[\s\S]*?req\.cookie\("sid"\)'),
    "sluice-chi": ("auth.go", r'func sidOf[\s\S]*?req\.Cookie\("sid"\)'),
    "mantle-symfony": ("src/EventSubscriber/RouteGuard.php", r"cookies->get\('sid'"),
    "trellis-quarkus": ("src/main/java/app/trellis/CookieFilter.java", r'getCookies\(\)\.get\("sid"\)'),
}
NEW = ("rate_limit", "csrf", "cookie_flags", "pii_log", "pii_data", "prompt_injection")
# per-part size floors (positives, decoys) across all apps, with margin over the part minimums
MIN = {**{c: (12, 8) for c in NEW}}
MIN_ROUTES = (30, 30)
MIN_OUTBOUND = (30, 15)
OUTBOUND = ("ssrf", "no_timeout", "tls_off", "secret_in_url", "secret_in_log")
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
    rb = app / "config" / "routes.rb"
    if rb.exists():
        text = rb.read_text()
        for r in routes:
            src = (app / r["file"]).read_text().split("\n")[r["line"] - 1]
            m = re.search(r"def (\w+)", src)
            assert not m or m.group(1) in text, r


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
    n = lambda cs, k: sum(t["class"] in cs and t["kind"] == k for t in all_truth)
    for name, cs, floor in (("routes", ROUTE_CLASSES, MIN_ROUTES), ("outbound", OUTBOUND, MIN_OUTBOUND),
                            *((c, (c,), MIN[c]) for c in NEW)):
        assert (n(cs, "positive"), n(cs, "decoy")) >= floor, (name, n(cs, "positive"), n(cs, "decoy"))
    truth_path = Path(a.truth)
    truth_path.write_text(json.dumps(all_truth, indent=1) + "\n")
    (truth_path.parent / "routes.json").write_text(json.dumps(inventory, indent=1) + "\n")
    print(f"truth rows {len(all_truth)}, routes {sum(map(len, inventory.values()))}")


if __name__ == "__main__":
    sys.exit(main())
