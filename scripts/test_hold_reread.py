#!/usr/bin/env python3
"""merge_train: a hold label (policy hold_labels) or draft/close after plan stops the merge; a read error fails closed."""
import io
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".claude", "skills", "agentic-delivery", "scripts"))
import merge_train as mt

TMP = tempfile.mkdtemp(prefix="hold-reread-")
N = 0


def merge(after=None, runner=None, policy=None):
    """Verify 2 PRs, apply `after(forge)`, then merge; return (output, merged PR numbers)."""
    global N
    N += 1
    f = mt.FakeForge(2)
    base = ["--base", "main", "--state", os.path.join(TMP, f"{N}.json"), "--backoff", "5"]
    old = os.environ.pop("PERUN_POLICY", None)
    try:
        assert mt.run(["verify", "--verify-cmd", "t", *base], runner=f, out=io.StringIO(), sleep=f.sleeps.append) == mt.OK
        if after:
            after(f)
        if policy is not None:  # set after verify: the plan-time check would otherwise skip every PR first
            pf = os.path.join(TMP, f"{N}.policy")
            with open(pf, "w") as fh:
                fh.write(policy)
            os.environ["PERUN_POLICY"] = pf
        out = io.StringIO()
        mt.run(["merge", "--apply", "--grant", "g", *base], runner=runner(f) if runner else f, out=out, sleep=f.sleeps.append)
    finally:
        os.environ.pop("PERUN_POLICY", None)
        if old is not None:
            os.environ["PERUN_POLICY"] = old
    return out.getvalue(), [int(c[3]) for c in f.calls if c[:3] == ["gh", "pr", "merge"]]


def raising(f):
    def r(args, cwd=None, timeout=None):
        if "state,isDraft,labels" in args:
            raise OSError("boom")
        return f(args, cwd, timeout)
    return r


def blocked(name, want, **kw):
    out, merged = merge(**kw)
    assert merged == [] and want in out, (name, merged, out)  # the train HALTs: the unverified remainder never lands alone


def main():
    blocked("label", "held (label do-not-merge)", after=lambda f: f.prs[1].update(labels=["do-not-merge"]))
    blocked("case", "held (label Do-Not-Merge)", after=lambda f: f.prs[1].update(labels=[" Do-Not-Merge "]))
    blocked("custom", "held (label wip)", after=lambda f: f.prs[1].update(labels=["wip"]), policy='{"hold_labels": ["WIP"]}')
    blocked("draft", "draft", after=lambda f: f.prs[1].update(isDraft=True))
    blocked("closed", "state=CLOSED", after=lambda f: f.view_override.update({1: {"state": "CLOSED"}}))
    blocked("bad-shape", "cannot re-read", after=lambda f: f.view_override.update({1: {"labels": "x"}}))
    blocked("read-error", "cannot re-read", runner=raising)
    blocked("policy-invalid", "policy unreadable", policy='{"hold_labels": []}')
    _, merged = merge(after=lambda f: f.prs[1].update(labels=["do-not-merge"]), policy='{"hold_labels": ["other"]}')
    assert merged == [1, 2], merged  # custom list replaces the default
    _, merged = merge()
    assert merged == [1, 2], merged  # clean PRs still land
    f = mt.FakeForge(2)
    f.prs[1]["labels"] = ["do-not-merge"]
    buf = io.StringIO()
    mt.run(["plan", "--base", "main", "--state", os.path.join(TMP, "p.json")], runner=f, out=buf, sleep=f.sleeps.append)
    assert "SKIP #1 held (label do-not-merge)" in buf.getvalue(), buf.getvalue()
    print("hold-reread: 11/11")


if __name__ == "__main__":
    main()
