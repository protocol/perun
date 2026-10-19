# Perun

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Perun is a suite of written instructions that make an AI coding assistant work
the same careful way every time, from review to delivery, showing the evidence
for what it reports.**

Each part is a **skill**: a text file of instructions the AI assistant reads
before it starts work. The suite covers:

- **Deep code review** (the flagship, and the default install): a repeatable
  review with evidence for every problem.
- **Token and cost optimisation:** token reports, auto-compact plus handoff, and
  model-tier guidance.
- **Gated agentic delivery** (opt-in): merge train, lanes, a destructive-command
  guard and auto-update.
- **An idea critic**, plus **product, growth, positioning, business-ops and
  output-safety** specialists.

**Not a developer?** Read [Perun for leaders](docs/for-leaders.md): what it gives
your team, a pilot plan, limits and an FAQ.

**Choosing a bundle?** See [Perun vs other skill bundles](docs/perun-vs-rivals.md): measured ties, losses and token overhead. Rivals and gaps per capability: [capability matrix](docs/capability-matrix.md).

## Why it matters

**Bottom line (measured 2026-10-12):** on 39 held-out real bug fixes, Perun caught
more bugs than a plain "review this" prompt, but the gain is borderline: the lower
end of its margin of error is 0. Against Claude Code's built-in `/code-review`, Perun
caught about the same number of bugs with far fewer false alarms. Treat this as
directional evidence, not proof.

Setup: model `claude-sonnet-5-5`, every run with `--strict-mcp-config`, the same day,
the same cases, the same verifier for every arm. The assistant saw only the code
change (checked out at the commit before the fix), not the fix. "Recall" is the share of
the known bugs the review caught, judged by a verifier model; "strict" uses a fixed
text match instead. "Verified precision" is the share of flagged issues the verifier
confirmed as real. F1 combines recall and verified precision.

Perun against a plain prompt (39 cases, paired):

| | Plain prompt | Perun, one pass | Perun minus plain [95% interval] |
|---|---|---|---|
| Recall, verifier-judged | 0.385 | 0.487 | +0.103 [0.000, +0.231] |
| Recall, strict | 0.462 | 0.615 | +0.154 [0.000, +0.308] |
| Verified precision | 0.778 | 0.800 | +0.022 [-0.104, +0.142] |
| F1 | 0.515 | 0.606 | not computed |

Cost is not shown for these two tables: the same harness re-run on 37 of the 39 cases
priced the plain prompt at $0.098 per case, not the $0.06 first recorded, and the first
run did not record what its figure included. Cost per bug found is below.

Perun against `/code-review` (34 of the 39 cases; 5 did not finish before the spend cap):

| | Plain prompt | Perun | `/code-review` | `/code-review` plus verifier |
|---|---|---|---|---|
| Recall, verifier-judged | 0.382 | 0.529 | 0.529 | 0.412 |
| Recall, strict | 0.441 | 0.647 | 0.735 | 0.529 |
| Verified precision | 0.792 | 0.839 | 0.336 | 0.688 |
| F1 | 0.516 | 0.649 | 0.411 | 0.515 |

Paired differences, Perun minus the other (95% interval):

| Against | Recall, verifier-judged | Verified precision | F1 |
|---|---|---|---|
| `/code-review` | +0.000 [-0.088, +0.088] | +0.502 [+0.405, +0.590] | +0.238 [+0.135, +0.333] |
| `/code-review` plus verifier | +0.118 [+0.029, +0.235] | +0.151 [+0.004, +0.292] | +0.134 [+0.043, +0.240] |

Strict recall against `/code-review` was -0.088 [-0.206, +0.029]: `/code-review` caught as
many or slightly more by the strict match, with about 3 times as many findings.

**Caveats.** One model. One 39-case corpus of open-source projects, 34 for the
`/code-review` comparison. One run per case. The verifier is itself a model, not a
person. Recall against the plain prompt is borderline (interval lower bound 0).
Perun still misses about half the bugs, so keep people reviewing too. Full tables:
[`bench-results.md`](.claude/skills/deep-code-review/scripts/fixtures/bench-results.md).
Earlier, different runs (a prompt-only 89-case test and a high-stakes Opus test) are in
[older results](docs/bench/bench90-results.md); they are not today's numbers and are not
comparable with the tables above.

**On the strongest model the review method ties a plain prompt (measured 2026-10-13).**
The same 39 cases on `claude-opus-5-5`: plain prompt F1 0.772, Perun 0.777 (difference
+0.005, interval -0.051 to +0.061), (per-run cost was not published for this run). A second
independent pass raised recall from 0.69 to 0.74 (+0.05, interval 0.00 to +0.13) at twice
the cost. Extra probe steps were tried on 24 further cases, did not help, and were not
shipped. The advantages in the tables above are measured on the mid-tier model only.

**With tools enabled (the reviewer may run commands), measured 2026-10-13.** 50 Node and
Python cases on `claude-sonnet-5-5`, pooled over repeated runs: Perun caught 48.0% of the
known bugs against 43.3% for a plain prompt with the same tools (+4.7 points, interval +0.7
to +9.3); precision was equal (80%); F1 0.601 against 0.563 (+0.038, interval -0.006 to
+0.086, a tie); per-run cost was not published for this run. Extra "run a probe for each candidate" and
"compare old and new behavior" steps, and a much shorter core file, were tested and either
did not help or made results worse; none shipped. Plainly: on small bug-fix diffs Perun is
a little better than a plain prompt at finding bugs on the mid-tier model and no better on
the strongest one. Its clear advantage is far fewer false alarms than `/code-review`.

**Large changes, measured 2026-10-14.** On 78 real change ranges of about 490 changed lines
across 14 files, one review pass found 31% of the known bugs, with or without Perun's method
(27.5% against 25% on the first 40 cases, a tie). What raised that number was spending more:
five independent passes found 47%, a chunked review (`partition_diff.py`) found 46% at the
same cost, and both together found 58%. No method beat plain repeated passes at equal cost.
Perun ships the splitter and this recipe so the trade is explicit; it does not claim a
smarter reviewer.

**Against other review skills, measured 2026-10-14.** On 37 of the same bug-fix cases
(`claude-sonnet-5-5`, read-only file tools, same day, same scorer), Perun was compared with
three widely used, locally runnable review instructions: obra/superpowers
`requesting-code-review`, the `code-reviewer` agent from Anthropic's pr-review-toolkit plugin,
and the `code-reviewer` agent from wshobson/agents. The pass mark was written down before the
run: "better" only if the F1 difference's 95% interval stays above 0. Result: a tie with all
three. Every arm caught the same share of known bugs (29.7%); F1 was 0.442 for Perun against
0.430, 0.451 and 0.422. Perun's findings were real more often than a plain prompt's (86%
against 73%) and wshobson's (72%); the pr-review-toolkit agent reported fewer findings and
was the most precise (93%, a tie with Perun). Perun cost $0.136 per case against $0.090 to $0.098 for the others (review calls only; 1.4 to 1.5 times).

**What a caught bug costs (computed 2026-10-19 from committed files).** Per bug found,
Perun costs more than the cheapest rival, and its recall gain over it is not measured. On
22 patch-only cases, with raw outputs committed: Perun caught 13 of 22 bugs at $0.093 per
caught bug (review calls only), the Anthropic toolkit reviewer 12 of 22 at $0.030, about 3.1
times as much. Recall was 0.591 against 0.545 (the intervals overlap), and false alarms
were equal at 0.50 per case. Per case, review cost was $0.0551 against $0.0162 (3.4 times).
On the 37-case run above every arm caught 11 bugs, so cost per caught bug follows cost per
case: $0.457 for Perun against $0.303 to $0.330 for the others (aggregates only; false
alarms per case were not recorded there). Perun's measured edge is fewer false alarms
than `/code-review` and, on two older sets, than a plain prompt; it is not a cheaper bug. Method, intervals and every
set: [cost per caught bug](docs/bench/review-cost-per-recall/README.md).

- **Shorter instructions to read.** AI tools charge by the *token* (a piece of a word).
  The instructions the assistant must read before each review shrank by
  [19%](CHANGELOG.md) (release 1.501.0, counted as characters divided by 4).
- **Safer AI agents.** An *agent* is an AI assistant that can run commands on
  your computer. The installer tells you how to switch on each agent's
  *sandbox* (a fence around what its commands can touch). No number is claimed:
  the effect has not been measured ([host safety](docs/host-safety.md)).

Time saved and money saved have not been measured, so none are claimed. To
estimate them for your team, use the worked formula and the three-step pilot in
[Perun for leaders](docs/for-leaders.md).

## Quick start

You need `git`, a terminal, and an AI coding agent such as Claude Code or
Cursor (the installer lists the others it supports). No terminal? Paste the
skill into any AI chat instead: [getting started](docs/getting-started.md).

**Fastest: Claude Code plugin.** Two commands, no download:

```
/plugin marketplace add protocol/perun
/plugin install perun@perun
```

The plugin installs every skill, while `install.sh` below defaults to review-only.

Other hosts, one native command each:

- **Codex:** `codex plugin marketplace add protocol/perun`, then `codex plugin add perun@perun` (smoke-tested against a local checkout).
- **Gemini CLI:** `gemini extensions install https://github.com/protocol/perun` (loads `AGENTS.md` as context only; not smoke-tested, the CLI is not installed here).
- **GitHub Copilot CLI:** `copilot plugin marketplace add protocol/perun`; Copilot also reads the shipped `.claude-plugin/marketplace.json` (not smoke-tested).

Or install with the script:

1. **Download Perun:**

   ```bash
   git clone --depth 1 https://github.com/protocol/perun.git
   ```

2. **Install it into your project.** It copies text files only, with no
   admin rights, and adds files only inside your project's `.claude`, `.cursor`
   and `.agents` folders ([`install.sh`](install.sh)):

   ```bash
   perun/install.sh /path/to/your/project
   ```

3. **Ask your agent to review a real file you care about.** Type
   `run a deep code review FILE src/checkout.py`. `FILE` is a literal keyword:
   type it as written, then put your own file's path after it.

4. **Check the install.** Run the command the installer printed last (shown
   below); it confirms Perun is installed and working:

   ```bash
   python3 perun/scripts/perun_doctor.py /path/to/your/project
   ```

What step 2 prints (shortened; your version and paths will differ). The last
line names the check in step 4:

```
installed: deep-code-review 1.535.0 (@ 84acfb19) -> your-project/.claude/skills/deep-code-review
safety: Claude Code: OS sandbox is off by default; set sandbox.enabled=true (or run /sandbox) and keep allowUnsandboxedCommands=false. https://code.claude.com/docs/en/sandboxing
Perun installed 1 skill(s) into 3 tool folder(s) of your-project.
Next, run this one command to confirm it works: python3 perun/scripts/perun_doctor.py your-project
```

The "safety" line is the sandbox setting to switch on for that agent. The "3
tool folders" are where different agents look for skills, so one install works
for several of them.

What step 3 gives you: a list of problems, worst first, on a six-step scale
from Blocker (stops the software working) to Nit (style only). Each problem
names the file and line, the evidence and a fix. A made-up example from the
[example report](docs/example-review-report.md):

```
### F3 - High - CONFIRMED
Inbound webhook accepts unsigned body
- Evidence: routes/hooks.mjs:22 parses JSON; no signature check.
- Fix: verify the signature; bind the account to the verified sender.
```

"CONFIRMED" means the assistant re-checked the problem against the exact code
it reviewed, not just suspected it.

## About the name

Perun is the project's name (after the Slavic thunder god of order). The
code-review skill inside it is still called `deep-code-review`, after what it does.

## Who it's for

- **Engineers:** a repeatable review of a file, a branch or a whole project,
  with evidence for every problem.
- **Team leads:** a ranked report you can check, plus a pilot plan
  ([Perun for leaders](docs/for-leaders.md), [team install](docs/team-install.md)).
- **Non-technical teams:** no licence fee ([MIT](LICENSE)), only your AI usage
  cost, and a plain-English summary of risks and decisions
  ([Perun for leaders](docs/for-leaders.md)).

## Safety

Perun is instructions, not a service: your code goes only where your agent
already sends it. Switch on your agent's sandbox and keep human review
([host safety](docs/host-safety.md), [`SECURITY.md`](SECURITY.md)).

## Learn more

- [Perun for leaders](docs/for-leaders.md): a worked story, what each role
  gets, a pilot plan, limits, a glossary and an FAQ.
- [Getting started](docs/getting-started.md): every install option, optional
  skills, updating and removing.
- [Example report](docs/example-review-report.md); the
  [test method](scripts/bench_corpus.py) and
  [cases](scripts/eval-fixtures/bench/) behind the numbers.
- [Technical overview](docs/technical-overview.md),
  [token cost tips](docs/token-cost-tips.md),
  [running many agents](docs/for-fleets.md), [roadmap](docs/roadmap.md).
- Contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md), rules in
  [`CLAUDE.md`](CLAUDE.md), verified standards in
  [`docs/standards-index.md`](docs/standards-index.md),
  [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md),
  [CI status](https://github.com/protocol/perun/actions/workflows/ci.yml).

[MIT](LICENSE). Credits and sources: [`docs/standards-index.md`](docs/standards-index.md).
