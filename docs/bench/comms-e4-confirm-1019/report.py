#!/usr/bin/env python3
"""r2 report: accuracy (r1's scorer), regex invented rate, judged real-fabrication rate, words, and the preregistered keep rule for E4 against V0.
usage: report.py held ARM..  |  report.py r1 ARM..   (r1 = descriptive re-score of comms-outcome-1019 held outputs; BASE=V0)
A scenario's real-fab rate is the share of its 3 samples with at least one judge-labelled fabricated figure. Writes report_held.txt, per_scenario_held.json (or *_r1)."""
import concurrent.futures as cf, json, os, sys
sys.dont_write_bytecode = True
import fabjudge as f  # noqa: E402

b, D = f.b, f.D
MARGIN, WORDS_X = 0.02, 1.25   # preregistered: real-fab difference CI upper bound <= +0.02; E4 words <= 1.25 x V0


def rows(split, arm, out_dir):
    """b.score rows (accuracy etc.) plus per-scenario real_fab and the count of flagged figures the judge left unlabelled."""
    b.D = out_dir
    try:
        S, miss = b.score("held", arm)
        sc = b.load("held")
    finally:
        b.D = D
    def fab(a):
        s, k = a
        p = out_dir / "outputs/held" / arm / f"{s['id']}_{k}.txt"
        return f.real_fab(p.read_text(), s["prompt"]) if p.exists() else (0, 0)
    with cf.ThreadPoolExecutor(b.JOBS) as ex:
        r = list(ex.map(fab, [(s, k) for s in sc for k in range(b.SAMPLES)]))
    for i, row in enumerate(S):
        row["real_fab"] = sum(x[0] for x in r[i * 3:i * 3 + 3]) / 3
    return S, miss, sum(x[1] for x in r)


def main(which, arms, base="V0"):
    out_dir = D if which == "held" else f.R1
    S, lines, unl = {}, [], {}
    for a in arms:
        S[a], miss, unl[a] = rows(which, a, out_dir)
        m = lambda key: sum(r[key] for r in S[a]) / len(S[a])
        lines.append(f"{a}: n={len(S[a])} accuracy={m('acc'):.3f} " + " ".join(f"{r}={sum(x['by_reader'][r] for x in S[a]) / len(S[a]):.3f}" for r in b.READERS)
                     + f" | dropped_rate={m('dropped'):.3f} regex_invented_rate={m('invented'):.3f} real_fab_rate={m('real_fab'):.3f} words={m('words'):.0f} missing_grades={miss} unlabelled_figures={unl[a]}")
    P = lambda a, key: [r[key] for r in S[a]]
    for a in arms:
        if a != base:
            c = {key: b.paired(P(a, key), P(base, key)) for key in ("acc", "invented", "real_fab")}
            lines.append(f"{a} - {base}: accuracy {c['acc'][0]:+.3f} 95% CI [{c['acc'][1]:+.3f}, {c['acc'][2]:+.3f}] | real_fab {c['real_fab'][0]:+.3f} [{c['real_fab'][1]:+.3f}, {c['real_fab'][2]:+.3f}] | regex_invented {c['invented'][0]:+.3f} [{c['invented'][1]:+.3f}, {c['invented'][2]:+.3f}]")
    if "E4" in S and base in S and which == "held":
        acc, fab = b.paired(P("E4", "acc"), P(base, "acc")), b.paired(P("E4", "real_fab"), P(base, "real_fab"))
        w4, w0 = sum(P("E4", "words")) / len(S["E4"]), sum(P(base, "words")) / len(S[base])
        ok = dict(accuracy_ci_lower_above_0=acc[1] > 0, real_fab_ci_upper_within_margin=fab[2] <= MARGIN, words_within_budget=w4 <= WORDS_X * w0,
                  judge_complete=unl["E4"] == 0 and unl[base] == 0)
        lines.append(f"KEEP RULE E4 vs {base}: {ok} -> " + ("KEEP" if all(ok.values()) else "REVERT"))
    txt = "\n".join(lines)
    print(txt)
    (D / f"report_{which}.txt").write_text(txt + "\n")
    (D / f"per_scenario_{which}.json").write_text(json.dumps(S, indent=1) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2:], os.environ.get("BASE", "V0"))
