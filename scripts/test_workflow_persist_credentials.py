#!/usr/bin/env python3
"""Every actions/checkout step in .github/workflows must set `persist-credentials: false`
(zizmor artipacked), unless the step carries a `zizmor: ignore[artipacked]` comment with a reason.
Offline; run with `python3 scripts/test_workflow_persist_credentials.py [workflow_dir]`. Exit 1 lists offenders."""
import pathlib, re, sys

def offenders(text):
    """Return 1-based line numbers of checkout steps lacking persist-credentials: false."""
    lines, bad = text.splitlines(), []
    for i, ln in enumerate(lines):
        if not re.search(r"uses:\s*actions/checkout@", ln):
            continue
        indent = len(ln) - len(ln.lstrip())
        block = [ln]
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) < indent + 2 and not nxt.lstrip().startswith("#"):
                break
            if re.match(r"\s*-\s", nxt) and len(nxt) - len(nxt.lstrip()) <= indent:
                break
            block.append(nxt)
        body = "\n".join(block)
        if not re.search(r"persist-credentials:\s*false", body) and "zizmor: ignore[artipacked]" not in body:
            bad.append(i + 1)
    return bad

def main():
    d = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else ".github/workflows")
    # self-check: the detector must flag a bare checkout and accept the fixed forms
    assert offenders("steps:\n  - uses: actions/checkout@abc\n  - run: x\n") == [1 + 1]
    assert offenders("steps:\n  - uses: actions/checkout@abc\n    with:\n      fetch-depth: 0\n") == [2]
    assert offenders("steps:\n  - uses: actions/checkout@abc\n    with:\n      persist-credentials: false\n") == []
    assert offenders("steps:\n  - uses: actions/checkout@abc # zizmor: ignore[artipacked] pushes tag\n") == []
    fails = [f"{p}:{n}" for p in sorted(d.glob("*.y*ml")) for n in offenders(p.read_text())]
    if fails:
        print("checkout without persist-credentials: false:", *fails, sep="\n  ")
        sys.exit(1)
    print("ok")

main()
