#!/usr/bin/env python3
"""Standing rival harness: scores each Perun skill against its strongest public rival so superiority is a number.

usage: rival_eval.py run [--skills a,b | --changed [BASE]] [--split heldout|tune] [--gen pcss|claude]
                         [--out DIR] [--jobs N] [--cap USD] [--total-cap USD]
       rival_eval.py write SKILL SPLIT      (draw a scenario set from the skill's writer brief; never shows skill text)
       rival_eval.py changed [BASE]         (print the skills a diff touches)
       rival_eval.py check [SKILL ...]      (split hygiene only; offline)
       rival_eval.py keys SKILL RUNDIR      (answer-key hit rate per arm from cached outputs; offline)

Per skill: Perun arm = the skill's SKILL.md as a system prompt; rival arm = the rival's public text; both answer the same
scenarios with no tools. A blind pairwise judge with no rubric picks the better answer, in both orders. The two answers
carry random three-letter labels (never "Response 1"/"Response 2") and the judge writes a short comparison before its verdict,
because models lean toward a literal slot 1 and a verdict-first reply gives no room to reason. The default judge is GLM-5.1;
a scenario counts as a win or loss only when both orders agree, else it is a tie (0.5). A judge whose slot-1 rate (share of
non-tie picks that sat in the first position) leaves 0.4-0.6 is dropped and GLM-5.2, then gpt-oss_120b, judges instead; when all
are biased the skill gets no verdict. The generator is never a judge. Each judge's slot-1 rate is reported as a health metric.
Output per skill: win rate, bootstrap 95% CI (10,000 resamples, seed 1, over scenarios), PASS only if the lower bound
is above 0.5, and cost. The default generator and judges are PCSS models (free, $0); `--gen claude` is opt-in, one probe call
first, aborts when plan-quota utilization is at or above 0.8, and is capped per skill run (--cap) and in total.
The PCSS key comes from PCSS_KEY or a repo-root .env (never printed, never an argument). Only the PCSS host and, with
--gen claude, the Claude API are contacted; rival texts are fetched once from the URL in rival.json and cached.
Tune sets are for tuning a skill and never produce a verdict; only the frozen held-out set does.
"""
import argparse
import concurrent.futures as cf
import hashlib
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIX = ROOT / "scripts/eval-fixtures/rival"
PCSS = "https://llm.hpc.psnc.pl/v1"
GEN_MODEL, JUDGE_MODEL, TIE_MODEL, LAST_MODEL = "Qwen3.5-397B-A17B", "GLM-5.1", "GLM-5.2", "gpt-oss_120b"  # TIE/LAST = fallback judges
JUDGES = (JUDGE_MODEL, TIE_MODEL, LAST_MODEL)  # tried in order; the first with a healthy slot-1 rate scores a skill
NO_THINK = (GEN_MODEL, JUDGE_MODEL, TIE_MODEL)  # run in non-thinking mode: ~15x faster, and the judge reasons in its own "analysis" field
SLOT1_OK = (0.4, 0.6)  # a judge whose share of "Response 1" picks leaves this band is position-biased and dropped
CLAUDE_MODEL, QUOTA_STOP = "haiku", 0.8
MIN_HELDOUT, MIN_TUNE = 10, 5
ARMS = ("PERUN", "RIVAL")
GEN_TASK = ("Respond to the request below as the assistant the requester has asked for help. You have no tools, no "
            "network and no files: do not claim to have checked or run anything, and use only the facts given. Keep "
            "your whole answer under 600 words. Put the deliverable first; add at most two short lines of note after "
            "it, and only if essential. Do not describe which skills, rules or frameworks you are using.\n\nREQUEST:\n")
JUDGE_SYSTEM = ("You are an impartial judge. Two assistants (Response {a} and Response {b}) answered the same request from a "
                "working professional. You do not know which system wrote which, and the order they appear in carries no "
                "information. Decide which response you would rather receive if you were the requester: the one that would "
                "best help you make the right call or do the work with the fewest follow-up questions, given the situation "
                "described. Do not prefer a response for length, formatting, tone or position. No checklist is provided; use "
                "your own judgement.\n\nFirst compare what each response gets right and wrong for the requester in "
                '"analysis" (two or three sentences), then decide. Output only JSON: '
                '{{"analysis": "<comparison>", "verdict": "{a}" or "{b}" or "tie"}}')


class Stop(Exception):
    """Cap reached or quota too high: the run ends and reports what it has."""


class State:
    def __init__(self, cap):
        self.cap, self.spent, self.reserved, self.util, self.lock = cap, 0.0, 0.0, 0.0, threading.Lock()


def sha(b):
    return hashlib.sha256(b if isinstance(b, bytes) else b.encode()).hexdigest()


def load_key():
    """PCSS_KEY from the environment, else the first repo-root .env (this checkout, then the main checkout of a worktree)."""
    if os.environ.get("PCSS_KEY"):
        return os.environ["PCSS_KEY"]
    cands = [ROOT / ".env"]
    if os.environ.get("PCSS_ENV_FILE"):  # explicit override: search only this file
        cands = [Path(os.environ["PCSS_ENV_FILE"])]
    else:
        common = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--git-common-dir"], capture_output=True, text=True).stdout.strip()
        if common:
            cands.append((ROOT / common).resolve().parent / ".env")
    for p in cands:
        if p.is_file():
            m = re.search(r"^\s*(?:export\s+)?PCSS_KEY\s*=\s*['\"]?([^'\"\s]+)", p.read_text(), re.M)
            if m:
                return m.group(1)
    raise SystemExit("PCSS_KEY missing: set it in the environment or in the repo-root .env")


def chat(model, system, user, max_tokens=6000, temperature=0.0, tries=3):
    """One PCSS chat completion -> text with any <think> block removed. Raises RuntimeError after `tries` failures."""
    req_body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
                "max_tokens": max_tokens, "temperature": temperature}
    if model in NO_THINK:
        req_body["chat_template_kwargs"] = {"enable_thinking": False}
    body = json.dumps(req_body).encode()
    err = ""
    for i in range(tries):
        try:
            req = urllib.request.Request(PCSS + "/chat/completions", body, {"Authorization": "Bearer " + load_key(), "Content-Type": "application/json"})
            txt = json.load(urllib.request.urlopen(req, timeout=600))["choices"][0]["message"]["content"] or ""
            txt = re.sub(r"<think>.*?</think>", "", txt, flags=re.S).strip()
            if txt:
                return txt
            err = "empty output"
        except Exception as e:  # network, HTTP, JSON shape: retry then report the type only (never the key)
            err = type(e).__name__
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{model}: {err}")


def claude_call(system, user, st, reserve=0.10):
    """One claude -p call, no tools -> text. The cap is checked against spend plus every in-flight reserve; the plan-quota
    reading must be present (fail closed). A timeout charges the reserve; a missing binary or timeout becomes a RuntimeError."""
    with st.lock:
        if st.util >= QUOTA_STOP:
            raise Stop(f"plan quota utilization {st.util:.2f} >= {QUOTA_STOP}")
        if st.spent + st.reserved + reserve > st.cap:
            raise Stop(f"cap ${st.cap} reached: spent {st.spent:.3f}, in flight {st.reserved:.3f}")
        st.reserved += reserve
    cmd = ["claude", "-p", "--model", CLAUDE_MODEL, "--output-format", "stream-json", "--verbose", "--tools", "",
           "--no-session-persistence", "--setting-sources", "project,local", "--strict-mcp-config", "--disable-slash-commands",
           "--max-budget-usd", str(reserve), "--system-prompt", system]
    txt, cost, util, seen, err = "", 0.0, 0.0, False, ""
    try:
        with tempfile.TemporaryDirectory(prefix="rival-") as w:
            p = subprocess.run(cmd, input=user, capture_output=True, text=True, cwd=w, timeout=900)
        for line in p.stdout.splitlines():
            try:
                j = json.loads(line)
            except ValueError:
                continue
            if j.get("type") == "rate_limit_event":
                ws = (j.get("rate_limit_info") or {}).get("unifiedWindows") or {}
                util, seen = max([util] + [float(v.get("utilization") or 0) for v in ws.values()]), seen or bool(ws)
            elif j.get("type") == "result":
                txt, cost = j.get("result") or "", float(j.get("total_cost_usd") or 0)
    except subprocess.TimeoutExpired:
        cost, err = reserve, "claude: timed out"  # unknown spend: charge the whole reserve
    except FileNotFoundError:
        err = "claude: binary not found"
    with st.lock:
        st.reserved -= reserve
        st.spent += cost
        if not err:
            st.util = max(st.util, util if seen else 1.0)  # no utilization reading: treat the quota as exhausted
    if err:
        raise RuntimeError(err)
    if not seen:
        raise Stop("no plan-quota utilization reading in the claude output (fail closed)")
    if not txt.strip():
        raise RuntimeError("claude: empty output")
    return txt


def generate(backend, system, user, st):
    return claude_call(system, user, st) if backend == "claude" else chat(GEN_MODEL, system, user, temperature=0.3)


def boot(vals, n=10000, seed=1):
    """Percentile bootstrap 95% CI of the mean of per-scenario scores."""
    rng, m = random.Random(seed), len(vals)
    bs = sorted(sum(vals[rng.randrange(m)] for _ in range(m)) / m for _ in range(n))
    return bs[int(0.025 * n)], bs[int(0.975 * n) - 1]


def order_score(verdict, first):
    """Perun's score for one judged order: first/second = the arm shown as Response 1/2."""
    if verdict == "tie":
        return 0.5
    win = first if verdict == "1" else "RIVAL" if first == "PERUN" else "PERUN"
    return 1.0 if win == "PERUN" else 0.0


def scenario_score(orders):
    """1 only when Perun wins both orders, 0 only when it loses both; any split or tie is 0.5."""
    return orders[0] if len(set(orders)) == 1 and orders[0] in (0.0, 1.0) else 0.5


def slot1_rate(verdicts):
    """Share of non-tie verdicts that picked Response 1 (None with no decisive verdict): position-bias health metric."""
    v = [x for x in verdicts if x in ("1", "2")]
    return v.count("1") / len(v) if v else None


def jparse(txt):
    s = txt.strip()
    for o, c in (("[", "]"), ("{", "}")):
        if o in s and c in s:
            try:
                return json.loads(s[s.index(o): s.rindex(c) + 1])
            except ValueError:
                pass
    out, i, dec = [], 0, json.JSONDecoder()  # a writer that drops the outer brackets: objects back to back
    try:
        while i < len(s):
            if s[i] != "{":  # skip separators and stray seed numbers between objects
                i += 1
                continue
            o, i = dec.raw_decode(s, i)
            out.append(o)
    except ValueError:
        return None
    return out or None


def config(skill):
    return json.loads((FIX / skill / "rival.json").read_text())


def skills():
    return sorted(p.name for p in FIX.iterdir() if (p / "rival.json").is_file())


def load_scenarios(skill, split):
    """-> [{"id", "prompt"}]; a scenario with a "file" field takes the file's text as its prompt (review patches)."""
    out = []
    for s in json.loads((FIX / skill / f"{split}.json").read_text()):
        if "file" in s:
            s = {"id": s["id"], "prompt": "Review this patch and report what is wrong with it:\n\n" + (ROOT / s["file"]).read_text()}
        out.append(s)
    return out


def digest(skill):
    """sha256 over heldout.json plus the bytes of every file a scenario references, so a swapped patch breaks the freeze."""
    h = (FIX / skill / "heldout.json").read_bytes()
    for x in json.loads(h):
        if "file" in x:
            h += b"\0" + (ROOT / x["file"]).read_bytes()
    return sha(h)


def norm(t):
    return re.sub(r"\W+", " ", t.lower()).strip()


def shingles(t, k=6):
    w = norm(t).split()
    return {" ".join(w[i:i + k]) for i in range(max(1, len(w) - k + 1))}


def check_split(skill):
    """Split-hygiene problems for one skill (empty list = clean). Held-out must be frozen, disjoint from tune and big enough."""
    cfg, bad = config(skill), []
    held, tune = load_scenarios(skill, "heldout"), load_scenarios(skill, "tune")
    if digest(skill) != cfg.get("heldout_sha256"):
        bad.append("heldout.json or a file it references changed without updating heldout_sha256 in rival.json")
    if len(held) < MIN_HELDOUT:
        bad.append(f"heldout n={len(held)} < {MIN_HELDOUT}")
    if len(tune) < MIN_TUNE:
        bad.append(f"tune n={len(tune)} < {MIN_TUNE}")
    for name, s in (("heldout", held), ("tune", tune)):
        if len({x["id"] for x in s}) != len(s):
            bad.append(f"{name} has duplicate ids")
        if len({norm(x["prompt"]) for x in s}) != len(s):
            bad.append(f"{name} has duplicate prompts")
    if {x["id"] for x in held} & {x["id"] for x in tune}:
        bad.append("heldout and tune share an id")
    tsh = [shingles(x["prompt"]) for x in tune]
    for h in held:
        hs = shingles(h["prompt"])
        if any(len(hs & t) / max(1, min(len(hs), len(t))) > 0.5 for t in tsh):
            bad.append(f"heldout {h['id']} overlaps a tune prompt by more than half")
    return bad + check_keys(skill)


def load_keys(skill):
    """-> {scenario id: {"must": {name: regex}, "mustnot": {...}, "mustnot_draft": {...}}} from <skill>/keys.json, or {} without one."""
    f = FIX / skill / "keys.json"
    return json.loads(f.read_text()) if f.is_file() else {}


def check_keys(skill):
    """Answer-key hygiene (empty = clean): every held-out id keyed, 3-6 must-hit and 1-3 must-not items, every regex compiles."""
    keys, bad = load_keys(skill), []
    if not keys:
        return bad
    for sc in load_scenarios(skill, "heldout"):
        k = keys.get(sc["id"])
        if not k:
            bad.append(f"keys.json: no key for heldout {sc['id']}")
            continue
        no = len(k.get("mustnot", {})) + len(k.get("mustnot_draft", {}))
        if not 3 <= len(k.get("must", {})) <= 6 or not 1 <= no <= 3:
            bad.append(f"keys.json {sc['id']}: needs 3-6 must and 1-3 mustnot items")
    for i, k in keys.items():
        for grp in ("must", "mustnot", "mustnot_draft"):
            for name, rx in k.get(grp, {}).items():
                try:
                    re.compile(rx)
                except re.error as e:
                    bad.append(f"keys.json {i}/{name}: bad regex ({e})")
    return bad


def draft_text(t):
    """Only the parts of an answer that read as a drafted public message: > quoted lines and fenced blocks."""
    out, fence = [], False
    for ln in t.splitlines():
        if ln.lstrip().startswith("```"):
            fence = not fence
        elif fence or ln.lstrip().startswith(">"):
            out.append(ln)
    return "\n".join(out)


NEG = re.compile(r"\b(never|don'?t|do not|doesn'?t|won'?t|shouldn'?t|avoid|not|no|without|omit|exclude|instead of)\b", re.I)


def violated(rxs, text):
    """Names of must-not regexes that match inside a sentence with no negation word before the match, so "never promise a
    guaranteed profit" is not a violation. [placeholder] and <placeholder> spans are blanked first."""
    text = re.sub(r"\[[^\]]*\]|<[^>]*>", " ", text)
    out = []
    for n, rx in rxs.items():
        for s in re.split(r"(?<=[.!?])\s+|\n", text):
            if any(not NEG.search(s[:m.start()]) for m in re.finditer(rx, s, re.I)):
                out.append(n)
                break
    return out


def key_score(skill, outs):
    """Deterministic outcome score: per arm, mean fraction of must-hit items found (hit_rate) and share of scenarios with any
    must-not hit (violation_rate). outs = {arm: {scenario id: answer text}}; only ids with a key and every arm's answer count.
    Regex only, case-insensitive; must-nots skip negated sentences (see `violated`); `mustnot_draft` is checked against the
    drafted-message lines only; `needs_draft` keys flag `no_draft` (counted as a violation) when the answer has none.
    ponytail: keyword match proves presence, not quality; upgrade to a PCSS item-presence judge if regex misses paraphrases."""
    keys = load_keys(skill)
    ids = [i for i in keys if all(i in outs[a] for a in outs)]
    res = {}
    for a in outs:
        per = {}
        for i in ids:
            t, k = outs[a][i], keys[i]
            hit = [n for n, rx in k["must"].items() if re.search(rx, t, re.I | re.S)]
            d = draft_text(t)
            bad = violated(k.get("mustnot", {}), t) + violated(k.get("mustnot_draft", {}), d)
            no_draft = bool(k.get("needs_draft")) and not d.strip()  # asked for a drafted message, none in a > quote or code fence
            per[i] = dict(hits=len(hit), of=len(k["must"]), missed=sorted(set(k["must"]) - set(hit)), violated=bad, no_draft=no_draft)
        n = len(per)
        res[a] = dict(n=n, hit_rate=round(sum(p["hits"] / p["of"] for p in per.values()) / n, 3) if n else None,
                      violation_rate=round(sum(bool(p["violated"]) or p["no_draft"] for p in per.values()) / n, 3) if n else None, per_scenario=per)
    return res


def arm_text(skill, arm):
    cfg = config(skill)
    if arm == "PERUN":
        return (ROOT / cfg["perun"]).read_text()
    r = cfg["rival"]
    if "path" in r:
        return (ROOT / r["path"]).read_text()
    cache = Path(os.environ.get("RIVAL_CACHE", Path.home() / ".cache/perun-rival")) / (sha(r["url"])[:16] + ".md")
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(urllib.request.urlopen(r["url"], timeout=60).read())
    return cache.read_text()


def save(p, text):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("\n".join(x.rstrip() for x in text.splitlines()) + "\n")


def labels(sc, a, b):
    """Two distinct neutral 3-letter tokens for this pair, seeded by scenario and both answers so a cached verdict stays valid.
    Models lean to the literal slot name "Response 1"; an arbitrary token carries no ordinal."""
    r, al = random.Random(sha(sc["id"] + a + b)), "BCDFGHJKLMNPQRSTVWXZ"
    x = "".join(r.choice(al) for _ in range(3))
    y = x
    while y == x:
        y = "".join(r.choice(al) for _ in range(3))
    return x, y


def parse_verdict(txt, x, y):
    """The last "verdict" value in the judge text, mapped from its labels back to slots: "1", "2", "tie" or None (unusable)."""
    m = re.findall(r'"verdict"\s*:\s*"([^"]*)"', txt)
    v = m[-1].strip().split()[-1] if m and m[-1].strip() else ""
    return {x: "1", y: "2", "tie": "tie"}.get(v)


def judge_one(model, sc, a_arm, b_arm, d, outs):
    """Cached judge call -> raw verdict ("1", "2", "tie") for this order, or None when the model gave no usable verdict."""
    a, b = outs[a_arm][sc["id"]], outs[b_arm][sc["id"]]
    x, y = labels(sc, a, b)
    system = JUDGE_SYSTEM.format(a=x, b=y)
    user = f"REQUEST:\n{sc['prompt']}\n\n=== Response {x} ===\n{a}\n\n=== Response {y} ===\n{b}\n"
    p = d / "judge" / model / f"{a_arm}__{b_arm}" / f"{sc['id']}-{sha(model + system + user)[:8]}.json"  # key: judge, rubric, scenario, both answers
    if not p.exists():
        for _ in range(2):
            try:
                v = parse_verdict(chat(model, system, user, max_tokens=3000), x, y)
            except RuntimeError:
                continue
            if v:
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(json.dumps({"verdict": v}, indent=1) + "\n")
                break
        else:
            return None
    return json.loads(p.read_text())["verdict"]


def run_skill(skill, split, backend, out, jobs, cap):
    """Generate both arms, judge, score. Returns the result dict (also written to <dir>/results.json)."""
    assert GEN_MODEL not in JUDGES, "judge must differ from the generator"
    if split == "heldout":
        bad = check_split(skill)
        if bad:
            raise SystemExit(f"{skill}: split hygiene failed (fail closed): " + "; ".join(bad))
    cfg, scs, st = config(skill), load_scenarios(skill, split), State(cap)
    gen_task = (ROOT / cfg["gen_task"]).read_text() if "gen_task" in cfg else GEN_TASK
    systems = {a: arm_text(skill, a) for a in ARMS}
    key = sha("".join(systems.values()) + gen_task + (CLAUDE_MODEL if backend == "claude" else GEN_MODEL))[:8]
    d = out / skill / f"{split}-{key}"
    outs, errs = {a: {} for a in ARMS}, []

    def gen(a, sc):
        p = d / "outputs" / a / f"{sc['id']}-{sha(sc['prompt'])[:8]}.txt"
        if not p.exists():
            try:
                save(p, generate(backend, systems[a], gen_task + sc["prompt"], st))
            except RuntimeError as e:
                return errs.append(f"gen {a}/{sc['id']}: {e}")
        outs[a][sc["id"]] = p.read_text()

    stopped = ""
    try:
        if backend == "claude":
            claude_call("Be terse.", "ok", st, 0.05)  # quota probe: aborts before any real call when utilization >= 0.8
        with cf.ThreadPoolExecutor(jobs) as ex:
            list(ex.map(lambda t: gen(*t), [(a, s) for a in ARMS for s in scs]))
    except Stop as e:
        stopped = str(e)
    ok = [s for s in scs if all(s["id"] in outs[a] for a in ARMS)]

    health, used, sc_scores = {}, None, {}
    for model in JUDGES:
        def both(sc, model=model):
            return sc["id"], [judge_one(model, sc, a, b, d, outs) for a, b in (ARMS, ARMS[::-1])]
        with cf.ThreadPoolExecutor(jobs) as ex:
            vs = dict(ex.map(both, ok))
        rate = slot1_rate([x for pair in vs.values() for x in pair])
        health[model] = None if rate is None else round(rate, 3)
        if rate is not None and SLOT1_OK[0] <= rate <= SLOT1_OK[1]:  # no decisive verdict at all is unhealthy too
            used = model
            for i, pair in vs.items():
                if None in pair:
                    errs.append(f"judge {i}: no verdict")
                else:
                    sc_scores[i] = scenario_score([order_score(x, a) for x, (a, _) in zip(pair, (ARMS, ARMS[::-1]))])
            break
    if used is None:
        errs.append(f"no judge with slot-1 rate in {SLOT1_OK}: {health}")
    v = list(sc_scores.values())
    res = dict(skill=skill, split=split, rival=cfg["rival"]["name"], n=len(v), n_scenarios=len(scs),
               gen_model=CLAUDE_MODEL if backend == "claude" else GEN_MODEL, judge=used, slot1_rate=health,
               spend_usd=round(st.spent, 4), per_scenario=sc_scores, errors=errs, stopped=stopped,
               perun_sha256=sha(systems["PERUN"])[:16], rival_sha256=sha(systems["RIVAL"])[:16],
               bootstrap="10000 resamples, seed 1, percentile, over scenarios")
    if load_keys(skill):
        res["answer_key"] = {a: {k: x for k, x in r.items() if k != "per_scenario"} for a, r in key_score(skill, outs).items()}
    if v:
        lo, hi = boot(v)
        res.update(win_rate=round(sum(v) / len(v), 3), ci95=[round(lo, 3), round(hi, 3)])
        if split == "heldout":
            res["verdict"] = "PASS" if lo > 0.5 and len(v) >= MIN_HELDOUT else "FAIL"
        else:
            res["verdict"] = "tuning only (no verdict)"
    (d / "results.json").parent.mkdir(parents=True, exist_ok=True)
    (d / "results.json").write_text(json.dumps(res, indent=1) + "\n")
    return res


def summary(results):
    rows = ["| Skill | Rival | n | Win rate [95% CI] | Verdict | Spend |", "|---|---|---|---|---|---|"]
    for r in results:
        w = f"{r['win_rate']:.3f} [{r['ci95'][0]:.3f}, {r['ci95'][1]:.3f}]" if "win_rate" in r else "no data"
        rows.append(f"| {r['skill']} | {r['rival']} | {r['n']} | {w} | {r.get('verdict', 'n/a')} | ${r['spend_usd']:.2f} |")
    return "\n".join(rows) + "\n"


def changed_skills(base="origin/main"):
    """Skills whose SKILL.md/references or rival fixtures a diff touches (committed since BASE plus working tree)."""
    files = set()
    for args in (["diff", "--name-only", f"{base}...HEAD"], ["diff", "--name-only", "HEAD"], ["ls-files", "--others", "--exclude-standard"]):
        p = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True)
        if p.returncode:
            raise SystemExit(f"git {' '.join(args)} failed: {p.stderr.strip()}")
        files.update(p.stdout.split())
    known = set(skills())
    hit = set()
    for f in files:
        m = re.match(r"\.claude/skills/([^/]+)/|scripts/eval-fixtures/rival/([^/]+)/", f)
        if m and (m.group(1) or m.group(2)) in known:
            hit.add(m.group(1) or m.group(2))
    return sorted(hit)


def write_set(skill, split, force=False):
    """Draw a scenario set from the writer brief (public purpose only) and freeze the held-out hash."""
    cfg = config(skill)
    if split == "heldout" and (FIX / skill / "heldout.json").exists() and not force:
        raise SystemExit(f"{skill}: heldout.json is frozen; rewriting it needs --force")
    w = cfg["writer"]
    brief = (ROOT / w["brief"]).read_text()
    seeds = [l for l in (ROOT / w["seeds"]).read_text().splitlines() if re.match(r"\d\d ", l)]
    use = seeds[:6] if split == "tune" and w.get("sliced") else seeds[6:] if w.get("sliced") else seeds
    prompt = brief.replace("{N}", str(len(use))) + "\n" + "\n".join(use) + "\n"
    arr = None
    for _ in range(6):
        txt = chat(GEN_MODEL, "You write evaluation scenarios.", prompt, max_tokens=12000, temperature=0.7)
        arr = jparse(txt)
        if not isinstance(arr, list):  # writer ignored JSON: accept "NN" header lines followed by prose
            bits = re.split(r"(?m)^(\d\d)[ \t]*$", txt)
            arr = [{"id": i, "prompt": t.strip()} for i, t in zip(bits[1::2], bits[2::2]) if t.strip()]
        if isinstance(arr, list) and len(arr) == len(use) and all(isinstance(x, dict) and {"id", "prompt"} <= set(x) for x in arr):
            break
        print(f"retry {skill}/{split}: got {len(arr) if isinstance(arr, list) else type(arr).__name__}, want {len(use)}")
        arr = None
    assert arr, "writer returned no valid scenario array"
    p = FIX / skill / f"{split}.json"
    p.write_text(json.dumps([{"id": ("h" if split == "heldout" else "") + str(x["id"]), "prompt": x["prompt"]} for x in arr], indent=1) + "\n")
    if split == "heldout":
        cfg["heldout_sha256"] = digest(skill)
        (FIX / skill / "rival.json").write_text(json.dumps(cfg, indent=1) + "\n")
    print("wrote", p)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run")
    r.add_argument("--skills")
    r.add_argument("--changed", nargs="?", const="origin/main", metavar="BASE")
    r.add_argument("--split", default="heldout", choices=("heldout", "tune"))
    r.add_argument("--gen", default="pcss", choices=("pcss", "claude"))
    r.add_argument("--out", default=str(Path(os.environ.get("TMPDIR", "/tmp")) / "rival-eval"))
    r.add_argument("--jobs", type=int, default=4)
    r.add_argument("--cap", type=float, default=0.50, help="USD per skill run (claude generator only)")
    r.add_argument("--total-cap", type=float, default=6.0, help="USD over all skills in this invocation")
    w = sub.add_parser("write")
    w.add_argument("skill")
    w.add_argument("split", choices=("heldout", "tune"))
    w.add_argument("--force", action="store_true", help="overwrite a frozen held-out set")
    c = sub.add_parser("changed")
    c.add_argument("base", nargs="?", default="origin/main")
    q = sub.add_parser("keys", help="rescore cached outputs against the skill's answer key (offline, no model call)")
    q.add_argument("skill")
    q.add_argument("dir", help="a run dir holding outputs/<ARM>/<id>-<hash>.txt")
    k = sub.add_parser("check")
    k.add_argument("skills", nargs="*")
    a = ap.parse_args(argv)
    if a.cmd == "write":
        return write_set(a.skill, a.split, a.force)
    if a.cmd == "changed":
        return print("\n".join(changed_skills(a.base)))
    if a.cmd == "keys":
        for x in ARMS:
            if not (Path(a.dir) / "outputs" / x).is_dir():
                raise SystemExit(f"keys: missing arm directory {Path(a.dir) / 'outputs' / x}")
        outs = {x: {f.stem.rsplit("-", 1)[0]: f.read_text() for f in (Path(a.dir) / "outputs" / x).glob("*.txt")} for x in ARMS}
        return print(json.dumps({x: {k: v for k, v in r.items() if k != "per_scenario"} for x, r in key_score(a.skill, outs).items()}, indent=1))
    if a.cmd == "check":
        rc = 0
        for s in a.skills or skills():
            for b in check_split(s):
                rc = 1
                print(f"{s}: {b}")
        return rc
    load_key()  # the judges are always PCSS models: fail early, before any generation, when the key is missing
    want = a.skills.split(",") if a.skills else changed_skills(a.changed) if a.changed else skills()
    if not want:
        return print("no skill touched by the diff: nothing to score")
    out, results, total = Path(a.out), [], 0.0
    for s in want:
        if total >= a.total_cap:
            print(f"total cap ${a.total_cap} reached; skipping {s}")
            continue
        res = run_skill(s, a.split, a.gen, out, a.jobs, min(a.cap, a.total_cap - total))
        total += res["spend_usd"]
        results.append(res)
        print(summary([res]).splitlines()[-1], flush=True)
        if res["stopped"]:
            print("STOP:", res["stopped"])
            break
    (out / "summary.md").parent.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(summary(results))
    (out / "summary.json").write_text(json.dumps({"total_spend_usd": round(total, 4), "results": results}, indent=1) + "\n")
    print(summary(results) + f"Total spend ${total:.2f}")


if __name__ == "__main__":
    sys.exit(main())
