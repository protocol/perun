#!/usr/bin/env python3
"""Computed-error outcome bench for growth-analytics against a rival and no skill (see PREREGISTERED.md). Free PCSS models only; no claude -p.

usage: bench.py tune [LEVEL..] | calibrate | freeze pre | gen | freeze held | run ARM.. | report        ARM = V0 | RIVAL | NONE   (JOBS=8 env: threads)

tune runs the NONE arm only on the tune split (key.py tune); calibrate prints NONE recall per level. After the freeze, gen writes the held-out key and readouts
(deterministic, key.py) and run/report score V0, RIVAL and NONE on it. A reviewer answer is scored deterministically against the key: its last `ERRORS:` line
(flagged codes) and `DECISION:` line are parsed and compared with the planted errors. No model writes or grades anything. Tune calls are logged to
tune_ledger.jsonl, held-out calls to ledger.jsonl; every output is cached under outputs/ and never overwritten.
"""
import concurrent.futures as cf, hashlib, json, os, re, subprocess, sys, threading, time, urllib.request
from datetime import datetime, timezone
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D.parents[2] / "scripts"))
sys.path.insert(0, str(D))
import rival_eval as R  # noqa: E402
import key as K  # noqa: E402

GENERATOR, SAMPLES, TEMP = R.GEN_MODEL, 2, 0.7
JOBS = int(os.environ.get("JOBS", 8))
ARMS = ("V0", "RIVAL", "NONE")
MARGIN_FA, NONINF_PASS, TOKENS_X, MAX_UNPARSED = 0.03, -0.15, 1.25, 0.05  # preregistered keep-rule constants
TARGET, RANGE = (0.5, 0.7), (0.4, 0.8)  # NONE recall: calibration target on tune; held-out sanity range (outside it the instrument is uninformative)
_lock = threading.Lock()


def ledger(split="held", **kw):
    now = datetime.now(timezone.utc)
    with _lock, open(D / ("ledger.jsonl" if split == "held" else "tune_ledger.jsonl"), "a") as f:
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


def call(split, model, system, user, temperature, **tag):
    t = time.time()
    try:
        out = chat_usage(model, system, user, temperature)
        ledger(split, event="call", role="answer", model=model, sec=round(time.time() - t, 1), err="", **tag)
        return out
    except RuntimeError as e:
        ledger(split, event="call", role="answer", model=model, sec=round(time.time() - t, 1), err=str(e)[:80], **tag)
        raise


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


def answer(split, arm, sc, k):
    p = D / "outputs" / split / arm / f"{sc['id']}_{k}.txt"
    if p.exists():
        return
    task = (D / "prompts/task.txt").read_text() + sc["spec"]
    try:
        txt, tok = call(split, GENERATOR, (D / "prompts" / ("V0.md" if arm == "V0" else "RIVAL.txt" if arm == "RIVAL" else "NONE.txt")).read_text(), task, TEMP, arm=arm, id=sc["id"], k=k)
    except RuntimeError:
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.with_suffix(".tok").write_text(str(tok))
    p.write_text(txt + "\n")


def run(split, arms, levels=None):
    sc = json.loads((D / f"scenarios_{split}.json").read_text())
    if levels is not None:
        sc = [s for s in sc if int(s["id"][1]) in levels]
    with cf.ThreadPoolExecutor(JOBS) as ex:
        list(ex.map(lambda a: answer(split, *a), [(a, s, k) for a in arms for s in sc for k in range(SAMPLES)]))


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


def score(split, arm, levels=None):
    """Per-scenario rows (means over samples; None where undefined) for an arm, plus the number of missing answers."""
    key = {k["id"]: k for k in json.loads((D / f"key_{split}.json").read_text())}
    rows, miss = [], 0
    for s in json.loads((D / f"scenarios_{split}.json").read_text()):
        if levels is not None and int(s["id"][1]) not in levels:
            continue
        rs = []
        for k in range(SAMPLES):
            p = D / "outputs" / split / arm / f"{s['id']}_{k}.txt"
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
        S[a], miss[a] = score("held", a)
        c = lambda m: [r[m] for r in S[a] if r[m] is not None]
        ci = lambda m: "%.3f [%.3f, %.3f]" % ((sum(c(m)) / len(c(m)),) + R.boot(c(m)))
        lines.append(f"{a}: n={len(S[a])} (flawed {len(c('recall'))}, benign {len(c('pass'))}) recall={ci('recall')} hold_on_flawed={ci('hold')} "
                     f"ship_on_benign={ci('pass')} | false_alarm={ci('fa')} unparsed={sum(c('unparsed')) / len(c('unparsed')):.3f} words={sum(c('words')) / len(c('words')):.0f} "
                     f"tokens={sum(c('tokens')) / len(c('tokens')):.0f} missing={miss[a]}")
    none = sum(r["recall"] for r in S["NONE"] if r["recall"] is not None) / len([r for r in S["NONE"] if r["recall"] is not None])
    for base in ("RIVAL", "NONE"):
        checks, label = verdict(S, "V0", base, miss)
        if not RANGE[0] <= none <= RANGE[1]:
            label = f"UNINFORMATIVE (no-skill recall {none:.3f} outside {RANGE}); would have been {label}"
        lines += [f"V0 vs {base}:"] + [f"  [{'x' if ok else ' '}] {k}" for k, ok in checks.items()] + [f"-> {label} (V0 against {base})"]
    (D / "report_held.txt").write_text("\n".join(lines) + "\n")
    (D / "per_scenario_held.json").write_text(json.dumps(S, indent=1) + "\n")
    print("\n".join(lines))


def calibrate():
    """NONE recall, hold and false-alarm per tune level; writes report_tune.txt."""
    out = []
    for lv in range(4):
        rows, miss = score("tune", "NONE", {lv})
        c = lambda m: [r[m] for r in rows if r[m] is not None]
        mean = lambda m: sum(c(m)) / len(c(m))
        out.append(f"level {lv}: n={len(rows)} NONE recall={mean('recall'):.3f} hold_on_flawed={mean('hold'):.3f} ship_on_benign={mean('pass'):.3f} "
                   f"false_alarm={mean('fa'):.3f} unparsed={mean('unparsed'):.3f} tokens={mean('tokens'):.0f} missing={miss}")
    (D / "report_tune.txt").write_text("\n".join(out) + "\n")
    print("\n".join(out))


def freeze(phase):
    fz, base = D / "SHA256-frozen.txt", "docs/bench/growth-outcome-r2-1019/"
    if phase == "held":
        names = ["key_held.json", "scenarios_held.json"]
        with open(fz, "a") as f:
            f.writelines(f"{sha(D / n)}  {base}{n}\n" for n in names)
        ledger(event="held_frozen", key_sha256=sha(D / "key_held.json"), scenarios_sha256=sha(D / "scenarios_held.json"))
    else:
        names = ["PREREGISTERED.md", "key.py", "bench.py", "calibration.json", "key_tune.json", "scenarios_tune.json", "report_tune.txt", "prompts/task.txt", "prompts/V0.md",
                 "prompts/RIVAL.txt", "prompts/NONE.txt"]
        fz.write_text("".join(f"{sha(D / n)}  {base}{n}\n" for n in names))
        ledger(event="preregistered", sha256_of="SHA256-frozen.txt", sha256=sha(fz))


def gen():
    for a in (["held", str(json.loads((D / "calibration.json").read_text())["level"])], ["render", "held"]):
        subprocess.run([sys.executable, str(D / "key.py"), *a], check=True)


if __name__ == "__main__":
    cmd, args = sys.argv[1], sys.argv[2:]
    {"tune": lambda: run("tune", ["NONE"], {int(a) for a in args} if args else None), "calibrate": calibrate, "gen": gen,
     "run": lambda: run("held", args), "report": report, "freeze": lambda: freeze(args[0])}[cmd]()
