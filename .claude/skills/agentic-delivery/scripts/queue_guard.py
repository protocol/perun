#!/usr/bin/env python3
# rail: owner=agentic-delivery, why=keep one priority queue and flag P0 inflation, review=2027-01-30
"""queue_guard.py — single priority queue: print the next issue to pull, flag P0 inflation.

WHY: when every urgent thing is labelled P0 the label stops ranking anything.
Do not relabel. Rank a top-N in PRIORITIES.md, tag the rest `p0:unranked`, and pull in
this order: ranked items (file order) first, then the remaining P0s oldest first.

USAGE: queue_guard.py --issues issues.json --priorities PRIORITIES.md [--max-unranked N]
  issues.json   `gh issue list --json number,title,createdAt,labels,state` output.
  PRIORITIES.md the first `#N` on each list line (`-`, `*`, or `1.`) is a ranked item,
                best first. Other lines are prose and ignored.
Output: `NEXT #N title` (or `NEXT none`), then `TAG p0:unranked: #a #b` for unranked P0s
not yet tagged, `STALE ranked: #n` for ranked ids that are not open P0s, and
`INFLATED` when the unranked P0 count exceeds N (default 5).
Exit 0 ok, 1 inflated, 2 bad input (missing or unparseable file: fails closed).
Edge cases: closed issues are ignored; a `p0:unranked` label counts as P0 and is
unranked unless the id is listed in PRIORITIES.md; label match is case-insensitive.
Side effects: none (read-only; never edits labels).
"""
import json, re, sys

LIST_LINE = re.compile(r"^\s*(?:[-*]|\d+[.)])\s.*?#(\d+)")


def ranked_ids(text):
    out = []
    for line in text.splitlines():
        m = LIST_LINE.match(line)
        if m and int(m.group(1)) not in out:
            out.append(int(m.group(1)))
    return out


def plan(issues, ranked, max_unranked=5):
    p0 = {}
    for i in issues:
        if i.get("state", "open").lower() != "open":
            continue
        names = {(l["name"] if isinstance(l, dict) else l).lower() for l in i.get("labels", [])}
        if names & {"p0", "p0:unranked"}:
            p0[i["number"]] = (i, "p0:unranked" in names)
    first = [p0[n][0] for n in ranked if n in p0]
    rest = sorted((v[0] for n, v in p0.items() if n not in ranked), key=lambda i: (i["createdAt"], i["number"]))
    return {
        "next": (first + rest or [None])[0],
        "unranked": len(rest),
        "inflated": len(rest) > max_unranked,
        "untagged": [i["number"] for i in rest if not p0[i["number"]][1]],
        "stale": [n for n in ranked if n not in p0],
    }


def render(r, max_unranked):
    n = r["next"]
    lines = ["NEXT none" if n is None else "NEXT #%d %s" % (n["number"], n["title"])]
    if r["inflated"]:
        lines.append("INFLATED: %d unranked P0 > %d; rank a top-%d in PRIORITIES.md, tag the rest p0:unranked, do not relabel"
                     % (r["unranked"], max_unranked, max_unranked))
    if r["untagged"]:
        lines.append("TAG p0:unranked: " + " ".join("#%d" % n for n in r["untagged"]))
    if r["stale"]:
        lines.append("STALE ranked: " + " ".join("#%d" % n for n in r["stale"]))
    return "\n".join(lines)


def selftest():
    def mk(n, d, *lab, state="open"):
        return {"number": n, "title": "t%d" % n, "createdAt": d, "state": state, "labels": [{"name": x} for x in lab]}

    iss = [mk(1, "2026-01-03", "p0"), mk(2, "2026-01-01", "p0"), mk(3, "2026-01-02", "p0:unranked"),
           mk(4, "2026-01-04", "bug"), mk(5, "2026-01-05", "p0", state="closed"), mk(6, "2026-01-06", "P0")]
    ranked = ranked_ids("# Prio\nprose #9\n1. fix #1 first\n- also #6\n- dup #1\n- gone #7\n")
    assert ranked == [1, 6, 7], ranked
    r = plan(iss, ranked, 5)
    assert r["next"]["number"] == 1 and r["stale"] == [7] and r["untagged"] == [2] and not r["inflated"], r
    r = plan(iss, ranked, 1)  # unranked 2, 3 -> inflated
    assert r["inflated"] and r["unranked"] == 2, r
    assert plan(iss, [], 5)["next"]["number"] == 2  # no ranking: oldest P0
    assert plan([mk(4, "2026-01-04", "bug")], [], 5)["next"] is None
    # CLI fixture: gh-shaped JSON + PRIORITIES.md -> exit codes (0 ok, 1 inflated, 2 missing file)
    import tempfile, os
    with tempfile.TemporaryDirectory() as d:
        ip, pp = os.path.join(d, "i.json"), os.path.join(d, "P.md")
        json.dump([mk(n, "2026-01-0%d" % n, "p0") for n in (1, 2, 3)], open(ip, "w"))
        open(pp, "w").write("- #1 first\n")
        assert main(["--issues", ip, "--priorities", pp, "--max-unranked", "2"]) == 0
        assert main(["--issues", ip, "--priorities", pp, "--max-unranked", "1"]) == 1
        json.dump([dict(mk(1, "2026-01-01", "p0"), state=None)], open(ip, "w"))  # null state fails closed
        assert main(["--issues", ip, "--priorities", pp]) == 2
        assert main(["--issues", os.path.join(d, "none.json"), "--priorities", pp]) == 2
    print("queue_guard selftest ok")


def main(argv):
    if "--selftest" in argv:
        selftest()
        return 0
    a = dict(zip(argv[::2], argv[1::2]))
    try:
        mx = int(a.get("--max-unranked", 5))
        with open(a["--issues"]) as f:
            issues = json.load(f)
        with open(a["--priorities"]) as f:
            ranked = ranked_ids(f.read())
        r = plan(issues, ranked, mx)
    except (KeyError, OSError, ValueError, TypeError, AttributeError) as e:
        print("queue_guard: bad input (%s: %s)" % (type(e).__name__, e), file=sys.stderr)
        return 2
    print(render(r, mx))
    return 1 if r["inflated"] else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
