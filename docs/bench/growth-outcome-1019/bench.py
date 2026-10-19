#!/usr/bin/env python3
"""Outcome bench for growth-analytics against a rival and no skill (see PREREGISTERED.md). Free PCSS models only; no claude -p.

usage: bench.py freeze pre | scen | freeze scen | run ARM.. | report        ARM = V0 | RIVAL | NONE   (JOBS=8 env: threads)

A reviewer answer is scored deterministically against key.json: its last `ERRORS:` line (flagged error codes) and `DECISION:` line are parsed and compared
with the planted errors. No model grades anything; a model only writes the specs (from the key) and the answers. Every output is cached under outputs/
and never overwritten; every call is logged to ledger.jsonl.
"""
import concurrent.futures as cf, hashlib, json, os, random, re, sys, threading, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parents[2] / "scripts"))
sys.path.insert(0, str(D))
import rival_eval as R  # noqa: E402
import key as K  # noqa: E402

WRITER, GENERATOR, SAMPLES, TEMP = "DeepSeek-V4-Flash", R.GEN_MODEL, 2, 0.7
JOBS = int(os.environ.get("JOBS", 8))
ARMS = ("V0", "RIVAL", "NONE")
MARGIN_FA, NONINF_PASS, TOKENS_X, MAX_UNPARSED = 0.03, -0.15, 1.25, 0.05  # preregistered keep-rule constants
_lock = threading.Lock()


def ledger(**kw):
    now = datetime.now(timezone.utc)
    with _lock, open(D / "ledger.jsonl", "a") as f:
        f.write(json.dumps({"ts": int(now.timestamp()), "iso": now.strftime("%Y-%m-%dT%H:%M:%SZ"), **kw}) + "\n")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def chat_usage(model, system, user, temperature):
    """One PCSS chat completion -> (text, completion_tokens); same request shape as rival_eval.chat. RuntimeError (type only, never the key) after 3 tries."""
    body = {"model": model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}], "max_tokens": 3000, "temperature": temperature}
    if model in R.NO_THINK:
        body["chat_template_kwargs"] = {"enable_thinking": False}
    err = ""
    for i in range(3):
        try:
            req = urllib.request.Request(R.PCSS + "/chat/completions", json.dumps(body).encode(), {"Authorization": "Bearer " + R.load_key(), "Content-Type": "application/json"})
            j = json.load(urllib.request.urlopen(req, timeout=600))
            txt = re.sub(r"<think>.*?</think>", "", j["choices"][0]["message"]["content"] or "", flags=re.S).strip()
            if txt:
                return txt, int(j.get("usage", {}).get("completion_tokens", 0))
            err = "empty output"
        except Exception as e:
            err = type(e).__name__
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{model}: {err}")


def call(role, model, system, user, temperature, **tag):
    t = time.time()
    try:
        out = chat_usage(model, system, user, temperature)
        ledger(event="call", role=role, model=model, sec=round(time.time() - t, 1), err="", **tag)
        return out
    except RuntimeError as e:
        ledger(event="call", role=role, model=model, sec=round(time.time() - t, 1), err=str(e)[:80], **tag)
        raise


# ---- scenarios --------------------------------------------------------------------------------------------------------
def flat(t):
    return re.sub(r"\s+", " ", t.lower().replace("‑", "-").replace("–", "-").replace("—", "-")).strip()


def invalid(spec, item):
    """Why a written spec cannot carry the key (None when valid): a required anchor missing, an opposite-polarity anchor present, a stray category word, bad length."""
    t, why = flat(spec), []
    if not 90 <= len(spec.split()) <= 230:
        why.append("length")
    why += [f"missing: {a}" for a in item["required"] if flat(a) not in t]
    opp = [a for c in K.CODES for pol in "+-" for a in K.ANCHORS[c][pol] if a not in item["required"]]
    why += [f"opposite: {a}" for a in opp if flat(a) in t]
    for a in item["required"]:
        t = t.replace(flat(a), " ")
    why += [f"stray {c}" for c in K.CODES if re.search(K.STRAY[c], t)]
    why += ["generic hedge"] * bool(re.search(K.GENERIC, t))
    return "; ".join(why) or None


def write_one(item):
    brief = (D / "prompts/writer_brief.txt").read_text()
    for att in range(10):
        try:
            spec, _ = call("write", WRITER, "You write synthetic product specs for tests.", brief.format(domain=item["domain"], seed=f"{item['id']}-{att}", required="\n".join(f'- "{a}"' for a in item["required"])), 0.9, id=item["id"], att=att)
        except RuntimeError:
            continue
        if not invalid(spec, item):
            return {"id": item["id"], "split": "held", "domain": item["domain"], "spec": spec}
    return None


def scen():
    out = D / "scenarios_held.json"
    if out.exists():
        return print("exists", out)
    key = json.loads((D / "key.json").read_text())
    with cf.ThreadPoolExecutor(JOBS) as ex:
        res = [r for r in ex.map(write_one, key) if r]
    bn = sum(not k["planted"] for k in key if k["id"] in {r["id"] for r in res})
    print(f"{len(res)}/{len(key)} valid, {bn} benign")
    if len(res) < 80 or bn < 20:
        sys.exit("fewer than 80 valid scenarios or 20 benign controls: the bench stops and reports no verdict")
    out.write_text(json.dumps(res, indent=1) + "\n")


# ---- answers and scoring ------------------------------------------------------------------------------------------------
def parse(text):
    """(flagged codes or None, decision or None) from the LAST `ERRORS:` and `DECISION:` lines; None when absent or unreadable."""
    h = re.findall(r"(?im)^[\W_]*ERRORS[\W_]*:(.*)$", text)
    d = re.findall(r"(?im)^[\W_]*DECISION[\W_]*:\W*(HOLD|SHIP)\b", text)
    codes = None
    if h:
        found = {c for c in re.findall(r"[A-Z]{3,7}", h[-1].upper()) if c in K.CODES}
        codes = found if found else set() if "NONE" in h[-1].upper() else None
    return codes, d[-1].upper() if d else None


def answer(arm, sc, k):
    p = D / "outputs" / arm / f"{sc['id']}_{k}.txt"
    if p.exists():
        return
    task = (D / "prompts/task.txt").read_text() + sc["spec"]
    try:
        txt, tok = call("answer", GENERATOR, (D / "prompts" / ("V0.md" if arm == "V0" else "RIVAL.txt" if arm == "RIVAL" else "NONE.txt")).read_text(), task, TEMP, arm=arm, id=sc["id"], k=k)
    except RuntimeError:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_suffix(".tok").write_text(str(tok))
    p.write_text(txt + "\n")


def run(arms):
    sc = json.loads((D / "scenarios_held.json").read_text())
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda a: answer(*a), [(a, s, k) for a in arms for s in sc for k in range(SAMPLES)]))


def score_one(text, planted, tok):
    """Row for one answer. An unparsable answer counts as no flags and a wrong decision (the user got nothing usable)."""
    codes, dec = parse(text)
    bad = codes is None or dec is None
    flags = set() if bad else codes
    handled = set(K.CODES) - set(planted)
    return {"recall": len(flags & set(planted)) / len(planted) if planted else None,
            "hold": float(dec == "HOLD") if planted else None,
            "pass": float(dec == "SHIP" and not bad) if not planted else None,
            "fa": len(flags & handled) / len(handled), "unparsed": float(bad), "words": len(text.split()), "tokens": tok}


def score(arm):
    """Per-scenario rows (means over samples; None where undefined) for an arm, plus the number of missing answers."""
    key = {k["id"]: k for k in json.loads((D / "key.json").read_text())}
    rows, miss = [], 0
    for s in json.loads((D / "scenarios_held.json").read_text()):
        rs = []
        for k in range(SAMPLES):
            p = D / "outputs" / arm / f"{s['id']}_{k}.txt"
            if p.exists():
                rs.append(score_one(p.read_text(), key[s["id"]]["planted"], int(p.with_suffix(".tok").read_text())))
            else:
                miss += 1
        if rs:
            rows.append({"id": s["id"], "planted": len(key[s["id"]]["planted"]), **{m: (None if rs[0][m] is None else sum(r[m] for r in rs) / len(rs)) for m in rs[0]}})
    return rows, miss


def paired(a, b, n=10000, seed=1):
    assert len(a) == len(b), "unpaired arms"
    d = [x - y for x, y in zip(a, b)]
    return sum(d) / len(d), *R.boot(d, n, seed)


def verdict(S, a, base, miss):
    """The preregistered keep rule for arm a against arm base; returns (checks, label)."""
    col = lambda arm, m: [r[m] for r in S[arm] if r[m] is not None]
    pair = lambda m: paired(col(a, m), col(base, m))
    rec, fa, ps = pair("recall"), pair("fa"), pair("pass")
    mean = lambda arm, m: sum(col(arm, m)) / len(col(arm, m))
    checks = {f"1 recall diff CI lower > 0 ({rec[0]:+.3f} [{rec[1]:+.3f}, {rec[2]:+.3f}])": rec[1] > 0,
              f"2 false-alarm diff CI upper <= +{MARGIN_FA} ({fa[0]:+.3f} [{fa[1]:+.3f}, {fa[2]:+.3f}])": fa[2] <= MARGIN_FA,
              f"3 benign correct-pass diff CI lower >= {NONINF_PASS} ({ps[0]:+.3f} [{ps[1]:+.3f}, {ps[2]:+.3f}])": ps[1] >= NONINF_PASS,
              f"4 mean output tokens {mean(a, 'tokens'):.0f} <= {TOKENS_X} x {mean(base, 'tokens'):.0f}": mean(a, "tokens") <= TOKENS_X * mean(base, "tokens"),
              f"5 unparsed {mean(a, 'unparsed'):.3f} and {mean(base, 'unparsed'):.3f} <= {MAX_UNPARSED}, missing answers {miss[a]}+{miss[base]} = 0":
                  max(mean(a, "unparsed"), mean(base, "unparsed")) <= MAX_UNPARSED and miss[a] + miss[base] == 0}
    label = "WIN" if all(checks.values()) else "LOSS" if rec[2] < 0 else "NOT A WIN"
    return checks, label


def report():
    S, miss, lines = {}, {}, []
    for a in ARMS:
        S[a], miss[a] = score(a)
        c = lambda m: [r[m] for r in S[a] if r[m] is not None]
        ci = lambda m: "%.3f [%.3f, %.3f]" % ((sum(c(m)) / len(c(m)),) + R.boot(c(m)))
        lines.append(f"{a}: n={len(S[a])} (flawed {len(c('recall'))}, benign {len(c('pass'))}) recall={ci('recall')} hold_on_flawed={ci('hold')} "
                     f"ship_on_benign={ci('pass')} | false_alarm={ci('fa')} unparsed={sum(c('unparsed')) / len(c('unparsed')):.3f} words={sum(c('words')) / len(c('words')):.0f} "
                     f"tokens={sum(c('tokens')) / len(c('tokens')):.0f} missing={miss[a]}")
    for base in ("RIVAL", "NONE"):
        checks, label = verdict(S, "V0", base, miss)
        lines += [f"V0 vs {base}:"] + [f"  [{'x' if ok else ' '}] {k}" for k, ok in checks.items()] + [f"-> {label} (V0 against {base})"]
    (D / "report_held.txt").write_text("\n".join(lines) + "\n")
    (D / "per_scenario_held.json").write_text(json.dumps(S, indent=1) + "\n")
    print("\n".join(lines))


def freeze(phase):
    fz = D / "SHA256-frozen.txt"
    if phase == "scen":
        with open(fz, "a") as f:
            f.write(f"{sha(D / 'scenarios_held.json')}  docs/bench/growth-outcome-1019/scenarios_held.json\n")
        ledger(event="scenarios_frozen", sha256=sha(D / "scenarios_held.json"))
    else:
        names = ["PREREGISTERED.md", "key.py", "key.json", "bench.py", "prompts/task.txt", "prompts/writer_brief.txt", "prompts/V0.md", "prompts/RIVAL.txt", "prompts/NONE.txt"]
        fz.write_text("".join(f"{sha(D / n)}  docs/bench/growth-outcome-1019/{n}\n" for n in names))
        ledger(event="preregistered", sha256_of="SHA256-frozen.txt", sha256=sha(fz))


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"scen": lambda: scen(), "run": lambda: run(args), "report": report, "freeze": lambda: freeze(args[0])}[cmd]()
