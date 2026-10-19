#!/usr/bin/env python3
"""Generator and answer key for the growth-analytics computed-error bench (see PREREGISTERED.md). Deterministic; no model writes anything.

Every scenario is built from raw numbers (arm counts, sessions, orders, a per-device table, a daily lift series, dates, design inputs). A planted error is only
visible by arithmetic on those numbers; no phrase names an error. The gold set is COMPUTED from the numbers by `truth()` and `make()` refuses any scenario where
it differs from the planted set or lies in a gray zone, so the key cannot drift from the text.

usage: key.py tune | held LEVEL | render held      (tune: key_tune.json + scenarios_tune.json; held: key_held.json, then scenarios_held.json from it)
"""
import json, math, random, sys
from datetime import date, timedelta
from pathlib import Path

D = Path(__file__).resolve().parent
CODES = ("SRM", "PEEK", "POWER", "SIMPSON", "DENOM", "NOVELTY")
SEEDS = {"tune": 2019, "held": 3019}
# Difficulty level 0 (easy) to 3 (hard): how close a planted error sits to its detection threshold; sound scenarios sit near-symmetrically on the other side.
# Level 2 also hides the per-arm user totals (sum the per-device users); level 3 also states the planned end date instead of the planned duration.
SRM_BAD, POWER_BAD, POWER_OK = (6.0, 4.8, 4.0, 3.6), (0.30, 0.45, 0.60, 0.70), (1.9, 1.5, 1.25, 1.12)  # |z| of the arm-size gap; users per arm / users required
DENOM_BAD, SIMP_E, SIMP_G = (0.80, 0.86, 0.90, 0.93), (0.08, 0.06, 0.045, 0.03), (0.06, 0.045, 0.03, 0.02)  # sessions-per-user ratio; in-segment loss; pooled gain
PEEK_BAD, NOV_BAD = (0.45, 0.55, 0.65, 0.72), (0.12, 0.18, 0.25, 0.30)  # share of planned days run; late-days/early-days lift ratio (before noise)
NAMES = ("Ovenly", "Mealbox", "Booklark", "Skipass", "Wrenchly", "Fernwick", "Streakly", "Queuely", "Pawfinder", "Roomwise", "Pulsefit", "Castshelf",
         "Rentwise", "Pageturn", "Tipsy", "Galleria", "Taxwise", "Pausebrew", "Threadly", "Printbox", "Profilo", "Seatly", "Savorly", "Runfund")
CHANGES = ("bakery checkout button redesign", "meal-kit signup form", "library app renewal reminder", "ski-resort lift-pass upsell banner",
           "bike-repair booking page", "plant-nursery product page", "language-learning streak prompt", "concert-ticket waiting-room page",
           "pet-adoption search filter", "hotel-booking price display", "fitness-app onboarding flow", "podcast-app recommendation shelf",
           "car-rental insurance add-on", "bookshop newsletter popup", "food-delivery tip selector", "museum membership page",
           "tax-filing helper checklist", "coffee-subscription pause button", "gardening-forum reply box", "photo-printing cart reminder",
           "streaming-service profile picker", "train-ticket seat map", "recipe-site save button", "charity-run registration page")
Z_SUM = 1.959964 + 0.841621  # two-sided alpha 0.05 plus 80% power


def n_required(p, mde):
    """Users per arm for a two-proportion test (alpha 0.05 two-sided, power 80%) to detect a relative lift `mde` on baseline p."""
    p2 = p * (1 + mde)
    return Z_SUM ** 2 * (p * (1 - p) + p2 * (1 - p2)) / (p2 - p) ** 2


def lift(a, b):
    return b / a - 1


def series_ratio(s):
    return (sum(s[-3:]) / 3) / (sum(s[:3]) / 3)


def truth(x):
    """Planted set recomputed from the numbers a reader sees; None where a value sits in a gray zone no scenario may occupy."""
    n, out = x["n"], set()
    z = abs(n["t"] - n["c"]) / math.sqrt(n["t"] + n["c"])
    if z >= 3.5: out.add("SRM")
    elif z > 1.5: return None
    r = min(n["c"], n["t"]) / n_required(x["p"], x["mde"])
    if r < 0.9: out.add("POWER")
    elif r < 1.05: return None
    days = (date.fromisoformat(x["end"]) - date.fromisoformat(x["start"])).days / x["planned"]
    if days < 0.8: out.add("PEEK")
    elif days < 1.0: return None
    rep, o = x["reported"], x["orders"]
    if abs(rep["c"] - 100 * o["c"] / x["sessions"]["c"]) < abs(rep["c"] - 100 * o["c"] / n["c"]): out.add("DENOM")
    sl = [lift(x["seg"][s]["c"][1] / x["seg"][s]["c"][0], x["seg"][s]["t"][1] / x["seg"][s]["t"][0]) for s in ("desktop", "mobile")]
    pooled = lift(o["c"] / n["c"], o["t"] / n["t"])
    if pooled > 0 and max(sl) < -0.01: out.add("SIMPSON")
    elif min(sl) < 0.01 or pooled < 0.01: return None
    q = series_ratio(x["series"])
    if q < 0.5: out.add("NOVELTY")
    elif q < 0.65 or q > 1.5: return None
    return out


def build(rng, planted, lv):
    P, jit = set(planted), lambda v: v * rng.uniform(0.97, 1.03)
    p, mde = rng.choice((0.03, 0.04, 0.05, 0.06, 0.08)), rng.choice((0.05, 0.08, 0.10))
    N = 2 * round((jit(POWER_BAD[lv]) if "POWER" in P else jit(POWER_OK[lv])) * n_required(p, mde))
    z = rng.choice((-1, 1)) * (jit(SRM_BAD[lv]) if "SRM" in P else rng.uniform(0.1, 1.1))
    nc = (N - round(z * math.sqrt(N))) // 2
    n = {"c": nc, "t": N - nc}
    c, R = rng.uniform(0.35, 0.5), rng.uniform(2.5, 3.5)
    pm = p / (c * R + 1 - c)
    if "SIMPSON" in P:
        e, g = -jit(SIMP_E[lv]), jit(SIMP_G[lv])
        t = ((1 + g) * (c * (R - 1) + 1) / (1 + e) - 1) / (R - 1)  # desktop share in treatment that makes the pooled lift +g
    else:
        e, t = rng.uniform(0.04, 0.08), c
    seg = {}
    for s, k in (("desktop", R), ("mobile", 1.0)):
        sh = {"desktop": (c, t), "mobile": (1 - c, 1 - t)}[s]
        uc, ut = round(sh[0] * n["c"]), round(sh[1] * n["t"])
        seg[s] = {"c": [uc, round(uc * pm * k)], "t": [ut, round(ut * pm * k * (1 + e))]}
    orders = {a: sum(seg[s][a][1] for s in seg) for a in "ct"}
    sc = rng.uniform(1.25, 1.5)
    ratio = jit(DENOM_BAD[lv]) if "DENOM" in P else rng.uniform(0.92, 1.08)
    sess = {"c": round(n["c"] * sc), "t": round(n["t"] * sc * ratio)}
    den = sess if "DENOM" in P else n
    rc, rt = (round(100 * orders[a] / den[a], 3) for a in "ct")
    m = round(100 * lift(rc, rt), 1)
    planned = rng.choice((14, 21, 28))
    days = max(6, round(jit(PEEK_BAD[lv]) * planned)) if "PEEK" in P else planned + rng.choice((0, 1, 2))
    start = date(2026, 1, 5) + timedelta(rng.randrange(300))
    if "NOVELTY" in P:
        lo, hi = 0.0, 3.0
        for _ in range(60):  # solve the decay rate k so the noise-free late/early lift ratio hits the target
            k = (lo + hi) / 2
            b = [math.exp(-k * i) for i in range(days)]
            lo, hi = (k, hi) if series_ratio(b) > jit(NOV_BAD[lv]) else (lo, k)
        mb = sum(b) / days
        s = [m * v / mb for v in b]
    else:
        s = [m] * days
    noise = [rng.gauss(0, 0.12 * abs(m)) for _ in range(days)]
    s = [round(v + w - sum(noise) / days, 1) for v, w in zip(s, noise)]
    return {"p": p, "mde": mde, "n": n, "sessions": sess, "orders": orders, "seg": seg, "reported": {"c": rc, "t": rt, "lift": m, "p": pval(orders, den)},
            "start": start.isoformat(), "end": (start + timedelta(days)).isoformat(), "planned": planned, "series": s}


def pval(o, den):
    pc, pt = o["c"] / den["c"], o["t"] / den["t"]
    pp = (o["c"] + o["t"]) / (den["c"] + den["t"])
    z = (pt - pc) / math.sqrt(pp * (1 - pp) * (1 / den["c"] + 1 / den["t"]))
    return round(math.erfc(abs(z) / math.sqrt(2)), 4)


def make(split, lv, per=None):
    """Scenarios for one split at one level: per planted-count stratum (0 to 3 errors), `per` scenarios; tune uses 12, held 24."""
    per = per or {"tune": 12, "held": 24}[split]
    rng, out = random.Random(f"{SEEDS[split]}-{lv}"), []
    for k in (0, 1, 2, 3):
        for _ in range(per):
            planted = sorted(rng.sample(CODES, k), key=CODES.index)
            for _try in range(200):
                x = build(rng, planted, lv)
                if truth(x) == set(planted): break
            else:
                raise RuntimeError("no consistent scenario drawn")
            i = len(out) + 1
            out.append({"id": f"{'t' + str(lv) if split == 'tune' else 'h'}{i:03d}", "level": lv, "name": NAMES[(i - 1) % 24], "change": CHANGES[(i * 7 + lv) % 24],
                        "planted": planted, "data": x})
    return out


def f(v):
    return f"{v:,}"


def render(it):
    """The readout text a reviewer sees: raw numbers only, no word that names an error."""
    x, s = it["data"], it["data"]["seg"]
    seg = "\n".join(f"  {d}: control {f(s[d]['c'][0])} users / {f(s[d]['c'][1])} orders, treatment {f(s[d]['t'][0])} users / {f(s[d]['t'][1])} orders" for d in s)
    r, lv = x["reported"], it["level"]
    plan = (date.fromisoformat(x["start"]) + timedelta(x["planned"])).isoformat()
    dates = (f"Dates: started {x['start']}; planned end {plan}; final readout {x['end']}." if lv >= 3 else
             f"Dates: started {x['start']}; planned duration {x['planned']} days; final readout {x['end']}.")
    arms = "\n".join(f"  {a}: " + (f"{f(x['n'][k])} users, " if lv < 2 else "") + f"{f(x['sessions'][k])} sessions, {f(x['orders'][k])} orders" for a, k in (("control", "c"), ("treatment", "t")))
    return (f"{it['name']} experiment readout: {it['change']}. Metric: order conversion rate. Users were randomized by user id, 50/50 allocation.\n"
            f"Design: alpha 0.05 two-sided, power 80%, baseline rate {x['p'] * 100:.1f}%, target relative lift {x['mde'] * 100:.0f}%.\n"
            f"{dates}\n"
            f"Arms:\n{arms}\n"
            f"By device:\n{seg}\n"
            f"Reported conversion rate: control {r['c']}%, treatment {r['t']}%; relative lift {r['lift']}% (p = {r['p']}).\n"
            f"Daily relative lift in %, day 1 to day {len(x['series'])}: {', '.join(str(v) for v in x['series'])}.\n"
            f"Projection: the team applies the reported lift to the next twelve months of traffic. Recommendation: roll out to everyone.")


def scenarios(key):
    return [{"id": k["id"], "split": "tune" if k["id"][0] == "t" else "held", "spec": render(k)} for k in key]


def write(name, obj):
    (D / name).write_text(json.dumps(obj, indent=1) + "\n")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a[0] == "tune":
        key = [k for lv in range(4) for k in make("tune", lv)]
        write("key_tune.json", key), write("scenarios_tune.json", scenarios(key))
    elif a[0] == "held":
        write("key_held.json", make("held", int(a[1])))
    else:
        write("scenarios_held.json", scenarios(json.loads((D / "key_held.json").read_text())))
