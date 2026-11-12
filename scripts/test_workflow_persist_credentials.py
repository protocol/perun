#!/usr/bin/env python3
"""Every actions/checkout step in .github/workflows must set `persist-credentials: false` (zizmor artipacked).
The workflow is parsed with yaml.safe_load, so quoting, flow style, key order and `with:`/`uses:` text inside
run: blocks or comments cannot fool it. A step counts as a checkout when `str(uses).lower()` starts with
`actions/checkout@`; it passes only when `with.persist-credentials` is boolean False or the string "false".
There is no ignore comment. Fails closed (exit 2) when PyYAML is missing, the directory is missing, or no
workflow file is found; exit 1 lists offenders as `file: job[index]`. Offline.
Usage: python3 scripts/test_workflow_persist_credentials.py [dir ...]   (default .github/workflows)"""
import pathlib, sys

try:
    import yaml
except ImportError:
    print("PyYAML is required (import yaml failed); refusing to pass without parsing the workflows", file=sys.stderr)
    sys.exit(2)

def offenders(text):
    """Return `job[index]` for each checkout step in the workflow text lacking persist-credentials: false."""
    bad = []
    for job, body in ((yaml.safe_load(text) or {}).get("jobs") or {}).items():
        for i, step in enumerate((body or {}).get("steps") or []):
            if not isinstance(step, dict) or not str(step.get("uses", "")).lower().startswith("actions/checkout@"):
                continue
            pc = (step.get("with") or {}).get("persist-credentials")
            if pc is not False and pc != "false":
                bad.append(f"{job}[{i}]")
    return bad

def _wf(steps):
    return "jobs:\n  j:\n    steps:\n" + steps

def main():
    # self-check: the detector must flag bare checkouts and accept the fixed forms
    ok = "          persist-credentials: false\n"
    assert offenders(_wf("      - uses: actions/checkout@abc\n")) == ["j[0]"]
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with:\n          fetch-depth: 0\n")) == ["j[0]"]
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with:\n" + ok)) == []
    assert offenders(_wf("      - {uses: actions/checkout@abc}\n")) == ["j[0]"]  # flow-style step
    assert offenders(_wf("      - {uses: actions/checkout@abc, with: {persist-credentials: false}}\n")) == []
    assert offenders(_wf('      - uses: "actions/checkout@abc"\n')) == ["j[0]"]  # quoted uses
    assert offenders(_wf("      - uses: Actions/Checkout@abc\n")) == ["j[0]"]  # case-insensitive
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: false}\n")) == []  # flow with
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: \"false\"}\n")) == []
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: true}\n")) == ["j[0]"]
    # text in run:/comments is not a with: key or a checkout
    assert offenders(_wf("      - uses: actions/checkout@abc\n      - run: |\n          with:\n            persist-credentials: false\n")) == ["j[0]"]
    assert offenders(_wf("      - uses: actions/checkout@abc\n# persist-credentials: false\n")) == ["j[0]"]  # col-0 comment
    assert offenders(_wf("      - run: |\n          uses: actions/checkout@abc\n")) == []  # uses text in run:
    assert offenders(_wf("      - uses: actions/checkout@abc # zizmor: ignore[artipacked]\n")) == ["j[0]"]  # no ignore comment
    # a compliant step must not excuse a later bare one
    assert offenders(_wf("      - uses: actions/checkout@a\n        with:\n" + ok + "      - uses: actions/checkout@b\n")) == ["j[1]"]
    args = sys.argv[1:] or [".github/workflows"]
    files = []
    for d in args:
        if not pathlib.Path(d).is_dir():
            print(f"missing workflow directory: {d}", file=sys.stderr)
            sys.exit(2)
        files += sorted(pathlib.Path(d).glob("*.y*ml"))
    if not files:
        print("no workflow files found in: " + " ".join(args), file=sys.stderr)
        sys.exit(2)
    fails = [f"{p}: {n}" for p in files for n in offenders(p.read_text())]
    if fails:
        print("checkout without persist-credentials: false:", *fails, sep="\n  ")
        sys.exit(1)
    print("ok")

main()
