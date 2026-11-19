"""deep-code-review method.md is a core; the DIFF-only and bypass/probe lenses moved verbatim to method-diff.md and method-lenses.md.

Pins: every non-blank line of the pre-split method.md (43524 bytes, sha256 of the whole file
ebf9724444148579d64e13ef3c117110d96b1d6cdd32b66757204bf6dd403c58) survives in the core or a lazy file
(scripts/method-split-lines.txt holds the truncated sha256 of each old line; the four old lines cut mid-line are stored as
`old:head:tail` and both halves must be present as whole lines), each lazy file opens with "Read this when" and is routed by
path from the core and from full-map.md, the core names each trigger, each lens paragraph lives in exactly its own file, and the
core stays under a size cap that is a >=30% cut. Two old lines (the intent-conformance cites) were repointed to method-diff.md; their
fixture entries read `old:new` so the reworded line must survive whole.
"""
import hashlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import review_load_bytes as r  # noqa: E402

R = ROOT / ".claude/skills/deep-code-review/references"
FILES = ("method.md", "method-diff.md", "method-lenses.md")
CORE_CAP = 30200  # old file 43524 B; 30467 would be exactly -30%. Raised from 30000 for the known-vuln dependency impact-path clause.
h = lambda s: hashlib.sha256(s.strip().encode()).hexdigest()[:16]  # noqa: E731
text = lambda n: (R / n).read_text(encoding="utf-8")  # noqa: E731
OLD = [x for x in (ROOT / "scripts/method-split-lines.txt").read_text().split()]


def lost(texts):
    """Old lines (or split halves) absent from the given {name: text} map."""
    have = {h(x) for t in texts.values() for x in t.split("\n") if x.strip()}
    gone = []
    for e in OLD:
        parts = e.split(":")
        need = parts if len(parts) == 1 else parts[1:]  # a split line survives as its two halves
        gone += [p for p in need if p not in have]
    return gone


class MethodSplit(unittest.TestCase):
    def test_every_old_line_survives(self):
        self.assertEqual(lost({n: text(n) for n in FILES}), [])

    def test_survival_check_fails_on_a_dropped_or_truncated_line(self):
        t = {n: text(n) for n in FILES}
        for n, pick in (("method.md", "**Phase 4"), ("method-diff.md", "**Sweep-scope issue"), ("method-lenses.md", "**Mine the code's own comments")):
            line = next(x for x in t[n].split("\n") if x.startswith(pick))
            self.assertTrue(lost({**t, n: t[n].replace(line, "")}), n)  # dropped
            self.assertTrue(lost({**t, n: t[n].replace(line, line + " x")}), n)  # one char appended
        # a split half cut short must fail too (first and last line of a lazy file's split pieces)
        tail = next(x for x in t["method-diff.md"].split("\n") if x.startswith("**A fix that already scoped itself to an"))
        self.assertTrue(lost({**t, "method-diff.md": t["method-diff.md"].replace(tail, tail[:-1])}))

    def test_lazy_files_open_with_read_this_when_and_are_routed(self):
        core, fm = text("method.md"), text("full-map.md")
        for n in FILES[1:]:
            self.assertTrue(text(n).startswith("Read this when"), n)
            self.assertIn(f"`{n}`", core)
            self.assertIn(f"`{n}`", fm)

    def test_core_names_each_trigger(self):
        core = text("method.md")
        for k in ("On a `DIFF` or `FILE`, read `method-diff.md`", "Lenses: read `method-lenses.md` when", "procedure in `method-lenses.md`",
                  "`method-diff.md` holds the completeness sweeps"):
            self.assertIn(k, core)

    def test_each_lens_paragraph_lives_in_exactly_its_file(self):
        where = {"method-diff.md": ("**On a `DIFF`, classify each changed hunk", "**Intent-conformance — a lens", "**Sweep-scope issue",
                                    "**Rewritten browser spec", "**A fix that already scoped itself to an"),
                 "method-lenses.md": ("**Mine the code's own comments", "**Diff every ad-hoc re-derivation", "**Beyond the security openers, author a disposable probe")}
        for home, heads in where.items():
            for head in heads:
                self.assertEqual([n for n in FILES if any(x.startswith(head) for x in text(n).split("\n"))], [home], head)

    def test_core_keeps_comment_mining_and_canonical_predicate_stubs(self):
        core = text("method.md")
        for k in ("instead of|not using|hand-rolled|workaround", "shared `components/`, `ui/` or `lib/` dir", "re-derives it inline from a subset"):
            self.assertIn(k, core)

    def test_core_keeps_every_phase_and_sheds_the_lenses(self):
        core = text("method.md")
        for keep in ("**Phase 0 — Map the target.**", "**Phase 1 — Establish ground truth.**", "**Phase 2 — Domain audits.**",
                     "**Phase 3 — Adversarial / red-team pass.**", "**Phase 4 — Synthesize & rank.**", "**Anti-slop (drop before the report).**",
                     "**Presence and absence are not the same claim.**", "**Stated invariant / landed guard"):
            self.assertIn(keep, core)
        for gone in ("**Intent-conformance — a lens", "**Diff every ad-hoc re-derivation", "**Mine the code's own comments", "**Sweep-scope issue"):
            self.assertNotIn(gone, core)
        self.assertLess(len(core.encode()), CORE_CAP)

    def test_large_diff_load_model_reads_the_diff_file(self):
        self.assertIn("references/method-diff.md", r.load_set("references/full-map.md method-diff.md a match skips `INDEX.md`", 301)[1])
        self.assertNotIn("references/method-diff.md", r.load_set("references/full-map.md a match skips `INDEX.md`", 301)[1])


if __name__ == "__main__":
    unittest.main()
