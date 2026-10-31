#!/usr/bin/env bash
# Tests for the privacy gate's one-pass prefilter (cmd_privacy in scripts/ci-gates.sh): one `grep -f` pass over every pattern
# lists the only files the per-pattern greps then read, so a clean tree is read once, not once per pattern. Pins that the hit
# set is unchanged (compared with an independent one-grep-per-pattern oracle, on a tree larger than one 1000-file batch, with
# patterns from the primary and the local sibling banlist), that a clean tree costs one scanning grep per batch, that the
# per-pattern greps never see an unlisted file, that an invalid ERE and a prefilter grep error both fail closed, and that a hit
# in a file whose name holds a newline (a newline-delimited list cannot carry it) still blocks. Offline; a PATH shim logs every
# grep call and then runs the real one. Prints PASS/FAIL per case and "Tests: P/N"; exits non-zero on any failure.
# shellcheck disable=SC2319 # each `ok $?` reads the status of the [ ] check on the line before it, on purpose
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GATES="$ROOT/scripts/ci-gates.sh"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/dcr-test-privacy-prefilter.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT
export GIT_CONFIG_NOSYSTEM=1 GIT_CONFIG_GLOBAL=/dev/null
pass=0 total=0
ok() { total=$((total + 1)); if [ "$1" -eq 0 ]; then pass=$((pass + 1)); echo "PASS  $2"; else echo "FAIL  $2"; fi; }

# grep shim: logs each call's arguments, exits 2 on a `-f` (prefilter) call while $WORK/fail-prefilter exists, else runs the real grep
REAL="$(type -P grep)"
[ -n "$REAL" ] || { echo "FAIL  no grep on PATH"; exit 1; }
mkdir -p "$WORK/shim"
cat >"$WORK/shim/grep" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$*" >>"$WORK/grep.log"
case " \$* " in *" -f "*) [ -e "$WORK/fail-prefilter" ] && exit 2 ;; esac
exec "$REAL" "\$@"
EOF
chmod +x "$WORK/shim/grep"

# run <banlist> <tree>: the gate under the shim; its exit status is returned, its output goes to $WORK/out.log
run() {
  : >"$WORK/grep.log"
  PATH="$WORK/shim:$PATH" bash "$GATES" privacy --banlist "$1" "$2" >"$WORK/out.log" 2>&1
}
# norm <gate log>: one "<k> <file>" line per file of the k-th banned-pattern stanza (the gate prints no pattern numbers: stanzas follow pattern order)
norm() {
  awk '/^BLOCK: a banned pattern matched/ { k++; next } /^  / && k { sub(/^  /, ""); printf "%02d %s\n", k, $0 }' "$1" | sort
}
# oracle <tree> <banlist...>: the pre-prefilter algorithm, one grep per pattern over every file, in norm's format
oracle() {
  local pat k=0 hits
  while IFS= read -r pat; do
    case "$pat" in '' | '#'*) continue ;; esac
    hits="$(find "$1" -type f -print0 | xargs -0 grep -IlE -D skip -e "$pat" --)"
    [ -n "$hits" ] || continue
    k=$((k + 1))
    printf '%s\n' "$hits" | sed "s/^/$(printf '%02d' "$k") /"
  done < <(cat "${@:2}") | sort
}

# fixture: 2100 empty files (three 1000-file batches) plus hits for patterns 1, 3 and 5 (pattern 1 also in a file that holds pattern 5)
T="$WORK/tree"
mkdir -p "$T/sub"
( cd "$T" && seq -f 'f%05g.txt' 1 2100 | xargs touch )
printf 'nothing to see\n' >"$T/sub/clean.txt"
printf 'x ALPHA-123 y\n' >"$T/sub/one.txt"
printf 'the beta token\n' >"$T/sub/sp ace.txt"
printf 'deltatwo\nALPHA-999\n' >"$T/sub/five-and-one.txt"
printf 'ALPHA-555\n' >"$T/f00700.txt"
printf 'beta token\n' >"$T/f01400.txt"
printf 'deltaone\n' >"$T/f02100.txt"
HITS=("$T/sub/one.txt" "$T/sub/sp ace.txt" "$T/sub/five-and-one.txt" "$T/f00700.txt" "$T/f01400.txt" "$T/f02100.txt")
B="$WORK/ban"
mkdir -p "$B"
printf '# primary policy\nALPHA-[0-9]{3}\nNOHIT_[A-Z]+\nbeta[[:space:]]token\n' >"$B/.banlist.txt"
printf '# local override\n^gamma$\ndelta(one|two)\nNEVER_[0-9]+_MATCHES\n' >"$B/.banlist.local.txt"

# 1. the hit set: identical to one grep per pattern, patterns 1, 3 and 5 hit (5 comes from the local sibling), hits spread over the batches
want="$(oracle "$T" "$B/.banlist.txt" "$B/.banlist.local.txt")"
run "$B/.banlist.txt" "$T"; rc=$?
got="$(norm "$WORK/out.log")"
stanzas="$(printf '%s\n' "$want" | cut -d' ' -f1 | sort -u | wc -l | tr -d ' ')"
[ "$rc" -ne 0 ] && [ "$stanzas" -eq 3 ] && [ "$got" = "$want" ]
ok $? "hit set (file, hitting pattern) equals one grep per pattern: three patterns, 2100+ files, primary and local banlist"

# 2. the per-pattern greps read only what the prefilter listed: never an empty or clean file, but at least one run happened
pp="$(grep -F -- '-IlE -D skip -e ' "$WORK/grep.log")"
[ -n "$pp" ] && ! grep -qF -e 'sub/clean.txt' -e 'f00001.txt' <<<"$pp"
ok $? "per-pattern greps are handed only the prefiltered files"

# 3. a clean tree (same files, hits emptied): passes, and the only scanning greps are the prefilter's, one per 1000-file batch
for f in "${HITS[@]}"; do : >"$f"; done
run "$B/.banlist.txt" "$T"; rc=$?
n="$(find "$T" -type f | wc -l | tr -d ' ')"
calls="$(grep -c '^-IlE ' "$WORK/grep.log")"
[ "$rc" -eq 0 ] && grep -q 'privacy: clean' "$WORK/out.log" && [ "$calls" -eq $(((n + 999) / 1000)) ]
ok $? "clean tree passes after one scanning grep per 1000-file batch, not one per pattern (got $calls for $n files)"

# 4. an invalid ERE still fails closed, privately, before any prefilter grep
mkdir -p "$WORK/ban2"
printf 'ALPHA-[0-9]{3}\n[\n' >"$WORK/ban2/.banlist.txt"
run "$WORK/ban2/.banlist.txt" "$T"; rc=$?
[ "$rc" -ne 0 ] && grep -qiF 'content withheld' "$WORK/out.log" && ! grep -qF '[' "$WORK/out.log" && ! grep -qF -- ' -f ' "$WORK/grep.log"
ok $? "invalid ERE fails closed, content withheld, before the prefilter runs"

# 5. a prefilter grep error must not read as "no candidates" (clean tree: the only way to a false pass)
: >"$WORK/fail-prefilter"
run "$B/.banlist.txt" "$T"; rc=$?
rm -f "$WORK/fail-prefilter"
[ "$rc" -ne 0 ] && grep -qF 'failing closed' "$WORK/out.log" && ! grep -qF 'privacy: clean' "$WORK/out.log" && grep -qF -- ' -f ' "$WORK/grep.log"
ok $? "prefilter grep error (exit 2) fails closed and never reports clean"

# 6. a banned term in a file whose name ends in a newline, next to a clean file of the same name without it: a newline-delimited
#    candidate list would read the hit as the clean twin and pass, so the gate must still BLOCK (exit 1) like one grep per pattern
mkdir -p "$WORK/nl1"
printf 'x ALPHA-777\n' >"$WORK/nl1/leak"$'\n'
printf 'clean\n' >"$WORK/nl1/leak"
run "$B/.banlist.txt" "$WORK/nl1"; rc=$?
[ "$rc" -eq 1 ] && grep -qF 'BLOCK: a banned pattern matched' "$WORK/out.log"
ok $? "hit in a file named with a trailing newline, clean twin beside it: still BLOCKs (exit 1)"

# 7. the same with the newline inside the name: its two halves are the names of clean files
mkdir -p "$WORK/nl2"
printf 'x ALPHA-888\n' >"$WORK/nl2/leak"$'\n'half
printf 'clean\n' >"$WORK/nl2/leak"
printf 'clean\n' >"$WORK/nl2/half"
run "$B/.banlist.txt" "$WORK/nl2"; rc=$?
[ "$rc" -eq 1 ] && grep -qF 'BLOCK: a banned pattern matched' "$WORK/out.log"
ok $? "hit in a file named with an embedded newline, clean files named after its halves: still BLOCKs (exit 1)"

echo "Tests: $pass/$total"
[ "$pass" -eq "$total" ]
