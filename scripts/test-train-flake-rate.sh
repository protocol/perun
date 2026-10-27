#!/usr/bin/env bash
# Regression tests for the train flake fixes: (1) train_flake.sh blames a flake only when it fails every one of N solo
# re-runs (seeded 1000-trial simulation on the real script) and train_land lands a FLAKE only if it also flakes on the base
# (seeded regression-lands simulation, p=0.5, 2/3, 0.9), (2) merge_train.py caches the verdict per git tree SHA and
# re-runs a failing gate on a short --gate-backoff, (3) the keystone `contains` helper passes under a TMPDIR that differs
# from the OS user temp dir (a bare `mktemp -d` ignores TMPDIR on macOS). Stubs only; writes only under $WORK.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SC="$ROOT/.claude/skills/agentic-delivery/scripts"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-train-flake-rate.XXXXXX")"
trap '[ -n "$WORK" ] && rm -r "$WORK" 2>/dev/null' EXIT
# test-ci-gates.sh exports GIT_AUTHOR_*/GIT_COMMITTER_*; those override the selftest's own `git -c user.email=<owner>` and
# break its keystone owner-grant case, so run the selftests without them.
unset GIT_AUTHOR_NAME GIT_AUTHOR_EMAIL GIT_COMMITTER_NAME GIT_COMMITTER_EMAIL
pass=0 fail=0
ok() { if [ "$1" -eq 0 ]; then echo "PASS  $2"; pass=$((pass + 1)); else echo "FAIL  $2"; fail=$((fail + 1)); fi; }

# --- (1) seeded simulation: p = 1/3 flake, 1000 trials. RERUN_CMD pops one pre-drawn outcome (F|P) per call. ---
cat >"$WORK/rr.sh" <<'STUB'
r=$(head -c1 "$WORK/seq"); tail -c +2 "$WORK/seq" >"$WORK/seq.n"; mv "$WORK/seq.n" "$WORK/seq"; [ "$r" != F ]
STUB
export WORK RERUN_CMD="bash $WORK/rr.sh" FLAKE_INVOCATION=x
echo x >"$WORK/id"
sim=$(python3 -I - "$SC/train_flake.sh" "$WORK" <<'PY'
import random, subprocess, sys
script, work = sys.argv[1:3]
rng, trials, real, old_real = random.Random(20261016), 1000, 0, 0
verdict = {}  # the script is a pure function of the 3 pre-drawn outcomes: run each of the 8 distinct draws once, count the rest
def triage(seq):
    if seq not in verdict:
        open(f"{work}/seq", "w").write(seq)
        verdict[seq] = subprocess.run(["bash", script, f"{work}/id"], capture_output=True, text=True).stdout
    return verdict[seq]
for _ in range(trials):
    seq = "".join("F" if rng.random() < 1 / 3 else "P" for _ in range(3))
    real += triage(seq).startswith("REAL")
    old_real += seq.count("F") >= 2  # the retired 2-of-3 rule on the same draws
print(trials, real, old_real)
PY
)
read -r trials real old_real <<<"$sim"
echo "simulation: $trials trials, new rule false-blame $real, old 2-of-3 rule would blame $old_real"
[ "${trials:-0}" -ge 1000 ] && [ "$real" -le $((trials * 55 / 1000)) ] && [ "$old_real" -ge $((trials * 20 / 100)) ]
ok $? "train_flake: a 1-in-3 flake is blamed <= 5.5% of 1000 seeded trials (all-N rule ~3.7%; the 2-of-3 rule blamed >= 20% on the same draws)"

# --- (1b) regression-lands rate: train_land lands a FLAKE verdict only if the test also fails >= 1 of 3 solo runs on the base
# (train_flake.sh --base with FLAKE_REAL_AT=1). A regression is clean on the base; p = its per-run failure rate. Rates are
# conditional on the union gate having failed. old = the retired 2-of-3 rule (FLAKE when <= 1 of 3 solo runs fail, then lands).
# The script is a pure function of the pre-drawn outcomes, so each distinct draw (8 triage, 8 base) is run once and cached; the 300 trials are still counted.
cat >"$WORK/bb.sh" <<'STUB'
r=$(head -c1 "$WORK/bseq"); tail -c +2 "$WORK/bseq" >"$WORK/bseq.n"; mv "$WORK/bseq.n" "$WORK/bseq"; [ "$r" != F ] || { echo "FAIL x"; exit 1; }
STUB
land=$(python3 -I - "$SC/train_flake.sh" "$WORK" <<'PY'
import os, random, subprocess, sys
script, work = sys.argv[1:3]
rng, trials = random.Random(20261016), 300
def draw(p): return "".join("F" if rng.random() < p else "P" for _ in range(3))
tri, base = {}, {}
def lands(seq, bseq):  # the real triage, then the real base check, as train_land runs them
    if seq not in tri:
        open(f"{work}/seq", "w").write(seq)
        tri[seq] = subprocess.run(["bash", script, f"{work}/id"], capture_output=True, text=True).stdout.startswith("FLAKE")
    if not tri[seq]:
        return False
    if bseq not in base:
        open(f"{work}/bseq", "w").write(bseq)
        env = dict(os.environ, RERUN_CMD=f"bash {work}/bb.sh", FLAKE_REAL_AT="1")
        base[bseq] = subprocess.run(["bash", script, "--base", "x"], env=env, capture_output=True).returncode == 0
    return base[bseq]
for name, p in (("0.5", 0.5), ("2/3", 2 / 3), ("0.9", 0.9)):
    old = new = 0
    for _ in range(trials):
        seq = draw(p)
        old += seq.count("F") < 2
        new += lands(seq, "PPP")  # regression: never fails on the base
    print("reg", name, trials, old, new)
print("flake", trials, sum(lands(draw(1 / 3), draw(1 / 3)) for _ in range(trials)))  # genuine flake, flaky on the base too
PY
)
while read -r kind name n old new; do
  [ "$kind" = reg ] || continue
  echo "regression p=$name: lands $old/$n old 2-of-3 rule, $new/$n new rule"
  [ "$new" -le "$old" ] && [ "$new" -eq 0 ]; ok $? "regression p=$name lands <= the old rule's rate ($old/$n), and never when clean on the base ($new/$n)"
done <<<"$land"
read -r _ n fl <<<"$(grep '^flake' <<<"$land")"
echo "genuine flake (p=1/3 solo and on the base) lands $fl/$n"
[ "${fl:-0}" -ge $((n * 60 / 100)) ]; ok $? "a genuine flaky-on-base test still lands (>= 60% of $n)"

printf 'FFF' >"$WORK/seq"; bash "$SC/train_flake.sh" "$WORK/id" >"$WORK/o" 2>/dev/null; rc=$?
[ $rc -eq 1 ] && grep -q '^REAL x' "$WORK/o"; ok $? "train_flake: fails all 3 solo re-runs -> REAL"
printf 'FFP' >"$WORK/seq"; bash "$SC/train_flake.sh" "$WORK/id" >"$WORK/o" 2>/dev/null; rc=$?
[ $rc -eq 0 ] && grep -q '^FLAKE x (failed 2 of 3 alone)' "$WORK/o"; ok $? "train_flake: 2 failures then a pass -> FLAKE (no longer REAL)"
printf 'FFFFP' >"$WORK/seq"; FLAKE_RUNS=5 bash "$SC/train_flake.sh" "$WORK/id" >"$WORK/o" 2>/dev/null; rc=$?
[ $rc -eq 0 ] && grep -q '^FLAKE x' "$WORK/o"; ok $? "train_flake: N is configurable (FLAKE_RUNS=5: 4 of 5 failures is FLAKE)"
printf 'FFFFF' >"$WORK/seq"; FLAKE_RUNS=5 bash "$SC/train_flake.sh" "$WORK/id" >"$WORK/o" 2>/dev/null; rc=$?
[ $rc -eq 1 ] && grep -q '^REAL x' "$WORK/o"; ok $? "train_flake: FLAKE_RUNS=5 and all 5 fail -> REAL"
for i in 1 2; do printf 'FFP' >"$WORK/seq"; bash "$SC/train_flake.sh" "$WORK/id" >"$WORK/d$i" 2>/dev/null; done
cmp -s "$WORK/d1" "$WORK/d2" && [ -s "$WORK/d1" ]; ok $? "train_flake: two runs of the same outcome sequence give the same verdict"
printf 'PFF' >"$WORK/seq"; bash "$SC/train_flake.sh" "$WORK/id" >/dev/null 2>&1
[ "$(wc -c <"$WORK/seq")" -eq 2 ]; ok $? "train_flake: stops at the first pass (a flake costs one re-run)"

# --- (2) verdict cache + gate backoff, on merge_train's own fake forge (no network, no repo) ---
cache=$(python3 -I - "$SC" "$WORK" <<'PY'
import importlib.util, io, os, sys
sc, work = sys.argv[1:3]
spec = importlib.util.spec_from_file_location("merge_train", os.path.join(sc, "merge_train.py"))
mt = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mt)
f = mt.FakeForge(3)
f.bad = {3}
buf = io.StringIO()
rc = mt.run(["verify", "--base", "main", "--verify-cmd", "t", "--state", os.path.join(work, "c.json"),
             "--gate-backoff", "2"], runner=f, out=buf, sleep=f.sleeps.append)
out = buf.getvalue()
checks = {
    "green on #1,#2": rc == mt.OK and "GREEN base=B0 members=#1,#2" in out,
    "rebuilt union #1,#2 hit the cache": "CACHED union #1,#2" in out,
    "no tree tested twice (union x3 retries, base, #1, #1,#2)": f.gates == [(1, 2, 3)] * 3 + [(), (1,), (1, 2)],
    "gate retries sleep on --gate-backoff, not --backoff 30": f.sleeps == [2, 4],
}
for name, good in checks.items():
    print(("PASS  " if good else "FAIL  ") + "verdict cache: " + name)
if not all(checks.values()):
    print(out)
PY
)
echo "$cache"
pass=$((pass + $(grep -c '^PASS' <<<"$cache"))); fail=$((fail + $(grep -c '^FAIL' <<<"$cache")))
[ "$(grep -c '^PASS' <<<"$cache")" -eq 4 ] || fail=$((fail + 1))
python3 -I "$SC/merge_train.py" --selftest 2>&1 | tail -1 | grep -q 'SELFTEST OK'; ok $? "merge_train --selftest passes"

# --- (3) keystone: `mktemp -d` with no template must not be relied on (macOS ignores TMPDIR there) ---
mkdir "$WORK/shim"
real=$(command -v 'mktemp')  # quoted: a name lookup, not a bare call (scripts/test-mktemp-tmpdir.sh)
printf '#!/bin/sh\ncase "$*" in -d|"") echo "mktemp: bare template refused" >&2; exit 1;; esac\nexec %s "$@"\n' "$real" >"$WORK/shim/mktemp"
chmod +x "$WORK/shim/mktemp"
PATH="$WORK/shim:$PATH" python3 -I "$SC/merge_train.py" --selftest 2>&1 | tail -1 | grep -q 'SELFTEST OK'
ok $? "merge_train keystone: passes when a template-less mktemp is unusable (TMPDIR honored)"

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
