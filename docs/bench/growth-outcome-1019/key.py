#!/usr/bin/env python3
"""Answer key for the growth-analytics outcome bench (see PREREGISTERED.md). Deterministic: `key.py` writes key.json from a fixed seed.

Each scenario lists, for every analysis-error category, either a planted error (polarity "+") or an explicitly sound practice ("-"), as a verbatim anchor
phrase the readout writer must include. Gold: flag exactly the planted categories; DECISION is HOLD iff at least one is planted, else SHIP. The key
exists, and is hashed, before any scenario is written and before any arm answers."""
import json, random
from pathlib import Path

D = Path(__file__).resolve().parent
CODES = ("SRM", "PEEK", "POWER", "SIMPSON", "DENOM", "NOVELTY")
ANCHORS = {  # code -> polarity -> two verbatim phrases (variant 0 states the error plainly, variant 1 describes only the mechanism)
    "SRM": {"+": ("the arms received 52,300 and 47,700 users against a planned 50/50 split", "control got 60,400 visitors and treatment 50,100 under a planned even split"),
            "-": ("the arms received 50,080 and 49,920 users against a planned 50/50 split", "control got 50,200 visitors and treatment 50,100 under a planned even split")},
    "PEEK": {"+": ("the team checked the dashboard every day and stopped the test the first day p fell below 0.05", "the test was ended early, on the day the p-value first crossed 0.05 after daily looks"),
             "-": ("the stopping rule was set in advance and the result was read once, at the planned end date", "there was a single analysis at the planned end date, with no early looks")},
    "POWER": {"+": ("only 120 users were enrolled per arm and no power calculation was done", "each arm has 120 users and nobody sized the test for the lift it reports"),
              "-": ("each arm got 25,000 users, the size a power calculation required for the target lift", "a power calculation set 25,000 users per arm and both arms reached it")},
    "SIMPSON": {"+": ("overall treatment wins, but treatment loses within both the mobile segment and the desktop segment", "treatment leads in the pooled total yet trails within each platform because it drew far more of the high-converting desktop traffic"),
                "-": ("treatment wins overall and also wins within both the mobile segment and the desktop segment", "treatment leads in the pooled total and within each platform, with the same traffic mix in both arms")},
    "DENOM": {"+": ("conversion is computed per page view although users were the unit randomized", "conversions are divided by sessions while assignment was by user, and heavy users log many sessions"),
              "-": ("conversion is computed per randomized user, the unit of assignment", "the denominator is users, the same unit that was randomized")},
    "NOVELTY": {"+": ("the lift is concentrated in the first three days and fades each day after, yet the readout projects the day-one lift for a full year", "the lift was 12% on day one and 1% by day fourteen, and the forecast uses the 12%"),
                "-": ("the lift is stable across all four weeks with no fade after the first days", "the daily lift held at about 3% from day one through day twenty-eight")},
}
STRAY = {  # words that would plant or cancel a category outside its anchor: a readout containing one (after anchors are removed) is rejected
    "SRM": r"ratio|mismatch|50/50|even split|planned split", "PEEK": r"peek|\bearly\b|\bstopp|interim|sequential|p-value|planned end",
    "POWER": r"power|sample size|\bsized?\b|too small|enough users", "SIMPSON": r"simpson|paradox|segment|pooled|confound|platform",
    "DENOM": r"denominator|per page view|per session|\bsessions?\b|randomi[sz]|unit of", "NOVELTY": r"novelty|\bfad(e|es|ing)\b|decay|wear|stable|steady|ramp"}
GENERIC = r"\bhowever\b|\bnote\b|caution|double-?checked|\bverified|re-?ran|re-?computed|\bmatched\b|per-user|sanity|reassur"  # hedges that would soften or cancel any anchor
DOMAINS = ("a bakery checkout button redesign", "a meal-kit signup form", "a library app renewal reminder", "a ski-resort lift-pass upsell banner",
           "a bike-repair booking page", "a plant-nursery product page", "a language-learning streak prompt", "a concert-ticket waiting-room page",
           "a pet-adoption search filter", "a hotel-booking price display", "a fitness-app onboarding flow", "a podcast-app recommendation shelf",
           "a car-rental insurance add-on", "a bookshop newsletter popup", "a food-delivery tip selector", "a museum membership page",
           "a tax-filing helper checklist", "a coffee-subscription pause button", "a gardening-forum reply box", "a photo-printing cart reminder",
           "a streaming-service profile picker", "a train-ticket seat map", "a recipe-site save button", "a charity-run registration page")
STRATA = (0, 1, 2, 3)  # planted errors per scenario; one of each per domain: 24 domains x 4 = 96 scenarios, 24 benign controls


def make():
    rng, out = random.Random(1019), []
    for d in DOMAINS:
        for k in STRATA:
            planted = sorted(rng.sample(CODES, k), key=CODES.index)
            req = [ANCHORS[c]["+" if c in planted else "-"][rng.randrange(2)] for c in CODES]
            out.append({"id": f"g{len(out) + 1:03d}", "domain": d, "planted": planted, "required": req})
    return out


if __name__ == "__main__":
    (D / "key.json").write_text(json.dumps(make(), indent=1) + "\n")
