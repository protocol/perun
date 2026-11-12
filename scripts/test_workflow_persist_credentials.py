#!/usr/bin/env python3
"""Every actions/checkout step in .github/workflows must set `persist-credentials: false`
(zizmor artipacked), unless the step carries a `zizmor: ignore[artipacked]` comment with a reason.
Offline; run with `python3 scripts/test_workflow_persist_credentials.py [dir ...]; default is .github/workflows, pass the templates dir explicitly to scan it`. Exit 1 lists offenders."""
import pathlib, re, sys

def _indent(ln):
    return len(ln) - len(ln.lstrip())

def _sets_false(block):
    """True if the step's own `with:` mapping has a `persist-credentials: false` key (not run:/comment text)."""
    for j, ln in enumerate(block):
        if not re.match(r"\s*with:\s*(#.*)?$", ln):
            continue
        child = None
        for nxt in block[j + 1:]:
            if not nxt.strip() or nxt.lstrip().startswith("#"):
                continue
            if _indent(nxt) <= _indent(ln):
                break
            child = _indent(nxt) if child is None else child
            if _indent(nxt) == child and re.match(r"\s*persist-credentials:\s*[\"']?false[\"']?\s*(#.*)?$", nxt):
                return True
    return False

def offenders(text):
    """Return 1-based line numbers of the `- ` line of each checkout step lacking persist-credentials: false.
    A step is its own lines only: from its `- ` line to the next non-blank line at or left of that indent."""
    lines, bad = text.splitlines(), []
    for i, ln in enumerate(lines):
        if not re.match(r"\s*-\s", ln):
            continue
        block = [ln]
        for nxt in lines[i + 1:]:
            if nxt.strip() and _indent(nxt) <= _indent(ln):
                break
            block.append(nxt)
        if not any(re.match(r"\s*(-\s+)?uses:\s*[\"']?actions/checkout@", b) for b in block):
            continue
        ignored = any(re.search(r"#.*zizmor: ignore\[artipacked\]", b) for b in block)
        if not _sets_false(block) and not ignored:
            bad.append(i + 1)
    return bad

def main():
    args = sys.argv[1:] or [".github/workflows"]
    # self-check: the detector must flag a bare checkout and accept the fixed forms
    assert offenders("steps:\n  - uses: actions/checkout@abc\n  - run: x\n") == [1 + 1]
    assert offenders("steps:\n  - uses: actions/checkout@abc\n    with:\n      fetch-depth: 0\n") == [2]
    assert offenders("steps:\n  - uses: actions/checkout@abc\n    with:\n      persist-credentials: false\n") == []
    assert offenders("steps:\n  - uses: actions/checkout@abc # zizmor: ignore[artipacked] pushes tag\n") == []
    # quoted uses is still a checkout
    assert offenders('steps:\n  - uses: "actions/checkout@abc"\n') == [2]
    assert offenders("steps:\n  - uses: 'actions/checkout@abc'\n    with:\n      persist-credentials: false\n") == []
    # an ignore comment in the NEXT step must not excuse this one
    assert offenders("steps:\n  - uses: actions/checkout@abc\n  - uses: x@1 # zizmor: ignore[artipacked]\n") == [2]
    # uses need not be the first key; name-before-uses is covered
    assert offenders("steps:\n  - name: co\n    uses: actions/checkout@abc\n") == [2]
    assert offenders("steps:\n  - name: co\n    uses: actions/checkout@abc\n    with:\n      persist-credentials: false\n") == []
    # text in run:/comments is not a with: key
    assert offenders("steps:\n  - uses: actions/checkout@abc\n  - run: |\n      echo persist-credentials: false\n") == [2]
    assert offenders("steps:\n  - uses: actions/checkout@abc\n    # persist-credentials: false\n") == [2]
    assert offenders("steps:\n  - uses: actions/checkout@abc\n    with:\n      ref: persist-credentials: false\n") == [2]
    fails = [f"{p}:{n}" for d in args for p in sorted(pathlib.Path(d).glob("*.y*ml")) for n in offenders(p.read_text())]
    if fails:
        print("checkout without persist-credentials: false:", *fails, sep="\n  ")
        sys.exit(1)
    print("ok")

main()
