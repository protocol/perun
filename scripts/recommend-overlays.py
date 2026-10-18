#!/usr/bin/env python3
"""Recommend which overlay skills a target repo should install.

Inspects a project directory and prints a pack. Never writes. The owner
decides; an agent may recommend --full but must not install delivery into
a repo that already has another delivery pack without saying so.

Stdlib only. Bounded walk — no recursive glob of the whole tree.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "coverage",
    "__pycache__",
}

# Live delivery OS only. Historical notes under docs/archive/history/code-review
# do not count — a real product may keep old Superpowers plans without running
# that pack (example: a repo with only docs/superpowers/ notes, no live pack).
LIVE_DELIVERY_DIR_MARKERS = {
    "superpowers",
    "gstack",
    "spec-kit",
    ".specify",
}
ARCHIVE_TOP = {"docs", "doc", "archive", "history", "code-review", "notes"}
LIVE_DELIVERY_SKILL_PATHS = (
    ".claude/skills/superpowers/SKILL.md",
    ".agents/skills/superpowers/SKILL.md",
    ".cursor/skills/superpowers/SKILL.md",
    ".codex/skills/superpowers/SKILL.md",
    ".claude/skills/gstack/SKILL.md",
    ".agents/skills/gstack/SKILL.md",
)

# A live CUSTOM delivery pack: a skill directory under a real host skill root
# (not a docs/ archive) whose path, frontmatter name, or a small body prefix
# names a delivery OS. This catches a private factory, an already-installed
# agentic-delivery, or any gated-delivery overlay that is not one of the named
# packs above — so --recommend does not stack a second delivery OS on top of one
# already running in the target.
LIVE_SKILL_ROOTS = (
    ".claude/skills",
    ".agents/skills",
    ".cursor/skills",
    ".codex/skills",
)
# Review/critique OSes are never "other delivery", even though their prose names
# delivery gates (the review bar cites `agentic-delivery` and G0–G10; idea-critic
# cites G0/G1). Excluding them by name stops a review-only install from
# suppressing the very overlay a target may still want.
REVIEW_ONLY_SKILLS = {
    "deep-code-review",
    "idea-critic",
    "agentic-ceo",
    "product-discovery",
    "growth-analytics",
    "positioning",
    "business-ops",
    "contribution",
    "communication-structure",
    "product-output-safety",
}
# Delivery-positive tokens (case-insensitive). Distinctive multi-char tokens are
# matched as substrings; the short gate labels g0/g10 need word boundaries so
# they do not fire inside unrelated words. A token is required — merely being a
# "skill" or a "review" is not delivery.
DELIVERY_SUBSTRINGS = (
    "agentic-delivery",
    "software-house",
    "gated delivery",
    "shipping loop",
    "/ship",
    "spec-kit",
    "gstack",
    "delivery overlay",
)
DELIVERY_GATE_RE = re.compile(r"\b(?:g0|g10)\b")
# Read only a small prefix of each SKILL.md (frontmatter plus a little body),
# never the whole file, and never a walk of the tree under the skill root.
SKILL_PREFIX_CHARS = 4096
WEB_FILES = {
    "package.json",
    "next.config.js",
    "next.config.mjs",
    "vite.config.ts",
    "vite.config.js",
    "index.html",
}
API_FILES = {
    "openapi.yaml",
    "openapi.yml",
    "pyproject.toml",
    "go.mod",
    "Cargo.toml",
    "Gemfile",
}
IAC_FILES = {
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    "kustomization.yaml",
    "terraform.tf",
}
IAC_DIR_NAMES = {"terraform", "helm", "charts", "infra", "deploy"}
AGENT_FILES = {"SKILL.md", "AGENTS.md", "CLAUDE.md"}
REVIEW_PATHS = (
    ".claude/skills/deep-code-review/SKILL.md",
    ".agents/skills/deep-code-review/SKILL.md",
    ".cursor/skills/deep-code-review/SKILL.md",
)

# Gate/tooling markers, by basename, so the recommendation can report which
# quality gates the target ALREADY has and propose only what is missing. A
# marker's absence is reported as "not detected" — never "you have none": this
# is a bounded, filename-level inspection, not a guarantee.
LINT_MARKERS = {
    ".eslintrc", ".eslintrc.js", ".eslintrc.cjs", ".eslintrc.json",
    ".eslintrc.yml", ".eslintrc.yaml", "eslint.config.js", "eslint.config.mjs",
    "ruff.toml", ".ruff.toml", ".flake8", ".pylintrc", "biome.json",
    ".golangci.yml", ".golangci.yaml", ".rubocop.yml",
}
FORMAT_MARKERS = {
    ".prettierrc", ".prettierrc.js", ".prettierrc.json", ".prettierrc.yml",
    ".prettierrc.yaml", ".prettierrc.cjs", ".editorconfig", "rustfmt.toml",
    ".rustfmt.toml", ".clang-format",
}
TEST_FILE_MARKERS = {
    "pytest.ini", "tox.ini", "conftest.py", "jest.config.js", "jest.config.ts",
    "vitest.config.ts", "vitest.config.js", "phpunit.xml", "karma.conf.js",
}
TEST_DIR_MARKERS = {"tests", "test", "__tests__", "spec"}
PRECOMMIT_MARKERS = {".pre-commit-config.yaml", ".pre-commit-config.yml"}
BANLIST_MARKERS = {".banlist.txt", ".banlist.local.txt"}
CI_FILE_MARKERS = {
    ".gitlab-ci.yml", ".gitlab-ci.yaml", "azure-pipelines.yml", "Jenkinsfile",
    ".travis.yml", "bitbucket-pipelines.yml",
}


def _pkg_scripts(root: Path) -> set:
    """Return the npm script names declared in a root package.json (best effort)."""
    import json

    pkg = root / "package.json"
    if not pkg.is_file():
        return set()
    try:
        data = json.loads(pkg.read_text(encoding="utf-8"))
        scripts = data.get("scripts", {})
        return set(scripts) if isinstance(scripts, dict) else set()
    except (OSError, ValueError):
        return set()


def _pyproject_tools(root: Path) -> str:
    """Return the text of a root pyproject.toml (best effort, empty on failure)."""
    py = root / "pyproject.toml"
    if not py.is_file():
        return ""
    try:
        return py.read_text(encoding="utf-8")
    except OSError:
        return ""


def detect_gates(root: Path, names: set, entries: list) -> dict:
    """Filename-level inspection of which quality gates the target already has.

    Reads at most two well-known manifests (package.json, pyproject.toml) plus
    basename membership; never a full-tree content scan. Every value is a
    best-effort boolean; False means "not detected here", not "absent".
    """
    scripts = _pkg_scripts(root)
    pyproject = _pyproject_tools(root)
    dir_names = {p.name for p in entries if p.is_dir()}

    ci = (root / ".github" / "workflows").is_dir() or bool(names & CI_FILE_MARKERS)
    lint = (
        bool(names & LINT_MARKERS)
        or "lint" in scripts
        or "[tool.ruff]" in pyproject
        or "[tool.flake8]" in pyproject
        or "[tool.pylint" in pyproject
    )
    fmt = (
        bool(names & FORMAT_MARKERS)
        or "format" in scripts
        or "[tool.black]" in pyproject
        or "[tool.ruff.format]" in pyproject
    )
    tests = (
        bool(names & TEST_FILE_MARKERS)
        or bool(dir_names & TEST_DIR_MARKERS)
        or "test" in scripts
        or "[tool.pytest.ini_options]" in pyproject
    )
    pre_commit = bool(names & PRECOMMIT_MARKERS)
    privacy = bool(names & BANLIST_MARKERS)
    return {
        "ci": ci,
        "lint": lint,
        "format": fmt,
        "tests": tests,
        "pre_commit": pre_commit,
        "privacy": privacy,
    }


def walk(root: Path, max_depth: int = 3) -> list[Path]:
    out: list[Path] = []
    def _walk(cur: Path, depth: int) -> None:
        try:
            children = list(cur.iterdir())
        except OSError:
            return
        for child in children:
            if child.name in SKIP_DIRS or child.name.startswith("skill-backups"):
                continue
            out.append(child)
            if child.is_dir() and depth < max_depth:
                _walk(child, depth + 1)
    _walk(root, 0)
    return out


def _names_delivery_os(text: str) -> bool:
    low = text.lower()
    if any(tok in low for tok in DELIVERY_SUBSTRINGS):
        return True
    return bool(DELIVERY_GATE_RE.search(low))


def has_custom_delivery_skill(root: Path) -> bool:
    """True if a live (non-archived) skill declares a delivery OS.

    Bounded: for each known host skill root, look one level down at each skill's
    SKILL.md and read only a prefix — no recursive glob of the tree. Review-only
    skills are never delivery. Skip non-regular files and symlinks (a FIFO would
    hang open(); a symlink can point outside the target). Any single
    unreadable/missing SKILL.md is skipped (fail closed for that file), never
    fatal to the recommendation.
    """
    for host in LIVE_SKILL_ROOTS:
        try:
            children = sorted((root / host).iterdir())
        except OSError:
            continue
        for child in children:
            if child.name in REVIEW_ONLY_SKILLS or not child.is_dir():
                continue
            skill_md = child / "SKILL.md"
            # is_file() follows symlinks; reject those first so a planted FIFO
            # cannot hang open() and an out-of-tree symlink is not read.
            if skill_md.is_symlink() or not skill_md.is_file():
                continue
            try:
                with skill_md.open("r", errors="replace") as fh:
                    blob = fh.read(SKILL_PREFIX_CHARS)
            except OSError:
                continue
            if _names_delivery_os(f"{child.name}\n{blob}"):
                return True
    return False


def recommend(root: Path) -> dict:
    entries = walk(root)
    names = {p.name for p in entries}
    review_present = any((root / m).is_file() for m in REVIEW_PATHS)
    other_delivery = any((root / m).is_file() for m in LIVE_DELIVERY_SKILL_PATHS)
    if not other_delivery:
        for p in entries:
            if p.name not in LIVE_DELIVERY_DIR_MARKERS:
                continue
            try:
                rel = p.relative_to(root)
            except ValueError:
                continue
            if rel.parts and rel.parts[0] in ARCHIVE_TOP:
                continue
            other_delivery = True
            break
    if not other_delivery:
        other_delivery = has_custom_delivery_skill(root)
    web = bool(names & WEB_FILES)
    api = bool(names & API_FILES)
    iac = bool(names & IAC_FILES) or bool(names & IAC_DIR_NAMES)
    agentic = bool(names & AGENT_FILES)

    skills = ["deep-code-review"]
    reasons = ["review bar — always"]
    flags: list[str] = []

    if other_delivery:
        reasons.append(
            "another delivery pack detected — do not also install agentic-delivery"
        )
    elif web or api or iac:
        skills.append("agentic-delivery")
        flags.append("--with-delivery")
        reasons.append(
            "multi-file product / service / infra — gated delivery pays"
        )
    elif agentic:
        reasons.append(
            "agent-instruction surface only — review is enough unless a "
            "feature spans QA+security"
        )

    if "agentic-delivery" in skills or (agentic and not other_delivery):
        if "idea-critic" not in skills:
            skills.append("idea-critic")
            flags.append("--with-critic")
            reasons.append(
                "plans will be proposed — attack them before the owner sees them"
            )

    if "agentic-delivery" in skills and "idea-critic" in skills:
        pack_flag = "--full"
    elif flags:
        pack_flag = " ".join(flags)
    else:
        pack_flag = "(default — review only)"

    return {
        "review_present": review_present,
        "other_delivery": other_delivery,
        "skills": skills,
        "pack_flag": pack_flag,
        "reasons": reasons,
        "shape": {"web": web, "api": api, "iac": iac, "agentic": agentic},
        "gates": detect_gates(root, names, entries),
    }


# Advisory + conductor overlays — opt-in, default off, not in --full. --recommend
# lists these UNCONDITIONALLY so the owner learns they exist at pack-selection time;
# it never auto-installs them. Shape-based auto-push of the highest-fabrication-risk
# skills (positioning, business-ops) onto a target would violate the deny-by-default,
# owner-decides posture, so that is a deliberate non-goal.
ADVISORY_OVERLAYS = (
    ("--with-discovery", "product-discovery",
     "is this worth building? what first? is it working? — from real-user evidence"),
    ("--with-growth", "growth-analytics",
     "what to measure — North Star, AARRR funnel, event taxonomy — on your own analytics"),
    ("--with-positioning", "positioning",
     "value proposition, segment, message house — as a hypothesis to validate with buyers"),
    ("--with-business", "business-ops",
     "leads with the call on your pricing / unit-economics numbers; routes the binding legal / tax / securities part to a professional"),
    ("--with-output-safety", "product-output-safety",
     "govern harm from the product's own AI outputs; map/measure/manage; HITL on high-stakes actions"),
    ("--with-ceo", "agentic-ceo",
     "the suite conductor — routes (stage, area) to the right skill, sizes effort, chaos playbook"),
    ("--with-comms", "communication-structure",
     "BLUF / no-slop structure for human-facing messages and deliverables"),
    ("--with-contribution", "contribution",
     "prepare a privacy-safe upstream improvement for a human to review and open"),
)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", help="project directory to inspect")
    args = parser.parse_args(argv[1:])
    root = Path(args.target).resolve()
    if not root.is_dir():
        print(f"recommend: not a directory: {root}", file=sys.stderr)
        return 2
    rec = recommend(root)
    print(f"target: {root}")
    print(
        f"shape: web={rec['shape']['web']} api={rec['shape']['api']} "
        f"iac={rec['shape']['iac']} agentic={rec['shape']['agentic']}"
    )
    print(f"review already installed: {rec['review_present']}")
    print(f"other delivery pack: {rec['other_delivery']}")
    print(f"recommend skills: {', '.join(rec['skills'])}")
    print(f"install flag: ./install.sh {rec['pack_flag']} {root}")
    print("why:")
    for r in rec["reasons"]:
        print(f"  - {r}")

    specify = (root / ".specify").is_dir() or (root / "constitution.md").is_file()
    if specify:
        print()
        print("Spec Kit constitution detected. Review against it")
        print("(docs-and-dx.md). Do not install Spec Kit. Do not stack")
        print("agentic-delivery on top of .specify.")

    gates = rec["gates"]
    glabel = {"pre_commit": "pre-commit", "ci": "CI"}
    present = [glabel.get(g, g) for g, ok in gates.items() if ok]
    missing = [glabel.get(g, g) for g, ok in gates.items() if not ok]
    print()
    print("quality gates detected (filename-level; 'not detected' != 'absent'):")
    print(f"  present:      {', '.join(present) or '(none detected)'}")
    print(f"  not detected: {', '.join(missing) or '(all core gates detected)'}")
    if "agentic-delivery" in rec["skills"]:
        print()
        print("software-house pack (install with --with-delivery / --full):")
        print("  Adds the delivery roles as hats (not standing bots): Conductor,")
        print("  Product Analyst, Architect, Implementer, Evil Twin, QA, Security,")
        print("  UX & Design, Release, Docs. Depth: agentic-delivery/references/roles.md.")
        if missing:
            print("  Gates the deep-code-review Phase-6 imprint can wire that are")
            print(f"  not detected here: {', '.join(missing)}.")
        if rec["shape"]["web"]:
            print("  UI target: also wire verify-visible-UX + ux-evidence")
            print("  (deep-code-review product-ux-quality.md).")

    print()
    print("CI enforcement available (mechanism, not a skill; install with --with-gates):")
    print("  Wires the INSTALLED skill's own gate scripts into this repo's own CI, so")
    print("  the doctrine actually runs here instead of staying prose an agent may or")
    print("  may not follow:")
    print("    - fix_class_gate  every fix(...) commit touches a pinned test, or")
    print("                      carries a non-empty No-Test-Reason: trailer")
    print("    - binaries_gate   no git-tracked file at a banned image/media/")
    print("                      archive/build-output extension")
    print("    - selftests       every gate script above proves it fires on a")
    print("                      planted violation before its result is trusted")
    print("  Writes .github/workflows/dcr-gates.yml + scripts/dcr-gates.sh; never")
    print("  overwrites an existing file at either path (writes <path>.new instead).")

    print()
    print("advisory overlays available (opt-in, default off, not in --full;")
    print("--recommend never auto-installs these — the owner chooses):")
    for flag, name, reach in ADVISORY_OVERLAYS:
        print(f"  {flag:20} {name} — {reach}")

    print()
    print("Owner decides. Agent may recommend --full. Do not install")
    print("overlays without a yes. Caveman is not in this pack — see")
    print("https://github.com/JuliusBrussee/caveman if compressed chat")
    print("is wanted; persisted artifacts stay normal English.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
