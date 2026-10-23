"""performance-db-cost.md and api-contracts.md each shed verbatim depth into a lazy reference.

Pins, as a multiset (collections.Counter) of non-blank lines hashed with sha256[:16]: the combined line multiset of the four files
equals the pre-split multiset of the two old files (hashes in scripts/latency-split-lines.txt, one per line, duplicates kept) plus
exactly the ADDED allowlist below, and nothing else. A dropped line, a duplicated line or an edited line therefore all fail; every
edit to a moved line must be added to ADDED (and its old hash is then reported as lost). Also pins routing, the "Read this when"
headers, that the safety bullets stayed in the must-load cores (shared-cache keying, per-user data in a shared cache, cache as
source of truth = data loss, streaming auth pointer), and a size cap on each core.
"""
import hashlib
import pathlib
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT / ".claude/skills/deep-code-review/references"
FILES = ("performance-db-cost.md", "performance-latency-depth.md", "api-contracts.md", "api-contracts-streaming.md")
h = lambda s: hashlib.sha256(s.strip().encode()).hexdigest()[:16]  # noqa: E731
text = lambda n: (R / n).read_text(encoding="utf-8")  # noqa: E731
OLD = Counter((ROOT / "scripts/latency-split-lines.txt").read_text().split())
ADDED = [
    '# Performance depth — handler await ordering and cache expiry',
    'Read this when the target has a server request handler, page loader or resolver that assembles one response from several async calls, or an application-level cache layer (memoization, Redis, CDN). It fires at FILE or FULL scope on what the repo contains, not only on a diff. Moved verbatim from `performance-db-cost.md`; "above" and "below" in these bullets resolve against that file\'s *Indexes*, *Necessity*, *N+1* and *External / API / LLM calls* bullets, and its 🚩 grep list stays there.',
    '## Handler await ordering',
    '## Cache invalidation, key space and refresh',
    '- Cache invalidation of derived entries, key cardinality, expiry stampede and refresh-on-every-read depth: `performance-latency-depth.md` — **read it when** the target has an application-level cache layer (memoize, Redis, CDN) or a 🚩 grep hit below names one of those shapes, at any scope.',
    '- Handler `await` ordering (sequential independent awaits, a shared source re-read per projection, an expensive `await` above an early return): `performance-latency-depth.md` — **read it when** a request handler, page loader or resolver assembles a response from several async calls, or a 🚩 grep hit below names one of those shapes, at any scope.',
    '# Streaming transports — contract & reliability',
    'Read this when the target serves or consumes a WebSocket, SSE or gRPC-streaming endpoint (server, client or SDK wrapper). It fires at FILE or FULL scope on what the repo contains, not only on a diff. Moved verbatim from `api-contracts.md`, where "this file" refers; the auth angle stays in `security-api.md`.',
    'Reconnect-resume, slow-consumer bounds, two-way liveness, ordering/dedup, gRPC keepalive and bidi flow control: `api-contracts-streaming.md` — **read it when** the target serves or consumes a WebSocket, SSE or gRPC-streaming endpoint, at any scope (FILE or FULL, not only a diff). The auth angle (upgrade auth, `Origin`/CSWSH, per-connection limits) stays in `security-api.md`.',
]



def lines(texts):
    return Counter(h(x) for t in texts.values() for x in t.split("\n") if x.strip())


def diff(texts):
    """(lost, extra) multiset differences against OLD + ADDED."""
    want, have = OLD + Counter(h(a) for a in ADDED), lines(texts)
    return want - have, have - want


class LatencySplit(unittest.TestCase):
    def texts(self):
        return {n: text(n) for n in FILES}

    def test_line_multiset_survives_with_only_the_allowlisted_additions(self):
        self.assertEqual(diff(self.texts()), (Counter(), Counter()))

    def test_mutations_fail(self):
        t = self.texts()
        for n, pick in (("performance-latency-depth.md", "- **Stampede"), ("performance-latency-depth.md", "- **Sequential"),
                        ("performance-db-cost.md", "- **Cache-aside write race"), ("api-contracts-streaming.md", "- **Bound a slow"),
                        ("api-contracts.md", "- **Adding a required field")):
            line = next(x for x in t[n].split("\n") if x.startswith(pick))
            for bad in (t[n].replace(line, ""), t[n].replace(line, line + "\n" + line), t[n].replace(line, line + " x")):
                self.assertNotEqual(diff({**t, n: bad}), (Counter(), Counter()), (n, pick))
        # a line duplicated across files (moved text left behind in the core too) fails
        dup = next(x for x in t["performance-latency-depth.md"].split("\n") if x.startswith("- **Stampede"))
        self.assertTrue(diff({**t, "performance-db-cost.md": t["performance-db-cost.md"] + dup + "\n"})[1])

    def test_lazy_files_open_with_read_this_when_and_are_routed(self):
        fm = text("full-map.md")
        for lazy, core in (("performance-latency-depth.md", "performance-db-cost.md"), ("api-contracts-streaming.md", "api-contracts.md")):
            self.assertIn("Read this when", "\n".join(text(lazy).split("\n")[:4]), lazy)
            self.assertIn(f"`{lazy}`", text(core), lazy)
            self.assertIn(f"`{lazy}`", fm, lazy)

    def test_triggers_fire_on_repo_content_not_only_a_diff(self):
        for n in ("performance-latency-depth.md", "api-contracts-streaming.md"):
            self.assertIn("not only on a diff", text(n), n)
        self.assertIn("at any scope", text("performance-db-cost.md"))
        self.assertIn("not only a diff", text("api-contracts.md"))

    def test_safety_bullets_stay_in_the_must_load_cores(self):
        core = text("performance-db-cost.md")
        for k in ("No caching of sensitive/per-user data in a shared cache", "**A shared cache must key on whatever varies the representation.**",
                  "**Authoritative vs advisory — state which.**", "turns an eviction into\n  **data loss**",
                  "**Every append-only store on disk names a reaper"):
            self.assertIn(k, core)
        api = text("api-contracts.md")
        self.assertIn("`security-api.md`", api.split("## Streaming transports")[1].split("\n---")[0])
        for k in ("## Webhooks — consuming (inbound)", "## Webhooks — providing (outbound)", "## Message / queue / serialized-state evolution",
                  "## Transactional / bulk email"):
            self.assertIn(k, api)

    def test_cores_stay_cut(self):
        self.assertLessEqual(len(text("performance-db-cost.md").encode()), 31100)  # old 43051
        self.assertLessEqual(len(text("api-contracts.md").encode()), 21500)  # old 28126


if __name__ == "__main__":
    unittest.main()
