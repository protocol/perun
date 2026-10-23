# Safety-critical behaviour — fail-safe, limits & hazard warnings (domain F)

Read this when the target can hurt people, property or the environment if it misbehaves: it drives hardware or actuators (vehicle, drone, robot, industrial, building, energy or charging control), is or feeds a medical, health or emergency decision, issues safety-relevant alarms, or takes an irreversible high-value action with no human in the loop. It adds the **safety** lens that ISO/IEC 25010:2023 names as a quality characteristic of its own (it has no 2011 counterpart). Ordinary data loss and security stay in `domain-d.md` and `domain-b.md`; this file starts where the failure's victim is a person or a physical asset. Harm that comes from a model's output or an automated decision reaching end users (bias, hallucination presented as fact, unsafe automation of a high-stakes call) belongs to the `product-output-safety` overlay when it is installed; this file covers the controls on physical and irreversible effects.

## What a review can and cannot say

A review finds missing or weak controls. It cannot certify that a system is safe. Safety regimes (the IEC 61508 functional-safety family and sector standards derived from it, such as ISO 26262 for road vehicles) are named, not walked: route a certification question to the owner and a qualified safety engineer. Do not write "safe", "compliant" or a safety integrity level about a target from a code read; the status is `unverified`, and the finding names the artifact that would resolve it (the hazard analysis, the safety case, the fault-injection results). This mirrors the rule that an ASVS, CIS or SLSA level is never stated unless it was walked (`SKILL.md`).

## The five ISO/IEC 25010:2023 safety sub-characteristics, as probes

For each hazard the target can cause, walk all five. A hazard with no control under a sub-characteristic is a finding, rated below.

**Operational constraint** (the product keeps its operation within safe parameters or states).
- Limits are enforced at the last software boundary before the effect (service, firmware, actuator driver), not only in the UI or the client. A check that lives only in the form is advisory.
- Out-of-range input is rejected or clamped and logged. Silently coercing a bad command into range hides a fault upstream.
- Bounds carry units in names or types, and cover rate of change as well as absolute value.
- A state interlock (a command valid alone but invalid in the current state) reads the current state at the moment of action, not a cached copy.
- A limit cannot be raised by a flag or remote config without a recorded approval (`domain-f.md` already holds the two-key confirmation rule).
- 🚩 a range check only in the UI; a setpoint from a request or queue applied unclamped; an `override` or `force` parameter with no audit trail; the same limit duplicated in two places with different values (a lockstep drift, `domain-h.md`).

**Risk identification** (the product can recognise events that expose life, property or the environment).
- A hazard analysis exists and each hazard traces to a control and a test (hazard, control, test). No artifact means `unverified`, not a pass.
- 🚩 safety claims in a README or PR with no hazard log; a new actuator, mode or feature with no hazard entry; a control named in documentation with no code path behind it.

**Fail safe** (the product places itself in, or returns to, a safe state after a fault).
- Name the safe state per hazard first. It is not always "off": the safe state of a brake, a valve, a fire-route door, a heater and an infusion pump differ.
- On timeout, lost heartbeat, stale, invalid or non-finite sensor input (`domain-a.md`), crash, restart or lost link, the safe state is reached without operator action. The watchdog or heartbeat is enforced on the actuator side: a controller that stops sending must not leave its last command latched.
- After recovery, do not resume a hazardous action from stale state or a replayed queued command. Re-validate current state and permission; retry and idempotency depth is in `reliability-error-handling.md`.
- Fault-inject each path: the test kills the sensor, link or process and asserts the safe state (`domain-j.md`: test the failure, not just the feature).
- 🚩 last command latched on comms loss; a queue or retry that replays an actuator command after recovery; `except: pass` around a sensor read; a default value substituted for a missing reading; a watchdog that lives in the process it supervises.

**Hazard warning** (the product warns of unacceptable risk).
- A warning reaches someone who can act and cannot be silently suppressed. Route it above the rate limiter and debouncer (`domain-f.md`: control-plane traffic above the limiter), and do not let deduplication hide a new, distinct hazard.
- The alarm path itself is monitored: a dead notification channel is a hazard, so it needs its own heartbeat. Alert fatigue is a safety defect, not only noise (`observability.md`, alerting).
- The warning names the hazard and the action, and severities separate "act now" from "for information".
- 🚩 a safety alarm behind the same throttle as marketing notifications; an alert muted after N repeats with no escalation; no test that the alarm fires.

**Safe integration** (safety holds during and after integration with other components).
- Updates, config pushes, feature flags, third-party SDKs, simulators and demo modes cannot disable or bypass a limit. A `SIMULATION`, `DEBUG` or `SKIP_CHECKS` branch must be absent or unreachable in the production artifact.
- Rolling back to the previous known-safe version is tested (`release-engineering.md`, rollback). An update cannot leave a device half-updated in an unsafe state: name the mechanism (staged, atomic, A/B or equivalent).
- 🚩 an `if SIMULATION:` branch that skips a limit and ships; remote config that can raise a limit; an over-the-air update with no rollback path.

## Fail-safe is not fail-closed

The security rule in `domain-b.md` (gates fail closed, prefer allow-lists) can point the opposite way from a safety state. A general-reference definition (Wikipedia, a tertiary source, 2026-10-16): fail-safe means a device "will not endanger lives or property when it fails"; fail-secure, "also called fail-closed", means access or data "will not fall into the wrong hands in a security failure". Its example is a fire: a fail-safe system unlocks doors for escape, a fail-secure one keeps them locked.

For every control that denies or blocks, ask what its failure does to a person. If a block can trap, starve or endanger someone, the safe state may be the open one. Where security and safety conflict, surface both as an owner decision with the hazard named (principles 4 and 5 in `full-map-principles.md`). Do not choose silently, and do not relabel one as the other: a bare "this fails open" finding on a safety path can itself be the hazard.

## Rating

Rate on consequence and reachability like any finding. A reachable path to injury or irreversible physical loss is Critical. A latent one keeps its intrinsic severity and blocks enabling, not unrelated merges. Stage does not relax it: a prototype that can injure is still Critical, the same guardrail as security and data loss. When the harm model is unknown (no hazard analysis, no stated operating environment), say so and rate `unverified` at provisional severity rather than guessing a hazard.
