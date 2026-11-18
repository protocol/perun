#!/usr/bin/env python3
"""Tests for templates/semgrep-taint/llm-supply.yml (OWASP LLM03/LLM04: unpinned hub download, trust_remote_code, torch.load, pickle/joblib load)
and llm-output.yml (OWASP LLM05: LLM completion text reaching eval/exec/Function, innerHTML/dangerouslySetInnerHTML, subprocess/shell, raw SQL).
Every rule has a positive and a clean twin. Fixtures use `# ruleid: <id>` / `// ruleid: <id>` (next line must be a finding) and `# ok: <id>` /
`// ok: <id>` (next line must stay clean); any finding of these rules on an unannotated line fails. Each rule must carry cwe and owasp-llm metadata.
Live check needs semgrep and prints SKIP without it. Fictional names only. RULES=<dir> checks another copy."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")

SUPPLY = '''
import pickle
import joblib
import torch
import huggingface_hub
from huggingface_hub import hf_hub_download, snapshot_download
from transformers import AutoModel

# ruleid: perun.py.llm-unpinned-hub-download
m1 = AutoModel.from_pretrained("acme-labs/tiny-model")
# ruleid: perun.py.llm-unpinned-hub-download
p1 = hf_hub_download("acme-labs/tiny-model", "weights.bin")
# ruleid: perun.py.llm-unpinned-hub-download
p2 = huggingface_hub.hf_hub_download(repo_id="acme-labs/tiny-model", filename="weights.bin")
# ruleid: perun.py.llm-unpinned-hub-download
p3 = snapshot_download(repo_id="acme-labs/tiny-model")
# ok: perun.py.llm-unpinned-hub-download
m2 = AutoModel.from_pretrained("acme-labs/tiny-model", revision="0123456789abcdef0123456789abcdef01234567")
# ok: perun.py.llm-unpinned-hub-download
m3 = AutoModel.from_pretrained("./local-model")
# ok: perun.py.llm-unpinned-hub-download
p4 = snapshot_download(repo_id="acme-labs/tiny-model", revision="0123456789abcdef0123456789abcdef01234567")

# ruleid: perun.py.llm-trust-remote-code
m4 = AutoModel.from_pretrained("./local-model", trust_remote_code=True)
# ok: perun.py.llm-trust-remote-code
m5 = AutoModel.from_pretrained("./local-model", trust_remote_code=False)

# ruleid: perun.py.llm-torch-load-unsafe
w1 = torch.load("ckpt.pt", map_location="cpu", weights_only=False)
# ok: perun.py.llm-torch-load-unsafe
w2 = torch.load("ckpt.pt", weights_only=True)
# ruleid: perun.py.llm-torch-load-default
w3 = torch.load("ckpt.pt")
# ok: perun.py.llm-torch-load-default
w4 = torch.load("ckpt.pt", weights_only=True)

def load_all():
    # ruleid: perun.py.llm-pickle-model-load
    a = pickle.load(open("model.pkl", "rb"))
    # ruleid: perun.py.llm-pickle-model-load
    b = joblib.load("model.joblib")
    # ok: perun.py.llm-pickle-model-load
    c = json.load(open("model.json"))
    return a, b, c
'''

PY_OUT = '''
import os
import subprocess
from anthropic import Anthropic
from openai import OpenAI
from sqlalchemy import text

def code_exec_openai(client, prompt):
    r = client.chat.completions.create(model="m", messages=[{"role": "user", "content": prompt}])
    # ruleid: perun.py.llm-output-code-exec
    eval(r.choices[0].message.content)

def code_exec_anthropic(client, prompt):
    msg = client.messages.create(model="m", max_tokens=9, messages=[{"role": "user", "content": prompt}])
    # ruleid: perun.py.llm-output-code-exec
    exec(msg.content[0].text)

def code_exec_gemini(model, prompt):
    out = model.generate_content(prompt)
    # ruleid: perun.py.llm-output-code-exec
    eval(out.text)

def code_exec_legacy(openai, prompt):
    r = openai.ChatCompletion.create(model="m", messages=[])
    # ruleid: perun.py.llm-output-code-exec
    eval(r["choices"][0]["message"]["content"])

def code_exec_clean(client, prompt):
    client.chat.completions.create(model="m", messages=[])
    # ok: perun.py.llm-output-code-exec
    eval("1 + 1")

def command_shell(client, prompt):
    r = client.responses.create(model="m", input=prompt)
    # ruleid: perun.py.llm-output-command
    os.system(r.output_text)

def command_subprocess(client, prompt):
    msg = client.messages.create(model="m", max_tokens=9, messages=[])
    cmd = msg.content[0].text
    # ruleid: perun.py.llm-output-command
    subprocess.run(cmd, shell=True)

def command_clean(client, prompt):
    client.messages.create(model="m", max_tokens=9, messages=[])
    # ok: perun.py.llm-output-command
    subprocess.run(["ls", "-l"])

def sql_execute(client, conn, prompt):
    r = client.chat.completions.create(model="m", messages=[])
    q = r.choices[0].message.content
    # ruleid: perun.py.llm-output-sql
    conn.execute(f"SELECT * FROM t WHERE {q}")

def sql_text(client, prompt):
    r = client.chat.completions.create(model="m", messages=[])
    # ruleid: perun.py.llm-output-sql
    return text(r.choices[0].message.content)

def sql_clean(client, conn, prompt):
    r = client.chat.completions.create(model="m", messages=[])
    # ok: perun.py.llm-output-sql
    conn.execute("SELECT * FROM t WHERE name = ?", (r.choices[0].message.content,))
'''

JS_OUT = '''
import { generateText } from "ai";
import { exec } from "child_process";
import DOMPurify from "dompurify";
import vm from "vm";

function runSnippet(code) {
  return vm.runInNewContext(code);
}

function measure(code) {
  return code.length;
}

export async function helperSink(api, prompt) {
  const r = await api.createCompletion({ model: "m", prompt });
  const snippet = r.data.choices[0].text;
  // ok: perun.js.llm-output-code-exec
  measure(snippet);
  // ruleid: perun.js.llm-output-code-exec
  return runSnippet(snippet);
}

export async function codeExecOpenAI(client, prompt) {
  const r = await client.chat.completions.create({ model: "m", messages: [] });
  // ruleid: perun.js.llm-output-code-exec
  eval(r.choices[0].message.content);
}

export async function codeExecVercel(model, prompt) {
  const { text } = await generateText({ model, prompt });
  // ruleid: perun.js.llm-output-code-exec
  new Function("a", text)(1);
}

export async function codeExecGemini(model, prompt) {
  const res = await model.generateContent(prompt);
  // ruleid: perun.js.llm-output-code-exec
  eval(res.response.text());
}

export async function codeExecClean(client, prompt) {
  await client.messages.create({ model: "m", max_tokens: 9, messages: [] });
  // ok: perun.js.llm-output-code-exec
  eval("1 + 1");
}

export async function xssInnerHTML(client, el, prompt) {
  const msg = await client.messages.create({ model: "m", max_tokens: 9, messages: [] });
  // ruleid: perun.js.llm-output-xss
  el.innerHTML = msg.content[0].text;
}

export async function xssReact(model, prompt) {
  const { text } = await generateText({ model, prompt });
  // ruleid: perun.js.llm-output-xss
  return <div dangerouslySetInnerHTML={{ __html: text }} />;
}

export async function xssClean(client, el, prompt) {
  const msg = await client.messages.create({ model: "m", max_tokens: 9, messages: [] });
  // ok: perun.js.llm-output-xss
  el.innerHTML = DOMPurify.sanitize(msg.content[0].text);
  // ok: perun.js.llm-output-xss
  el.textContent = msg.content[0].text;
}

export async function commandExec(client, prompt) {
  const r = await client.chat.completions.create({ model: "m", messages: [] });
  // ruleid: perun.js.llm-output-command
  exec(r.choices[0].message.content);
}

export async function commandClean(client, prompt, re) {
  const r = await client.chat.completions.create({ model: "m", messages: [] });
  // ok: perun.js.llm-output-command
  exec("ls -l");
  // ok: perun.js.llm-output-command
  re.exec(r.choices[0].message.content);
}

export async function sqlQuery(client, db, prompt) {
  const r = await client.chat.completions.create({ model: "m", messages: [] });
  // ruleid: perun.js.llm-output-sql
  await db.query(r.choices[0].message.content);
}

export async function sqlClean(client, db, prompt) {
  const r = await client.chat.completions.create({ model: "m", messages: [] });
  // ok: perun.js.llm-output-sql
  await db.query("SELECT * FROM t WHERE name = $1", [r.choices[0].message.content]);
}
'''

FILES = {"supply.py": SUPPLY, "out.py": PY_OUT, "out.tsx": JS_OUT}
ANN = re.compile(r"^\s*(?:#|//) (ruleid|ok): (perun\.\S+)$")


def annotations(body):
    want, ok = set(), set()
    for i, l in enumerate(body.splitlines()):
        m = ANN.match(l)
        if m:
            (want if m.group(1) == "ruleid" else ok).add((m.group(2), i + 2))
    return want, ok


def short(cid):
    return "perun." + cid.split("perun.", 1)[1]


ids = set()
for body in FILES.values():
    w, o = annotations(body)
    ids |= {a for a, _ in w | o}
want_all = {n: annotations(b) for n, b in FILES.items()}
assert len(ids) == 12 and all(any(a == i for a, _ in want_all[n][0]) and any(a == i for a, _ in want_all[n][1]) for i in ids for n in [next(k for k, b in FILES.items() if f": {i}" in b)]), ids
for yml in ("llm-supply.yml", "llm-output.yml"):
    src = open(os.path.join(RULES, yml)).read()
    for rid in re.findall(r"^- id: (\S+)", src, re.M):
        assert rid in ids, ("rule without a fixture", rid)
    assert src.count("- id:") == src.count("    cwe:") == src.count("    owasp-llm:"), yml

if os.environ.get("REQUIRE_SEMGREP") and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for n, b in FILES.items():
            open(os.path.join(d, n), "w").write(b)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", RULES, "--metrics=off", "--disable-version-check", "--json", "--quiet", "--", *FILES],
                             capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    for n in FILES:
        got = {(short(x["check_id"]), x["start"]["line"]) for x in r["results"] if x["path"] == n and ".llm-" in x["check_id"]}
        want, ok = want_all[n]
        assert got == want, (n, "unexpected", sorted(got - want), "missed", sorted(want - got))
        assert not (got & ok), (n, "flagged a clean twin", sorted(got & ok))
    meta = {short(x["check_id"]): x["extra"]["metadata"] for x in r["results"] if ".llm-" in x["check_id"]}
    assert set(meta) == ids and all(m.get("cwe") and m.get("owasp-llm") for m in meta.values()), meta
    print("semgrep-llm-rules: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-llm-rules: ok")
