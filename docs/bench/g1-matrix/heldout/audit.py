#!/usr/bin/env python3
"""G1 different-vendor audit of one (a) label (heldout/RULES.md, "Audit"). One call, no retries.

Usage: audit.py ITEM DETECTOR_SHA MODEL OUTDIR   (run from the repo root; needs PCSS_KEY in the environment)
The prompt is built only from committed files: RULES.md, the item's held-out set and result, the item's RESULTS.md
section, and its pilot-api.md row and detector files, both read at DETECTOR_SHA. OUTDIR gets prompt.txt, response.json and
verdict.json (prompt sha256, model, verdict). Material is public and fictional only.
"""
import hashlib, json, os, re, subprocess, sys, urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
URL = "https://llm.hpc.psnc.pl/v1/chat/completions"
SK = ".claude/skills/deep-code-review"
DETECTOR = {"api3": [f"{SK}/templates/semgrep-taint/js.yml", f"{SK}/templates/semgrep-taint/py.yml"],
            "api5": [f"{SK}/scripts/route_auth_map.py", f"{SK}/scripts/tenant_scope_check.py"]}
RULE_IDS = {"api3": "the semgrep rules perun.js.mass-assignment and perun.py.mass-assignment (only these rules are shown from their files)",
            "api5": "route_auth_map.py --privileged"}
SYSTEM = "You are an independent application security auditor. You decide whether a static detector earns a status label. You are strict, and you give reasons."
ASK = """Item: OWASP API Security Top 10:2023 {label}, narrowed to the scope line in RULES.md.
Status (a) means a deterministic detector, with seeded positive and negative tests, that detects the item's class within its stated scope. The bar in RULES.md: precision of at least 0.7 on a held-out set of 30 cases. A low recall does not drop a detector, but the recall and the uncovered shapes must be stated beside the label.
The detector is {rule_ids}.
Question: does this detector detect the item's class within its stated scope well enough to earn status (a)? Answer ACCEPT or REJECT, with reasons. If you think a case is mislabelled, say so, but do not re-score.
End with exactly one fenced json block: {{"verdict": "ACCEPT" or "REJECT", "reasons": [...], "mislabelled_cases": [...]}}."""
LABEL = {"api3": "API3 Broken Object Property Level Authorization (inbound mass assignment)",
         "api5": "API5 Broken Function Level Authorization"}


def only_rules(yml, suffix):
    """The rule blocks of a semgrep file whose id ends in `.suffix`, verbatim. A block runs from its top-level `- id:` line to the next."""
    return "".join(re.findall(rf"^- id: perun\.\w+\.{re.escape(suffix)}\n.*?(?=^- id: |\Z)", yml, re.S | re.M))


def section(md, item):
    """The `## ITEM ...` section of RESULTS.md up to the next `## ` heading; empty when absent."""
    m = re.search(rf"^## {item.upper()}\b.*?(?=^## |\Z)", md, re.S | re.M)
    return m.group(0) if m else ""


def build(item, sha):
    d = HERE / item
    res = json.loads((d / "result.json").read_text())
    res.pop("set_sha256", None)
    parts = [ASK.format(label=LABEL[item], rule_ids=RULE_IDS[item]), "=== RULES.md ===", (HERE / "RULES.md").read_text()]
    pilot = subprocess.run(["git", "show", f"{sha}:docs/bench/g1-matrix/pilot-api.md"], capture_output=True, text=True, check=True).stdout
    row = [l for l in pilot.splitlines() if l.startswith(f"| {item.upper()} ")]
    parts += ["=== Claimed label (pilot-api.md row) ===", *row, "=== RESULTS.md section ===", section((HERE / "RESULTS.md").read_text(), item)]
    for p in DETECTOR[item]:
        body = subprocess.run(["git", "show", f"{sha}:{p}"], capture_output=True, text=True, check=True).stdout
        if p.endswith(".yml"):
            body = only_rules(body, "mass-assignment")
            assert body, p
        parts += [f"=== Detector file {p} at {sha} ===", body]
    parts += ["=== Held-out set: cases.json ===", (d / "cases.json").read_text()]
    for f in sorted(p for p in (d / "cases").rglob("*") if p.is_file()):
        parts += [f"=== {f.relative_to(d).as_posix()} ===", f.read_text()]
    parts += ["=== Scored result (result.json without file hashes) ===", json.dumps(res, indent=1)]
    return "\n\n".join(parts)


def main(item, sha, model, out):
    out = Path(out)
    out.mkdir(parents=True)
    prompt = build(item, sha)
    (out / "prompt.txt").write_text(prompt)
    body = json.dumps({"model": model, "temperature": 0, "max_tokens": 4000,
                       "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type": "application/json", "Authorization": "Bearer " + os.environ["PCSS_KEY"]})
    raw = json.loads(urllib.request.urlopen(req, timeout=900).read())
    (out / "response.json").write_text(json.dumps(raw, indent=1) + "\n")
    text = raw["choices"][0]["message"]["content"] or ""
    m = re.findall(r"```json\s*(\{.*?\})\s*```", text, re.S)
    v = json.loads(m[-1]) if m else {"verdict": "UNPARSED"}
    rec = {"item": item, "detector_sha": sha, "model": model, "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), **v}
    (out / "verdict.json").write_text(json.dumps(rec, indent=1) + "\n")
    print(item, model, rec["verdict"])


if __name__ == "__main__":
    main(*sys.argv[1:])
