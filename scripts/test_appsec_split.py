"""deep-code-review security-appsec.md keeps the per-category checks every application review needs; conditional blocks moved
verbatim to appsec-egress.md (SSRF guard transport footguns, parallel-lane drift), appsec-flows.md (A06 business-flow detect steps)
and appsec-corroboration.md (proof-to-claim map). The untrusted-egress caller census and the client-trust-fields check stay in the
parent: FILE/FULL scope never fires a diff-only trigger, and every review needs both.

Pins: the multiset of non-blank lines of the pre-split file (32790 bytes, sha256 80b0f6e38fa231ba7cfdf2e6efad652a4d938ff499daeea9b825f75f32fdf0f2,
parent commit 31419323d5860b34faa9b39dafe15e632ee34c94; scripts/appsec-split-lines.txt holds the truncated sha256 of each one) must equal
the multiset across the parent and the split files, minus EDITED (old lines deliberately reworded) and plus ADDED (an explicit allowlist
of every new line). A dropped, edited, OR DUPLICATED line therefore fails. Also: each split file opens with a "Read this when" line, is
routed by path from the parent's index (with its trigger) and from full-map.md, and the parent stays under a size cap.
"""
import hashlib
import pathlib
import unittest
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parent.parent
R = ROOT / ".claude/skills/deep-code-review/references"
PARENT = "security-appsec.md"
SPLITS = ("appsec-egress.md", "appsec-flows.md", "appsec-corroboration.md")
PARENT_CAP = 28000  # old file 32790 B (-14.6% at the cap)
TRIGGERS = {  # index row -> phrase its trigger must carry
    "appsec-egress.md": "SSRF guard",
    "appsec-flows.md": "check-then-act",
    "appsec-corroboration.md": "SARIF",
}
EDITED = (  # old lines reworded on purpose ("above" -> "in security-appsec.md"; the census tail split off)
    "- **A hand-rolled `fetch` replacement built to enforce the resolve-validate-pin above re-introduces the bugs `fetch`",
    "  calls is a no-op. **Parallel-lane version drift is the same census miss with a timestamp, not a gap.** Two lanes",
    '    is not "clean" (the `Secrets` rule above still holds: a committed secret is compromised).',
)
ADDED = (  # prefix of every line in the new files that the old file did not have; each must match exactly once
    "| `appsec-egress.md` | builds or changes an SSRF guard",
    "| `appsec-flows.md` | has a flow that moves value or advances state (checkout, refund, balance, coupon, invite, quota, wizard, approval, tier change)",
    "| `appsec-corroboration.md` | rests a finding on taint",
    "| `appsec-verify.md` | yields a finding",
    "  calls is a no-op. Parallel-lane version drift and the merge-time re-census: `appsec-egress.md`.",
    "- **Guard transport footguns and parallel-lane guard drift**",
    "**Detect steps for business flows** (money/state machines for checkout, refund, balance, coupon, invite, quota, wizard, approval, tier change;",
    "## Corroboration (cross-cutting)",
    "Deterministic corroboration (the proof-to-claim map and SARIF/OSV ingestion): `appsec-corroboration.md`",
    "# Application security depth — the SSRF guard transport footguns",
    "Read this when the target or diff builds or changes an SSRF guard",
    "## A01:2025 — Broken Access Control (depth: SSRF guard footguns and egress census)",
    "- **A hand-rolled `fetch` replacement built to enforce the resolve-validate-pin in security-appsec.md re-introduces",
    "- **Untrusted-egress caller census, continued (the census itself stays in `security-appsec.md`):**",
    "  **Parallel-lane version drift is the same census miss with a timestamp, not a gap.** Two lanes",
    "# Application security depth — money and state flows",
    "Read this when the target or diff has a flow that moves value or advances state",
    "## A06:2025 — Insecure Design (depth: detect steps for business flows)",
    "Read this when a finding claims that input reaches a sink",
    '    is not "clean" (the `Secrets` rule in security-appsec.md still holds:',
)
h = lambda s: hashlib.sha256(s.strip().encode()).hexdigest()[:16]  # noqa: E731
text = lambda n: (R / n).read_text(encoding="utf-8")  # noqa: E731
OLD = Counter((ROOT / "scripts/appsec-split-lines.txt").read_text().split())


def diff(texts):
    """(old line hashes missing from the new multiset beyond EDITED, new lines beyond the old multiset not in ADDED)."""
    lines = [x for t in texts.values() for x in t.split("\n") if x.strip()]
    new = Counter(h(x) for x in lines)
    missing = (OLD - new) - Counter(h(x) for x in EDITED)
    left, extra, used = list(ADDED), [], Counter()
    for x in lines:
        k = h(x)
        if (new - OLD)[k] > used[k]:
            used[k] += 1
            hit = next((p for p in left if x.startswith(p)), None)
            left.remove(hit) if hit else extra.append(x)
    return list(missing), extra, left


def files(**over):
    return {n: over.get(n, text(n)) for n in (PARENT,) + SPLITS}


class AppsecSplit(unittest.TestCase):
    def test_old_lines_survive_exactly_once(self):
        missing, extra, unused = diff(files())
        self.assertEqual((missing, extra, unused), ([], [], []))

    def test_pin_catches_a_drop_an_edit_and_a_duplicate(self):
        parent = text(PARENT)
        census = next(x for x in parent.split("\n") if x.startswith("- **Untrusted-egress caller census"))
        self.assertTrue(diff(files(**{PARENT: parent + "\n" + census}))[1], "duplicate census line passed")
        self.assertEqual(len(diff(files(**{PARENT: parent.replace(census, census + " x", 1)}))[0]), 1, "edit passed")
        self.assertTrue(diff(files(**{PARENT: parent.replace(census + "\n", "", 1)}))[0], "drop passed")
        dup_split = text(SPLITS[1]) + "\n" + text(SPLITS[1]).split("\n")[8]  # a verbatim old bullet line repeated
        self.assertTrue(diff(files(**{SPLITS[1]: dup_split}))[1], "duplicate split line passed")
        self.assertTrue(diff({n: t for n, t in files().items() if n != SPLITS[0]})[0], "deleted split passed")

    def test_split_files_open_with_read_this_when(self):
        for n in SPLITS:
            self.assertIn("Read this when", "\n".join(text(n).split("\n")[:3]), n)

    def test_routed_from_parent_index_and_full_map(self):
        parent, fmap = text(PARENT), text("full-map.md")
        for n, phrase in TRIGGERS.items():
            row = next((x for x in parent.split("\n") if x.startswith(f"| `{n}` |")), None)
            self.assertIsNotNone(row, f"{n} missing from the parent index")
            self.assertIn(phrase, row)
            self.assertIn(f"`{n}`", fmap)
        flows = next(x for x in parent.split("\n") if x.startswith("| `appsec-flows.md` |"))
        pointer = next(x for x in parent.split("\n") if x.startswith("**Detect steps for business flows**"))
        for term in ("invite", "approval", "tier change"):  # same flow list as appsec-flows.md line 3
            self.assertIn(term, flows)
            self.assertIn(term, pointer)
            self.assertIn(term, text(SPLITS[1]).split("\n")[2])

    def test_parent_points_at_each_moved_block_and_keeps_the_always_needed_ones(self):
        parent = text(PARENT)
        for n in SPLITS:
            self.assertGreaterEqual(parent.count(f"`{n}`"), 2, n)  # index row + the in-section pointer
        for gone in ("A hand-rolled `fetch` replacement", "**Detect steps, in order**", "## Deterministic corroboration"):
            self.assertNotIn(gone, parent)
        # kept in the core: FILE/FULL scope never fires the diff-only split triggers
        for keep in ("- **Untrusted-egress caller census (after a guard lands):**", "- **Client-trust fields.**"):
            self.assertIn(keep, parent)
        self.assertIn("\n## Corroboration (cross-cutting)\n", parent)  # own heading, not nested under Secrets

    def test_parent_shrank_and_keeps_core_checks(self):
        parent = text(PARENT)
        self.assertLess(len(parent.encode()), PARENT_CAP)
        for keep in ("- **SSRF**: URL/host/IP from input fetched server-side", "**Two-principal matrix", "**Anonymous GET sweep",
                     "## A07:2025 — Authentication Failures", "## Secrets (cross-cutting)", "## Going deeper"):
            self.assertIn(keep, parent)

    def test_no_stale_above_pointers(self):
        for n in SPLITS:
            self.assertNotIn("rule above", text(n))
            self.assertNotIn("resolve-validate-pin above", text(n))


if __name__ == "__main__":
    unittest.main()
