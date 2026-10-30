#!/usr/bin/env python3
"""pipeline_hub.py: one entry point that says where a delivery pipeline loses time, and names the job to fix.

WHY: `pipeline_profile.py` measures one pipeline in depth (stage map, critical chain, priced fixes). This hub is the
first read: per-workflow p50/p90, the slowest jobs, jobs that run the same check twice, re-run and flake rate per
job, PR lead time, and one recommendation per finding that names the workflow, job or step. It reuses
`pipeline_profile.py` (workflow reader, suite keys, lead metrics) and `gh_rest.py` (TLS fallback); it adds no
analysis engine of its own beyond grouping and percentiles.

TOOLS (hub, not home-grown, where a proven tool fits; `docs/standards-index.md` lists what was fetched):
  gh-workflow-stats  https://github.com/fchimpan/gh-workflow-stats (MIT, `gh extension install fchimpan/gh-workflow-stats`).
                     When installed it supplies the job table (p50 = its median, tail = its max, both over successful runs
                     only; failure rate) for every workflow file. Its JSON shape is read from its source (`parser.Result`); an unreadable or failed
                     run falls back to the gh sample and says so.
  gh API (fallback)  `gh api` through `gh_rest.fallback`, sampling recent completed PR runs, their jobs, the earlier
                     attempts of re-run runs (for per-job flakes) and recent merged PRs. Nothing else is installed.
No tool was found for duplicate-job detection or per-job flake attribution; those two use the repo's workflow files
(`pipeline_profile.parse_workflow` / `commands`) and the earlier run attempts. No DORA tool was wired (one has no
tagged release, the other is a deployed platform, not a command; see the index), so lead time is PR open to merge from
the sampled merged PRs, plus the push-to-merge numbers.

USAGE: pipeline_hub.py [--repo OWNER/NAME] [--root DIR] [--runs 30] [--merges 30] [--data FILE] [--offline]
                       [--no-oss] [--json]
`--data FILE` is a read-write bundle (same keys as `pipeline_profile.py profile --data`, plus `prior`): a rate-limited
run resumes from it and `--offline` re-analyses it without any call. A missing input is shown as n/a, never guessed.

Exit codes: 0 ok, 2 usage, an unreadable or unwritable --data, a --root that is not a checkout of --repo, or no data.
Side effects: `gh api` calls (read-only); `--data` writes that file.
Limits: durations are job wall time (started to completed); a duplicate is the same check command (script and
arguments) in two enforced CI steps (a PR or merge-group gate; a build, install or generate step is never flagged), so a
matrix or OS split also shows up: each recommendation says to check that first. The same script with different
arguments is an advisory (check one covers the other before dropping), never a drop, and is not priced. The API times
steps, not suites: a saving is priced only for a step that runs that one command; for any other step the suite's own
time is unmeasured and the recommendation says to time it locally. Jobs match on workflow and displayed name, with a
matrix suffix ignored. Duplicates are read from the workflow files under --root, so --root must be a checkout of --repo.
A run whose jobs or attempts call fails is named in the notes and its job data stays missing until a later run with
the same --data retries it; a failed runs-list or pulls call stops collection and says so.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gh_rest  # noqa: E402
import pipeline_profile as pp  # noqa: E402

RERUN_FLAG = 0.10  # a workflow re-run in more than this share of runs is called out
LEAD_SHARE = 0.25  # post-green wait above this share of the PR lead time is called out
DUP_FLOOR_S = 5.0  # a duplicate whose dropped copies all cost less than this is listed, not recommended
RED_FLAG = 0.15  # a job red in more than this share of runs (and over a minute long) is called out
CHECK = re.compile(r"test|typecheck|(?<![a-z])(?:lint|check|gate|verify|audit|scan|valid|spec|e2e|unit|cover|fmt|format"
                   r"|vet|clippy|tox|nox)")  # a word start, so `inspect` and `community` are not checks


def is_check(key):
    """True for a suite key that is a check (test, lint, gate, verify...). A build, install or generate step is never a
    duplicate to drop: a later step needs its output. Unknown keys count as not a check (skip rather than guess)."""
    return key.split()[0] in pp._RUN or bool(CHECK.search(key.lower()))


def api_error(err):
    """One line for a failed `gh api` call's stderr: gh's own `<message> (HTTP nnn)` line, else the JSON body's
    "message" (what the curl fallback keeps, after `HTTP nnn:`) with that status, else the last line. Never the bare
    `}` that ends a multi-line body. Blank stderr gives "gh api failed"."""
    err = (err or "").strip() or "gh api failed"
    m = re.search(r"^gh: (.+ \(HTTP \d+\))$", err, re.M)
    if m:
        return m.group(1)[:300]
    m = re.search(r'"message":\s*"((?:[^"\\]|\\.)*)"', err)
    if m:
        st = re.match(r"HTTP (\d+)", err)
        return (m.group(1) + (" (HTTP %s)" % st.group(1) if st else ""))[:300]
    return err.splitlines()[-1][:300]


def gh_get(path, params=None):
    """GET one REST page through bare `gh api` (curl fallback on gh's macOS-sandbox TLS failure) -> parsed JSON.
    A failure raises OSError with `api_error`'s one-line reason."""
    args = ["gh", "api", path + ("?" + urllib.parse.urlencode(params) if params else "")]
    p = subprocess.run(args, capture_output=True, text=True)
    rc, out, err = gh_rest.fallback(args, p.returncode, p.stdout, p.stderr)
    if rc:
        raise OSError(api_error(err))
    return json.loads(out)


def collect(repo, bundle, n_runs=30, n_pulls=30, get=gh_get):
    """Fill `bundle` {runs, jobs, prior, pulls, limits} from the API, reusing what is there. A failed jobs or attempts
    call skips that run and is recorded once in bundle['limits'] with the run id and the API message (a later run
    with the same --data retries it); a failed runs-list or pulls call stops collection and is recorded there too
    (rerun with the same --data to resume). It never raises."""
    for k, v in (("runs", []), ("jobs", {}), ("prior", {}), ("pulls", [])):
        bundle.setdefault(k, v)
    bundle["limits"] = []
    base = "/repos/%s" % repo
    try:
        if len(bundle["runs"]) < n_runs:
            got = get(base + "/actions/runs", {"per_page": min(n_runs, 100), "status": "completed",
                                               "event": "pull_request"})
            bundle["runs"] = [pp._run_row(r) for r in got.get("workflow_runs", [])][:n_runs]
        for r in bundle["runs"]:
            rid = str(r["id"])
            try:  # one run's endpoint can fail every time (an HTTP 502 on its /jobs): name it, go on to the next run
                if rid not in bundle["jobs"]:
                    got = get("%s/actions/runs/%s/jobs" % (base, rid), {"per_page": 100, "filter": "latest"})
                    bundle["jobs"][rid] = [pp._job_row(j) for j in got.get("jobs", [])]
                for a in range(1, (r.get("run_attempt") or 1)):  # earlier attempts: which job failed before the re-run
                    if "%s/%d" % (rid, a) not in bundle["prior"]:
                        got = get("%s/actions/runs/%s/attempts/%d/jobs" % (base, rid, a), {"per_page": 100})
                        bundle["prior"]["%s/%d" % (rid, a)] = [pp._job_row(j) for j in got.get("jobs", [])]
            except (OSError, ValueError) as e:
                # ponytail: an outage adds one note per remaining run; add a consecutive-failure stop if that shows up
                bundle["limits"].append("run %s skipped, its jobs or attempts call failed: %s" % (rid, e))
        for page in range(1, (n_pulls + 9) // 10 + 1):  # a PR object is large: small pages survive a body-cutting proxy
            if len(bundle["pulls"]) >= n_pulls or bundle.get("pulls_pages", 0) >= page:
                continue
            got = get(base + "/pulls", {"state": "closed", "per_page": 10, "page": page, "sort": "updated",
                                        "direction": "desc"})
            bundle["pulls"] += [{"number": p["number"], "created_at": p.get("created_at"),
                                 "merged_at": p.get("merged_at"), "head_ref": (p.get("head") or {}).get("ref")}
                                for p in got if p.get("merged_at")]
            bundle["pulls_pages"] = page
    except (OSError, ValueError) as e:
        bundle["limits"].append("collection stopped: %s. Re-run with the same --data file to resume." % e)
    return bundle


# --------------------------------------------------------------------------- analysis (pure functions)
def workflow_stats(bundle):
    """Per workflow (run name): runs, p50/p90 wall seconds (latest attempt start to last update), failed share,
    re-run share, and re-runs that ended green (flake suspects). Cancelled and skipped runs are excluded."""
    by = {}
    for r in bundle.get("runs") or []:
        if r.get("conclusion") in ("success", "failure", "timed_out"):
            by.setdefault(r["name"], []).append(r)
    out = []
    for name, rs in by.items():
        d = [pp.span(r.get("run_started_at"), r.get("updated_at")) for r in rs]
        re_ = [r for r in rs if (r.get("run_attempt") or 1) > 1]
        out.append({"workflow": name, "runs": len(rs), "p50_s": pp.med(d), "p90_s": pp.p90(d),
                    "fail_rate": sum(r["conclusion"] != "success" for r in rs) / len(rs),
                    "rerun_rate": len(re_) / len(rs), "flake_suspects": sum(r["conclusion"] == "success" for r in re_)})
    return sorted(out, key=lambda w: -(w["p50_s"] or 0))


def job_stats(bundle):
    """Per (workflow, job): runs, p50/p90 seconds, failed share, flakes (failed in an earlier attempt, green in the
    latest one; once per run; None when a re-run's earlier attempts were not fetched and none is confirmed) and the
    job's longest step by median. Slowest p50 first."""
    wf = {str(r["id"]): r["name"] for r in bundle.get("runs") or []}
    prior = bundle.get("prior") or {}
    gap = {str(r["id"]) for r in bundle.get("runs") or []  # re-runs whose earlier attempts were never fetched
           if any("%s/%d" % (r["id"], n) not in prior for n in range(1, (r.get("run_attempt") or 1)))}
    acc = {}

    def slot(w, name):
        return acc.setdefault((w, name), {"d": [], "fail": 0, "flakes": set(), "steps": {}, "gap": False})

    for rid, jobs in (bundle.get("jobs") or {}).items():
        for j in jobs if rid in wf else []:
            if j.get("conclusion") not in ("success", "failure", "timed_out"):
                continue
            a = slot(wf[rid], j["name"])
            a["gap"] |= rid in gap
            a["d"].append(pp.span(j.get("started_at"), j.get("completed_at")))
            a["fail"] += j["conclusion"] != "success"
            for s in j.get("steps") or []:
                if s.get("conclusion") != "skipped":
                    a["steps"].setdefault(s["name"], []).append(pp.span(s.get("started_at"), s.get("completed_at")))
    for key, jobs in prior.items():
        rid = key.split("/")[0]
        final = {j["name"]: j.get("conclusion") for j in (bundle.get("jobs") or {}).get(rid, [])}
        for j in jobs if rid in wf else []:
            if j.get("conclusion") in ("failure", "timed_out") and final.get(j["name"]) == "success":
                slot(wf[rid], j["name"])["flakes"].add(rid)
    out = []
    for (w, name), a in acc.items():
        top = max(((pp.med(v), s) for s, v in a["steps"].items() if pp.med(v) is not None), default=(None, None))
        out.append({"workflow": w, "job": name, "runs": len(a["d"]), "p50_s": pp.med(a["d"]), "p90_s": pp.p90(a["d"]),
                    "tail": "p90", "tail_s": pp.p90(a["d"]), "fail_rate": a["fail"] / len(a["d"]) if a["d"] else None,
                    "flakes": len(a["flakes"]) or (None if a["gap"] else 0), "top_step": top[1], "top_step_s": top[0],
                    "step_p50": {s: pp.med(v) for s, v in a["steps"].items()}})
    return sorted(out, key=lambda j: -(j["p50_s"] or 0))


def oss_jobs(repo, root, run=subprocess.run):
    """Job rows from the gh-workflow-stats extension for every workflow file under `root`.
    -> (rows, None) or (None, reason). Reads its documented JSON: workflow_jobs_stats_summary[].name,
    .total_runs_count, .rate.failure_rate (0..1), .execution_duration_stats.med / .max (seconds)."""
    owner, name = repo.split("/", 1)
    wdir = os.path.join(root, ".github", "workflows")
    rows = []
    for fn in sorted(os.listdir(wdir)) if os.path.isdir(wdir) else []:
        if not fn.endswith((".yml", ".yaml")):
            continue
        try:
            p = run(["gh", "workflow-stats", "jobs", "-o", owner, "-r", name, "-f", fn, "-e", "pull_request",
                     "-s", "completed", "--json"], capture_output=True, text=True)
        except OSError as e:
            return None, str(e)
        if p.returncode:
            return None, "gh workflow-stats unavailable: " + ((p.stderr or "").strip().splitlines() or ["failed"])[0][:120]
        try:
            for j in json.loads(p.stdout)["workflow_jobs_stats_summary"] or []:
                s = j["execution_duration_stats"]
                rows.append({"workflow": fn, "job": j["name"], "runs": j["total_runs_count"], "p50_s": s["med"],
                             "p90_s": None, "tail": "max", "tail_s": s["max"], "fail_rate": j["rate"]["failure_rate"],
                             "flakes": None, "top_step": None, "top_step_s": None, "step_p50": {}})
        except (ValueError, KeyError, TypeError):
            return None, "gh workflow-stats output unreadable"
    return sorted(rows, key=lambda j: -(j["p50_s"] or 0)), None


def dup_jobs(root, jobs):
    """Check suites (suite keys from `pipeline_profile.commands`, `is_check` only) run by two or more enforced CI steps
    (a PR or merge-group gate: a push-to-main run is the post-merge copy, not a duplicate). The same normalized command
    (script and arguments, as `commands` prints it) in two steps is a duplicate (`identical` True): keep the copy in the
    job with the lower p50 (red sooner) and drop the others. A suite whose steps all run it with different arguments is
    only an advisory (`identical` False, `saved_s` None): one may not cover the other. (Beside a repeated command, a
    copy with other arguments is left out: only the repeat is reported.) A step's median prices a copy only when that
    step runs that one command; the API times whole steps, never one suite, so for any other step
    `step_p50_s` is None (unmeasured) rather than an even split of the step; `saved_s` sums the measured copies (None
    when none is). Job rows match on workflow and job name."""
    wdir = os.path.join(root, ".github", "workflows")
    seen, ncmd, names = {}, {}, {}  # seen: suite key -> normalized command -> {step location}
    for fn in sorted(os.listdir(wdir)) if os.path.isdir(wdir) else []:
        if not fn.endswith((".yml", ".yaml")):
            continue
        text = pp.read(os.path.join(wdir, fn))
        m = re.search(r"^name:[ \t]*(\S.*)$", text, re.M)  # a run is named after the workflow, else its file path
        names[fn] = (pp._unq(m.group(1)), fn) if m else (".github/workflows/" + fn, fn)
        wf = pp.parse_workflow(text)
        for job in wf["jobs"].values():
            for st in job["steps"]:
                if st["run"] and pp._wf_stage(wf, st, job)[1]:
                    loc = (fn, job["name"], pp.step_label(st))
                    for cmd, key, _b in pp.commands(st["run"]):
                        ncmd[loc] = ncmd.get(loc, 0) + 1  # every suite command counts: the step median covers them all
                        if is_check(key):
                            seen.setdefault(key, {}).setdefault(cmd, {})[loc] = 1

    def find(fn, name):
        return [j for j in jobs if j["workflow"] in names[fn]
                and (j["job"] == name or j["job"].startswith(name + " ("))]

    groups = []  # (suite key, identical, {step location}), one per command that repeats
    for key, by_cmd in sorted(seen.items()):
        # no command repeats: the same suite with different arguments in each step is only an advisory
        groups += [(key, True, locs) for locs in by_cmd.values() if len(locs) > 1] or [
            (key, False, dict.fromkeys(loc for locs in by_cmd.values() for loc in locs))]
    out = []
    for key, identical, locs in groups:
        if len(locs) < 2:
            continue
        rows = []
        for fn, job, step in locs:
            m = find(fn, job)
            sec = [s for j in m for s in [j["step_p50"].get(step)] if s is not None and ncmd[(fn, job, step)] == 1]
            rows.append({"workflow_file": fn, "job": job, "step": step,
                         "job_p50_s": max((j["p50_s"] or 0 for j in m), default=None) if m else None,
                         "step_p50_s": max(sec) if sec else None})
        order = sorted(range(len(rows)), key=lambda i: (rows[i]["job_p50_s"] is None, rows[i]["job_p50_s"] or 0, i))
        keep = rows[order[0]]
        drop = [rows[i] for i in order[1:]]
        out.append({"suite": key, "identical": identical, "keep": keep, "drop": drop,
                    "saved_s": sum(r["step_p50_s"] or 0 for r in drop)
                    if identical and any(r["step_p50_s"] for r in drop) else None})
    return out


def lead_stats(bundle):
    """PR open to merge p50/p90 over the sampled merged PRs, plus pipeline_profile's push-to-merge numbers."""
    d = [pp.span(p.get("created_at"), p.get("merged_at")) for p in bundle.get("pulls") or [] if p.get("merged_at")]
    m = pp.lead_metrics(bundle)
    return {"prs": len(d), "open_to_merge_p50_s": pp.med(d), "open_to_merge_p90_s": pp.p90(d),
            "first_push_to_merge_s": m["first_push_to_merge_s"], "post_green_wait_s": m["post_green_wait_s"],
            "merged_per_day": m["merged_per_day"]}


def recommend(wfs, jobs, dups, lead, flake_jobs=None):
    """One recommendation per finding, each naming its job (or workflow / step). -> [{kind, target, text}]."""
    f, rec = pp.fmt, []
    for d in dups:
        k, drops = d["keep"], d["drop"]
        if all(x["step_p50_s"] is not None and x["step_p50_s"] < DUP_FLOOR_S for x in drops):
            continue
        for x in drops:
            if d["identical"]:
                tail = (". Run it once: keep the first, drop the second, unless the copies are a matrix or OS split; %s."
                        % ("saves at most about %s per run (its step's median)" % f(x["step_p50_s"]) if x["step_p50_s"]
                           else "the suite's own time is unmeasured: time it locally to price the saving"))
            else:
                tail = "; same suite, different arguments: check one covers the other before dropping."
            rec.append({"kind": "duplicate-job", "target": x["job"],
                        "text": "suite `%s` runs in job `%s` (step `%s`) and again in job `%s` (step `%s`, %s)%s"
                                % (d["suite"], k["job"], k["step"], x["job"], x["step"], x["workflow_file"], tail)})
    if jobs:
        j = jobs[0]
        rec.append({"kind": "slowest-job", "target": j["job"],
                    "text": "job `%s` (%s) is the slowest: p50 %s, %s %s%s. Profile it first with "
                            "`pipeline_profile.py profile`." % (
                                j["job"], j["workflow"], f(j["p50_s"]), j["tail"], f(j["tail_s"]),
                                "; its longest step is `%s` at %s" % (j["top_step"], f(j["top_step_s"]))
                                if j.get("top_step") else "")})
    red = [x for x in jobs if (x["fail_rate"] or 0) > RED_FLAG and (x["p50_s"] or 0) >= 60]
    if red:
        j = max(red, key=lambda x: x["fail_rate"] * x["p50_s"])
        rec.append({"kind": "red-job", "target": j["job"],
                    "text": "job `%s` ends red in %.0f%% of %d runs and runs %s each time. Move its cheapest failing "
                            "check into an earlier, faster job or run it locally before push, so a red stops sooner."
                            % (j["job"], 100 * j["fail_rate"], j["runs"], f(j["p50_s"]))})
    for j in sorted((x for x in flake_jobs or jobs if x.get("flakes")), key=lambda x: -x["flakes"]):
        rec.append({"kind": "flaky-job", "target": j["job"],
                    "text": "job `%s` failed and then passed on a re-run in %d of %d sampled runs. Fix or quarantine "
                            "its flaky step; each re-run burns about %s." % (j["job"], j["flakes"], j["runs"],
                                                                           f(j["p50_s"]))})
    for w in wfs:
        if w["rerun_rate"] > RERUN_FLAG:
            rec.append({"kind": "rerun-rate", "target": w["workflow"],
                        "text": "workflow `%s` is re-run in %.0f%% of runs (%d ended green: flake suspects)."
                                % (w["workflow"], 100 * w["rerun_rate"], w["flake_suspects"])})
    p50, wait = lead.get("open_to_merge_p50_s"), lead.get("post_green_wait_s")
    if p50 and wait and wait > LEAD_SHARE * p50:
        rec.append({"kind": "lead-time", "target": "merge gate",
                    "text": "PRs wait %s after the last green run (%.0f%% of the %s open-to-merge p50) at the `merge gate`: "
                            "look at the merge queue or review step, not at CI time." % (f(wait), 100 * wait / p50, f(p50))})
    return rec


# --------------------------------------------------------------------------- output
def render(rep):
    f, pct = pp.fmt, lambda x: "n/a" if x is None else "%.0f%%" % (100 * x)
    L = ["PIPELINE HUB  repo=%s  source: %s" % (rep["repo"], rep["source"])]
    L += ["  note: " + n for n in rep["notes"]]
    L += ["", "WORKFLOWS (sampled completed PR runs)", "  %-28s %5s %9s %9s %6s %6s %6s" % (
        "workflow", "runs", "p50", "p90", "red", "rerun", "flake?")]
    L += ["  %-28s %5d %9s %9s %6s %6s %6d" % (w["workflow"][:28], w["runs"], f(w["p50_s"]), f(w["p90_s"]),
                                              pct(w["fail_rate"]), pct(w["rerun_rate"]), w["flake_suspects"])
          for w in rep["workflows"]]
    L += ["", "SLOWEST JOBS (tail = p90, or max when the OSS tool supplies the table)",
          "  %-24s %-26s %5s %9s %9s %6s %6s" % ("workflow", "job", "runs", "p50", "tail", "red", "flakes")]
    L += ["  %-24s %-26s %5d %9s %9s %6s %6s" % (j["workflow"][:24], j["job"][:26], j["runs"], f(j["p50_s"]),
                                                f(j["tail_s"]), pct(j["fail_rate"]),
                                                "n/a" if j["flakes"] is None else j["flakes"])
          for j in rep["slowest_jobs"]]
    L += ["", "DUPLICATE CHECKS (same suite in 2+ CI steps)"]
    names = lambda xs: ", ".join("`%s`" % x["job"] for x in xs)  # noqa: E731
    L += ["  %s: keep in `%s`; also in %s" % (d["suite"], d["keep"]["job"], names(d["drop"])) if d["identical"] else
          "  %s: different arguments in %s (advisory: check one covers the other)"
          % (d["suite"], names([d["keep"]] + d["drop"])) for d in rep["duplicates"]]
    L += ["  none found"] * (not rep["duplicates"])
    ld = rep["lead"]
    L += ["", "PR LEAD TIME  prs=%d  open-to-merge p50=%s p90=%s  push-to-merge=%s  post-green wait=%s  merged/day=%s" % (
        ld["prs"], f(ld["open_to_merge_p50_s"]), f(ld["open_to_merge_p90_s"]), f(ld["first_push_to_merge_s"]),
        f(ld["post_green_wait_s"]), "n/a" if ld["merged_per_day"] is None else "%.1f" % ld["merged_per_day"])]
    L += ["", "RECOMMENDATIONS"] + ["  %d. [%s] %s" % (i, r["kind"], r["text"]) for i, r in enumerate(rep["recs"], 1)]
    L += ["  none: nothing crossed a threshold"] * (not rep["recs"])
    return "\n".join(L)


def build(repo, root, bundle, oss=None, notes=()):
    wfs, jobs = workflow_stats(bundle), job_stats(bundle)
    table = oss if oss else jobs
    dups, lead = dup_jobs(root, jobs or table), lead_stats(bundle)
    return {"repo": repo, "source": "gh-workflow-stats (job table) + gh API sample" if oss else "gh API sample",
            "notes": list(notes) + (["gh-workflow-stats durations cover successful runs only"] if oss else [])
            + bundle.get("limits", []), "workflows": wfs, "slowest_jobs": table[:8],
            "duplicates": dups, "lead": lead,
            "recs": recommend(wfs, table[:8], dups, lead, flake_jobs=jobs)}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--repo", help="OWNER/NAME (default: origin remote)")
    ap.add_argument("--root", default=".")
    ap.add_argument("--runs", type=int, default=30, help="completed PR runs to sample (max 100, default 30)")
    ap.add_argument("--merges", type=int, default=30, help="merged PRs to sample (default 30)")
    ap.add_argument("--data", metavar="FILE", help="read-write API bundle (resume, offline re-analysis)")
    ap.add_argument("--offline", action="store_true", help="never call gh; analyse --data only")
    ap.add_argument("--no-oss", action="store_true", help="skip the gh-workflow-stats extension")
    ap.add_argument("--json", action="store_true", help="print JSON instead of the report")
    a = ap.parse_args(argv)
    try:  # every failure below is exit 2 with one message, never a traceback (the documented contract)
        if not os.path.isdir(a.root):
            pp.die("--root %s is not a directory" % a.root)
        slug = pp._repo_slug(a.root)
        repo = a.repo or slug
        if not repo:
            pp.die("no --repo and no github.com origin remote")
        if not re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            pp.die("--repo must be OWNER/NAME, got %r" % repo)
        if slug and slug.lower() != repo.lower():  # the duplicate check reads --root's workflow files
            pp.die("--root %s is a checkout of %s, not %s: pass a checkout of %s as --root"
                   % (a.root, slug, repo, repo))
        notes = [] if slug else ["--root has no github.com origin: duplicate checks are read from it and not "
                                 "verified to belong to %s" % repo]
        bundle = pp.load_json(a.data) if a.data and os.path.exists(a.data) else {}
        if not isinstance(bundle, dict):
            raise ValueError("--data is not a JSON object")
        if not a.offline:
            collect(repo, bundle, min(a.runs, 100), a.merges)
            if a.data:
                pp.save_json(a.data, bundle)
        if not bundle.get("runs"):
            pp.die("no workflow runs: %s" % ("; ".join(bundle.get("limits", []))
                                              or "none found (use --data without --offline)"))
        oss, why = (None, None) if a.no_oss or a.offline else oss_jobs(repo, a.root)
        rep = build(repo, a.root, bundle, oss, notes + ([why] if why else []))
        print(json.dumps(rep, indent=1) if a.json else render(rep))
    except (OSError, ValueError, KeyError, TypeError, AttributeError, IndexError) as e:
        pp.die("pipeline_hub: %s: %s (a corrupt or unwritable --data, or an unexpected API reply)"
               % (type(e).__name__, e))
    return 0


if __name__ == "__main__":
    sys.exit(main())
