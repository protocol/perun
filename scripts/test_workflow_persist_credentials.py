#!/usr/bin/env python3
"""Every actions/checkout step in .github/workflows/*.y*ml and .github/actions/**/action.y*ml (composite
actions) must set `persist-credentials: false` (zizmor artipacked).
Files load through a yaml.BaseLoader subclass: every scalar stays a string (no YAML 1.1 bool coercion such as
`no`), and a duplicate mapping key or a `<<` merge key fails the file (a later key would silently win, or a merged
step could hide its `uses`). A step counts as a checkout when its lowercased `uses` starts with
`actions/checkout@`. A `uses` containing `${{` is unverifiable and fails. `with.persist-credentials` must be the
literal string false, False or FALSE (the forms actions/checkout reads as boolean false); anything else
("no", "${{ false }}", missing) fails. Quoting, flow style, key order and text in run: blocks or comments cannot
fool it. There is no ignore comment. Fails closed (exit 2) when PyYAML is missing, a given directory is missing,
or no file is found; exit 1 lists offenders as `file: job[index]`. Offline.
Usage: python3 scripts/test_workflow_persist_credentials.py [dir ...]   (default .github/workflows, plus
.github/actions when it exists)"""
import pathlib, sys

try:
    import yaml
except ImportError:
    print("PyYAML is required (import yaml failed); refusing to pass without parsing the workflows", file=sys.stderr)
    sys.exit(2)

class Loader(yaml.BaseLoader):
    """BaseLoader (all scalars are strings, `<<` is not merged) that rejects duplicate keys and merge keys."""
    def construct_mapping(self, node, deep=False):
        seen = set()
        for k, _ in node.value:
            key = self.construct_object(k, deep=True)
            if key == "<<" or key in seen:
                raise yaml.YAMLError(f"duplicate or merge key {key!r} (line {k.start_mark.line + 1})")
            seen.add(key)
        return super().construct_mapping(node, deep)

def _steps(label, body):
    steps = (body or {}).get("steps") if isinstance(body, dict) else None
    return [(f"{label}[{i}]", s) for i, s in enumerate(steps if isinstance(steps, list) else [])]

def offenders(text):
    """Return `job[index]` (or `composite[index]`) for each checkout step lacking persist-credentials: false.
    A file that fails to parse, repeats a key, or uses a merge key returns a single `parse error` entry."""
    try:
        doc = yaml.load(text, Loader) or {}
    except yaml.YAMLError as e:
        return [f"parse error: {str(e).splitlines()[0]}"]
    if not isinstance(doc, dict):
        return ["parse error: top level is not a mapping"]
    jobs = doc.get("jobs") if isinstance(doc.get("jobs"), dict) else {}
    steps = [s for j, b in jobs.items() for s in _steps(j, b)] + _steps("composite", doc.get("runs"))
    bad = []
    for label, step in steps:
        if not isinstance(step, dict):
            continue
        uses = step.get("uses", "")
        if not isinstance(uses, str) or "${{" in uses:
            bad.append(f"{label} (unverifiable uses)")
        elif uses.lower().startswith("actions/checkout@"):
            w = step.get("with")
            if not isinstance(w, dict) or w.get("persist-credentials") not in ("false", "False", "FALSE"):
                bad.append(label)
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
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: 'false'}\n")) == []  # quoted passes
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: False}\n")) == []
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: FALSE}\n")) == []
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: true}\n")) == ["j[0]"]
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: no}\n")) == ["j[0]"]  # no YAML1.1 bool
    assert offenders(_wf("      - uses: actions/checkout@abc\n        with: {persist-credentials: '${{ false }}'}\n")) == ["j[0]"]
    # text in run:/comments is not a with: key or a checkout
    assert offenders(_wf("      - uses: actions/checkout@abc\n      - run: |\n          with:\n            persist-credentials: false\n")) == ["j[0]"]
    assert offenders(_wf("      - uses: actions/checkout@abc\n# persist-credentials: false\n")) == ["j[0]"]  # col-0 comment
    assert offenders(_wf("      - run: |\n          uses: actions/checkout@abc\n")) == []  # uses text in run:
    assert offenders(_wf("      - uses: actions/checkout@abc # zizmor: ignore[artipacked]\n")) == ["j[0]"]  # no ignore comment
    # a compliant step must not excuse a later bare one
    assert offenders(_wf("      - uses: actions/checkout@a\n        with:\n" + ok + "      - uses: actions/checkout@b\n")) == ["j[1]"]
    # expression uses is unverifiable
    assert offenders(_wf("      - uses: ${{ matrix.co }}@v4\n")) == ["j[0] (unverifiable uses)"]
    # duplicate keys fail the file
    assert offenders("jobs:\n  j:\n    steps: []\n    steps:\n      - uses: actions/checkout@a\n")[0].startswith("parse error")
    assert offenders(_wf("      - uses: actions/checkout@a\n        with:\n" + ok + ok))[0].startswith("parse error")
    # merge key fails the file (an unmerged step would hide its uses)
    assert offenders("x: &c {uses: actions/checkout@a}\njobs:\n  j:\n    steps:\n      - <<: *c\n")[0].startswith("parse error")
    # composite action
    assert offenders("runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@a\n") == ["composite[0]"]
    assert offenders("runs:\n  using: composite\n  steps:\n    - uses: actions/checkout@a\n      with:\n        persist-credentials: false\n") == []
    args = sys.argv[1:] or [".github/workflows"]
    dirs = args + ([".github/actions"] if not sys.argv[1:] and pathlib.Path(".github/actions").is_dir() else [])
    files = []
    for d in dirs:
        p = pathlib.Path(d)
        if not p.is_dir():
            print(f"missing workflow directory: {d}", file=sys.stderr)
            sys.exit(2)
        files += sorted(p.glob("*.y*ml")) + sorted(p.rglob("action.y*ml"))
    files = sorted(set(files))
    if not files:
        print("no workflow files found in: " + " ".join(dirs), file=sys.stderr)
        sys.exit(2)
    fails = [f"{p}: {n}" for p in files for n in offenders(p.read_text())]
    if fails:
        print("checkout without persist-credentials: false:", *fails, sep="\n  ")
        sys.exit(1)
    print("ok")

main()
