"""Build a V2 skill copy: mk_v2.py NAME OUTDIR [SKILL_DIR]. SKILL.md = the repo frontmatter + variants/NAME.md (single inlined compact
method, no routed reference except full-map.md for non-DIFF scopes); references/full-map.md = the unedited skill body. Never writes under .claude/skills."""
import sys
from pathlib import Path

name, out = sys.argv[1], Path(sys.argv[2])
src = Path(sys.argv[3] if len(sys.argv) > 3 else Path(__file__).resolve().parents[3] / ".claude/skills/deep-code-review")
s = (src / "SKILL.md").read_text()
i = s.index("# Deep Code Review")
(out / "references").mkdir(parents=True, exist_ok=True)
(out / "references/full-map.md").write_text("Read this when the review is not a small DIFF. It is the skill's full body.\n\n" + s[i:])
(out / "SKILL.md").write_text(s[:i] + (Path(__file__).parent / "variants" / f"{name}.md").read_text())
