#!/usr/bin/env python3
"""Tests for templates/semgrep-taint/llm-context.yml: system-prompt leakage (CWE-200, LLM07:2025) and unscoped vector-store reads
(CWE-639, LLM08:2025). Fixtures use `# ruleid: <id>` / `// ruleid: <id>` (next line must be a finding of that id) and `ok: <id>` (next
line must stay clean). Every rule has a positive case and a clean twin; the live check also runs the JS fixture as .ts. Live check needs
semgrep and prints SKIP without it. Fictional names only; the key-shaped literal is assembled at run time. RULES=<dir> checks another copy."""
import json, os, re, shutil, subprocess, tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES = os.environ.get("RULES") or os.path.join(ROOT, ".claude", "skills", "deep-code-review", "templates", "semgrep-taint")
KEY = "sk-" + "a" * 30

PY = '''
import os
from flask import jsonify

SYSTEM_PROMPT = "You are Acme Capital's helper."
def secret_env_fstring(client, q):
    # ruleid: perun.llm.system-prompt-secret-py
    msgs = [{"role": "system", "content": f"Use key {os.environ['ACME_API_KEY']} to call tools"}, {"role": "user", "content": q}]
def secret_developer_var(db_password):
    # ruleid: perun.llm.system-prompt-secret-py
    return {"role": "developer", "content": "Login with " + db_password}
def secret_literal():
    # ruleid: perun.llm.system-prompt-secret-py
    return {"role": "system", "content": "token KEYLIT"}
def secret_anthropic(client, api_token):
    # ruleid: perun.llm.system-prompt-secret-py
    return client.messages.create(model="m", max_tokens=9, system=f"auth {api_token}", messages=[])
def secret_responses(client):
    # ruleid: perun.llm.system-prompt-secret-py
    return client.responses.create(model="m", instructions=f"key {os.getenv('ACME_SECRET')}")
def clean_prompt(max_tokens, name):
    # ok: perun.llm.system-prompt-secret-py
    a = {"role": "system", "content": f"Answer in {max_tokens} tokens for {name}"}
    # ok: perun.llm.system-prompt-secret-py
    return {"role": "user", "content": f"my key {os.environ['ACME_API_KEY']}"}
def clean_anthropic(client):
    # ok: perun.llm.system-prompt-secret-py
    return client.messages.create(model="m", max_tokens=9, system="Be brief.", messages=[])
def secret_format_pct(api_key, db_password):
    # ruleid: perun.llm.system-prompt-secret-py
    a = {"role": "system", "content": "key {}".format(api_key)}
    # ruleid: perun.llm.system-prompt-secret-py
    b = {"role": "system", "content": "pw {pw}".format(pw=db_password)}
    # ruleid: perun.llm.system-prompt-secret-py
    return {"role": "system", "content": "key %s" % api_key}
def clean_lookalikes(cfg, name):
    # ok: perun.llm.system-prompt-secret-py
    a = {"role": "system", "content": "You are the task-management-assistant"}
    # ok: perun.llm.system-prompt-secret-py
    b = {"role": "system", "content": f"limit {cfg.token_limit} {cfg.password_policy_text}"}
    # ok: perun.llm.system-prompt-secret-py
    c = {"role": "system", "content": f"Tokenizer is {tokenizer_name}"}
    # ok: perun.llm.system-prompt-secret-py
    d = {"role": "system", "content": f"Answer in {cfg.token_count} tokens"}
    # ruleid: perun.llm.system-prompt-secret-py
    e = {"role": "system", "content": f"Use {cfg.account_secret} for tools"}
    # ok: perun.llm.system-prompt-secret-py
    return {"role": "system", "content": "hi {}".format(name)}

def leak_route(app):
    # ruleid: perun.llm.system-prompt-response-py
    return jsonify(SYSTEM_PROMPT)
def leak_dict(app, cfg):
    # ruleid: perun.llm.system-prompt-response-py
    return jsonify({"prompt": cfg.system_prompt})
def leak_kwarg(app):
    # ruleid: perun.llm.system-prompt-response-py
    return jsonify(prompt=SYSTEM_PROMPT)
def clean_response(answer):
    # ok: perun.llm.system-prompt-response-py
    return jsonify({"answer": answer})
def clean_use(client):
    # ok: perun.llm.system-prompt-response-py
    return client.chat(SYSTEM_PROMPT)

def pine(index, vec, tenant):
    # ruleid: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5)
    # ok: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, filter={"tenant_id": tenant})
    # ok: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, namespace=tenant)
    # ruleid: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, filter=None)
    # ruleid: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, namespace=None)
    # ruleid: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, filter={})
    # ok: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, namespace=None, filter={"tenant_id": tenant})
    # ok: perun.llm.vector-pinecone-py
    index.query(vector=vec, top_k=5, namespace=tenant, filter={})
def chroma(col, tenant):
    # ruleid: perun.llm.vector-chroma-py
    col.query(query_texts=["q"], n_results=3)
    # ruleid: perun.llm.vector-chroma-py
    col.query(query_texts=["q"], n_results=3, where=None)
    # ok: perun.llm.vector-chroma-py
    col.query(query_texts=["q"], n_results=3, where={"tenant_id": tenant})
def lc(store, tenant):
    # ruleid: perun.llm.vector-langchain-py
    store.similarity_search("q", k=4)
    # ruleid: perun.llm.vector-langchain-py
    store.similarity_search_with_score("q")
    # ok: perun.llm.vector-langchain-py
    store.similarity_search("q", k=4, filter={"user_id": tenant})
    # ok: perun.llm.vector-langchain-py
    store.similarity_search("q", 4, {"user_id": tenant})
    # ruleid: perun.llm.vector-langchain-py
    store.max_marginal_relevance_search("q", 4, 20)
    # ok: perun.llm.vector-langchain-py
    store.max_marginal_relevance_search("q", 4, 20, 0.5, {"user_id": tenant})
def weav(docs, tenant, Filter):
    # ruleid: perun.llm.vector-weaviate-py
    docs.query.near_text(query="q", limit=3)
    # ruleid: perun.llm.vector-weaviate-py
    docs.query.near_text(query="q", limit=3, filters=None)
    # ok: perun.llm.vector-weaviate-py
    docs.query.near_text(query="q", limit=3, filters=Filter.by_property("tenant").equal(tenant))
    # ok: perun.llm.vector-weaviate-py
    docs.with_tenant(tenant).query.near_text(query="q")
def qd(client, vec, models):
    # ruleid: perun.llm.vector-qdrant-py
    client.search(collection_name="docs", query_vector=vec, limit=3)
    # ruleid: perun.llm.vector-qdrant-py
    client.search(collection_name="docs", query_vector=vec, query_filter=None, limit=3)
    # ok: perun.llm.vector-qdrant-py
    client.search(collection_name="docs", query_vector=vec, query_filter=models.Filter(), limit=3)
def unrelated(session, re, text):
    session.query(User)
    re.search("a", text)
'''

JS = '''
function secretTemplate(client, q) {
  // ruleid: perun.llm.system-prompt-secret-js
  const m = [{ role: "system", content: `Use ${process.env.ACME_API_KEY} for tools` }];
  // ruleid: perun.llm.system-prompt-secret-js
  const d = { role: "developer", content: "pw " + dbPassword };
  // ruleid: perun.llm.system-prompt-secret-js
  const l = { role: "system", content: "token KEYLIT" };
  // ruleid: perun.llm.system-prompt-secret-js
  return client.messages.create({ model: "m", max_tokens: 9, system: `auth ${apiToken}`, messages: [] });
}
function secretConcat(apiKey) {
  // ruleid: perun.llm.system-prompt-secret-js
  return { role: "system", content: "key ".concat(apiKey) };
}
function cleanLookalikes(cfg) {
  // ok: perun.llm.system-prompt-secret-js
  const a = { role: "system", content: "You are the task-management-assistant" };
  // ok: perun.llm.system-prompt-secret-js
  const b = { role: "system", content: `limit ${cfg.tokenLimit} ${cfg.passwordPolicyText}` };
  // ok: perun.llm.system-prompt-secret-js
  const c = { role: "system", content: `Tokenizer is ${tokenizerName}` };
  // ok: perun.llm.system-prompt-secret-js
  const d = { role: "system", content: `Answer in ${cfg.tokenCount} tokens` };
  // ruleid: perun.llm.system-prompt-secret-js
  const e = { role: "system", content: `Use ${cfg.accountSecret} for tools` };
  // ok: perun.llm.system-prompt-secret-js
  return { role: "system", content: "hi ".concat(cfg.name) };
}
function cleanPrompt(client, maxTokens) {
  // ok: perun.llm.system-prompt-secret-js
  const a = { role: "system", content: `Answer in ${maxTokens} tokens` };
  // ok: perun.llm.system-prompt-secret-js
  const u = { role: "user", content: `key ${process.env.ACME_API_KEY}` };
  // ok: perun.llm.system-prompt-secret-js
  return client.messages.create({ model: "m", max_tokens: 9, system: "Be brief.", messages: [] });
}
function leak(app, systemPrompt, cfg) {
  app.get("/p", (req, res) => {
    // ruleid: perun.llm.system-prompt-response-js
    res.json(systemPrompt);
  });
  // ruleid: perun.llm.system-prompt-response-js
  app.get("/q", (req, res) => res.send({ prompt: cfg.systemPrompt }));
  // ruleid: perun.llm.system-prompt-response-js
  app.get("/r", (req, res) => res.json({ systemPrompt }));
  // ok: perun.llm.system-prompt-response-js
  app.get("/s", (req, res) => res.json({ answer: systemAnswer }));
  // ok: perun.llm.system-prompt-response-js
  return client.chat(systemPrompt);
}
async function vec(index, ns, col, store, docs, qdrant, tenant) {
  // ruleid: perun.llm.vector-pinecone-js
  await index.query({ vector: v, topK: 5 });
  // ok: perun.llm.vector-pinecone-js
  await index.query({ vector: v, topK: 5, filter: { tenantId: tenant } });
  // ok: perun.llm.vector-pinecone-js
  await index.namespace(tenant).query({ vector: v, topK: 5 });
  // ruleid: perun.llm.vector-pinecone-js
  await index.query({ vector: v, topK: 5, filter: undefined });
  // ruleid: perun.llm.vector-pinecone-js
  await index.query({ vector: v, topK: 5, filter: {} });
  // ruleid: perun.llm.vector-pinecone-js
  await index.namespace(undefined).query({ vector: v, topK: 5 });
  // ruleid: perun.llm.vector-chroma-js
  await col.query({ queryTexts: ["q"], where: null });
  // ruleid: perun.llm.vector-chroma-js
  await col.query({ queryTexts: ["q"], nResults: 3 });
  // ok: perun.llm.vector-chroma-js
  await col.query({ queryTexts: ["q"], nResults: 3, where: { tenantId: tenant } });
  // ruleid: perun.llm.vector-langchain-js
  await store.similaritySearch("q", 4);
  // ok: perun.llm.vector-langchain-js
  await store.similaritySearch("q", 4, { userId: tenant });
  // ruleid: perun.llm.vector-weaviate-js
  await docs.query.nearText("q", { limit: 3 });
  // ok: perun.llm.vector-weaviate-js
  await docs.query.nearText("q", { limit: 3, filters: f });
  // ok: perun.llm.vector-weaviate-js
  await docs.withTenant(tenant).query.nearText("q", { limit: 3 });
  // ruleid: perun.llm.vector-qdrant-js
  await qdrant.search("docs", { vector: v, limit: 3 });
  // ok: perun.llm.vector-qdrant-js
  await qdrant.search("docs", { vector: v, limit: 3, filter: f });
  // ruleid: perun.llm.vector-qdrant-js
  await qdrant.query("docs", { query: v, limit: 3 });
  // ok: perun.llm.vector-qdrant-js
  await qdrant.query("docs", { query: v, limit: 3, filter: f });
}
'''

CLIENT = '''"use client";
// ruleid: perun.llm.system-prompt-client-export
export const SYSTEM_PROMPT = "You are Acme Capital's helper.";
// ok: perun.llm.system-prompt-client-export
export const GREETING = "Hello";
'''

CLIENT_LET = '''"use client";
// ruleid: perun.llm.system-prompt-client-export
export let SYSTEM_PROMPT = "You are Acme Capital's helper.";
'''

CLIENT_DEFAULT = '''"use client";
const SYSTEM_PROMPT = "x";
// ruleid: perun.llm.system-prompt-client-export
export default SYSTEM_PROMPT;
'''

CLIENT_LIST = '''"use client";
const SYSTEM_PROMPT = "x";
const GREETING = "y";
// ruleid: perun.llm.system-prompt-client-export
export { SYSTEM_PROMPT };
// ok: perun.llm.system-prompt-client-export
export { GREETING };
'''

SERVER = '''// ok: perun.llm.system-prompt-client-export
export const SYSTEM_PROMPT = "You are Acme Capital's helper.";
'''


def annotated(body, kind):
    out = set()
    for i, l in enumerate(body.splitlines()):
        m = re.match(rf"\s*(?:#|//) {kind}: (\S+)$", l)
        if m:
            out.add((i + 2, m.group(1)))
    return out


FILES = {"app.py": PY.replace("KEYLIT", KEY), "app.js": JS.replace("KEYLIT", KEY), "app.ts": JS.replace("KEYLIT", KEY),
         "client.js": CLIENT, "client_let.js": CLIENT_LET, "client_default.js": CLIENT_DEFAULT, "client_list.js": CLIENT_LIST,
         "server.js": SERVER}
want = {f: annotated(b, "ruleid") for f, b in FILES.items()}
ok = {f: annotated(b, "ok") for f, b in FILES.items()}
rule = open(os.path.join(RULES, "llm-context.yml")).read()
ids = re.findall(r"^- id: (\S+)", rule, re.M)
EXPECTED_IDS = ["perun.llm." + s for s in (
    "system-prompt-secret-py system-prompt-secret-js system-prompt-response-py system-prompt-response-js system-prompt-client-export "
    "vector-pinecone-py vector-pinecone-js vector-chroma-py vector-chroma-js vector-langchain-py vector-langchain-js "
    "vector-weaviate-py vector-weaviate-js vector-qdrant-py vector-qdrant-js").split()]
assert ids == EXPECTED_IDS, ("rule ids drifted", ids)
for i in ids:  # every rule: positive + clean twin, and cwe + owasp-llm metadata
    assert any(i == c for w in want.values() for _, c in w), ("no positive fixture", i)
    assert any(i == c for w in ok.values() for _, c in w), ("no clean twin", i)
assert rule.count("owasp-llm:") == len(ids) and rule.count("cwe: CWE-") == len(ids)

if os.environ.get("REQUIRE_SEMGREP") == "1" and not shutil.which("semgrep"):
    raise SystemExit("FAIL: REQUIRE_SEMGREP=1 but semgrep is not installed")
if shutil.which("semgrep"):
    with tempfile.TemporaryDirectory() as d:
        for f, b in FILES.items():
            open(os.path.join(d, f), "w").write(b)
        env = dict(os.environ, HOME=d, SEMGREP_USER_HOME=d)
        run = subprocess.run(["semgrep", "--config", os.path.join(RULES, "llm-context.yml"), "--metrics=off", "--disable-version-check",
                              "--json", "--quiet", "--"] + list(FILES), capture_output=True, text=True, env=env, cwd=d)
        r = json.loads(run.stdout)
    assert not r["errors"], r["errors"]
    for f in FILES:
        got = {(x["start"]["line"], "perun.llm." + x["check_id"].split("perun.llm.")[-1]) for x in r["results"] if x["path"] == f}
        assert got == want[f], (f, "unexpected", sorted(got - want[f]), "missed", sorted(want[f] - got))
    print("semgrep-llm-context: live ok")
else:
    print("SKIP: semgrep not installed (offline pins only)")
print("semgrep-llm-context: ok")
