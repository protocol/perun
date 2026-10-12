# Time, dates & time zones

Read this when reviewing anything that **stores, computes, schedules, or renders**
timestamps, durations, recurring events, or calendar math — especially across time
zones or a DST transition. Expands domain **A** of `SKILL.md`; cross-ref domain **W**
(`domain-w.md`, cron/jobs) and domain **E** (`billing-correctness.md`, usage
windows). The one-line rule in `domain-a.md` points here for depth.

---

## The distinction everything hangs on: an *instant* vs a *wall-clock* time

- An **instant** (exact / absolute time) is the same everywhere — a log line, a
  `created_at`, an event that already happened. Store it in **UTC**, render it in the
  viewer's zone. "Store in UTC" is correct **here**.
- A **wall-clock time** (local / clock time) is what a human reads off a clock —
  "9:00 am", "the 1st of the month" — and is meaningful only against a time zone. TC39
  Temporal draws the line: wall-clock time "depends on the time zone of the clock" while
  exact time "is the same everywhere"; a zoned datetime "encapsulates ... an exact time
  ... its wall-clock equivalent ... and the time zone that links the two." Local rules
  are set by governments and can change abruptly. (A wall-clock value carried with **no**
  zone at all — a "floating" time — is a third, weaker thing: "the same clock reading
  everywhere," which is *not* what a per-zone recurrence wants.)
- **The finding.** A **wall-clock-anchored recurring** event — a daily 9am reminder, a
  recurring meeting, a monthly invoice date — that bakes in a **single UTC instant at
  creation** drifts by the DST offset after a transition (9am silently becomes 8am or
  10am). The blanket rule "store *everything* in UTC" is **wrong** for this case. Store
  the **local wall-clock time + the tz-id** (on the wire, exactly the pair RFC 9557
  encodes — an RFC 3339 timestamp annotated with its IANA zone, e.g.
  `2022-07-08T00:14:07+01:00[Europe/Paris]`) and **re-resolve the UTC offset per
  occurrence**, not once. Match the representation to the feature: a past/point instant
  → UTC; a future wall-clock commitment or recurrence → local time + tz-id, resolved to
  an instant late (at/near each occurrence).
- **A default-argument clock captures the *server's* zone on a server-rendered path.** A
  testability seam like `function render(now: Date = new Date())` is fine until a **server-rendered**
  call site omits the argument: the default is evaluated on the server, so `new Date()` reflects the
  **server's** clock, and any `toLocale*` / format that reads the ambient zone renders in the
  **server's** time zone, not the request's or the user's — a date renders a day off, or a "today" boundary lands in the
  wrong zone, only under SSR and only for users in other zones. Pass the request's time (and the
  user's/target zone) explicitly on any rendered path; a `= new Date()` default is a test
  convenience, not a request clock.

## The boundary layer: the *kind* is assigned where a string, a wire payload, or a column becomes a typed time

The taxonomy above is about which kind a value **is**; this is about where the kind gets
**assigned** — silently — at the three edges where an untyped value crosses into a typed
time. Each edge can stamp the **wrong** kind onto a value while every later computation
(DST math, bucketing, durations, overflow) stays correct: a value that entered as the wrong
kind is already lost **upstream** of all of that. Three faces, by boundary.

- **Face 1 — the PARSE site (a string → an instant).** In JavaScript, `new Date('2026-03-14')`
  / `Date.parse('2026-03-14')` on a **date-only** string is parsed at **UTC** midnight — MDN:
  a date-only ISO string "will imply UTC time because it's date-only." But the *same* calendar
  day written **with a time and no offset** — `'2026-03-14T00:00:00'` — is parsed at **local**
  midnight — MDN: "set to ... in the local timezone of the system, because it has both date and
  time." So two spellings of one intended day resolve to instants that differ by nearly a day,
  and a date-only value formatted back with a viewer-local formatter renders the **previous
  calendar day** for any viewer behind UTC. **Frame it honestly:** only *this* asymmetry
  (date-only → UTC vs date-time-without-offset → local) is specified; beyond ISO the behavior is not — MDN:
  "Other formats are implementation-defined and may not work across all browsers" — so a slash
  form (`'2026/03/14'`), an `MM/DD/YYYY`, or **any non-ISO string handed to `new Date()` is
  unportable**, not reliably local, not reliably anything. Fix: keep a calendar day in **one
  frame** — compare/format the `YYYY-MM-DD` string as-is, or parse it explicitly as UTC and
  format with an explicit UTC zone, or hold a date-only **type** (Face 3) — never round-trip a
  bare day through `new Date(str)` + a viewer-local formatter. **Distinct** from the SSR
  default-argument `new Date()` bullet above (the no-arg *now* clock reading the server's zone)
  and from the `toISOString().slice(0,10)` **bucketing** bullet below (truncating an instant you
  already hold); this is the parse of an **incoming string**. Grep-signal in
  `lang-js-ts.md`.
- **Face 2 — the WIRE site (a payload → an instant).** A timestamp **ingested** from a client, a
  file, or a third-party API **with no offset** forces the parser to **guess** the sender's zone —
  and it guesses the receiver's zone or UTC, neither of which is the sender's. This is the
  **receiving** mirror of the `datetime.now()`/`utcnow()`-naive **construction** footgun in
  `lang-python.md` (there you *mint* a zoneless value; here you *accept* one). RFC 3339
  leaves no room for it: the offset is part of the grammar — `time-offset = "Z" / time-numoffset`
  and `full-time = partial-time time-offset` (no brackets — not optional), so a conforming
  `date-time` **carries** one. The subtlety a reviewer must know: `-00:00` is legal and
  **meaningful** — RFC 3339 §4.3, "the time in UTC is known, but the offset to local time is
  unknown," which "differs semantically from an offset of 'Z' or '+00:00'." So require an explicit
  offset on every ingested timestamp, treat a zoneless one as a **defect** (reject, or pin one
  documented assumed zone at the boundary), and read `-00:00` as *UTC-known / local-offset-unknown*,
  not a typo for `Z`. The requirement belongs in the interface contract — cross-ref
  `api-contracts.md`.
- **Face 3 — the SCHEMA site (a column → an instant).** A **civil** date — a date of birth, an
  invoice date, a public holiday, an all-day event — is the *floating* kind the taxonomy names:
  the same calendar date everywhere, with **no** instant attached. Storing it in a **`TIMESTAMP` /
  epoch** column (the type used for `created_at`) **forces** an instant — a midnight in *some*
  zone — and every later zone-conversion for display shifts it a day at the edges: a DOB of
  `1990-05-01` stored as a moment renders as `1990-04-30` for a viewer behind the storage zone.
  "Store everything in UTC" is right for an instant and **wrong** here, and *consistent formatting*
  cannot rescue it, because a moment is legitimately allowed to move under zone conversion — the
  defect is the **type**, not the formatter. Fix: a date-only **type** end to end — a SQL `DATE`
  column, a `LocalDate`, or `Temporal.PlainDate`, which MDN defines as "a calendar date (a date
  without a time or time zone) ... an event on a calendar which happens during the whole day no
  matter which time zone it's happening in" — a type with **no instant to convert**. The taxonomy
  *names* floating time but stops there; this is where it goes wrong in a schema. Cross-ref
  `data-quality.md` (the stored type must match the domain kind).

## Bucketing a stored instant to a calendar day needs *whose* wall clock, not a shared one

Grouping past events into calendar buckets for a **human** report — "which day / week did this
happen in" — is a wall-clock question asked of an **instant**, so it needs the **actor's** UTC
offset, not one shared clock. Truncating a stored UTC timestamp to its own calendar date
(`timestamp.slice(0,10)`, `new Date(ts).toISOString().slice(0,10)`, a UTC day/week-start helper
applied to an event time) misfiles every actor outside UTC by a full day — or, for a weekly
cadence, a full week — for the several hours each day their local date and the UTC date disagree.
This is a **distinct** bug from the "wrong clock for *now / today*" sibling — computing the
*present* date off the server's local zone instead of the single shared UTC frame — and equally from
the SSR default-argument-clock bullet above (whose fix is the *user's* zone, not UTC); both of those
concern a single "current" frame, whereas this concerns bucketing a **past actor event**. Bucketing a *past actor event* has no single right global clock
— attributing one person's action to "their day" requires **their** offset. (The bug is a *silent, accidental* frame — the storage zone chosen by truncation, which nobody
picked — not any shared clock: a **deliberately declared** canonical grid, e.g. an org-wide fiscal or
trading day in one documented zone for cross-actor comparability, is a legitimate design.) It hides precisely in
trees that already did the "obvious" UTC-anchoring fix for "today" and therefore look, and get
cited as, exemplary about dates; a reviewer who sees consistent UTC anchoring for "current date"
and moves on misses that a *separate* function applies that same principle to the wrong *kind* of
value. It is worse when the report reads an empty bucket as signal ("nobody reported this week,"
"silent / overdue"): the mis-bucketed event both lands in the wrong period **and** makes the right
period look emptier than it was. Fix: bucket by the timestamp **converted to the actor's zone**
(store or resolve each actor's tz-id). Prove it with a constructed instant — a US-West evening on a
Sunday whose UTC stamp already reads Monday, plus the mirror case ahead of UTC (early-morning local
Monday, UTC still Sunday) to show the defect is bidirectional.

## Ambiguous & missing local times at a DST transition

At a transition a local time is either **ambiguous** or **missing**, and code that
assumes every local time maps to exactly one instant is wrong at both. Require an
**explicit, documented disambiguation rule**; Python's PEP 495 names the cases: "A
local time that falls in the fold is called *ambiguous*" (fall-back: the hour repeats,
so the local time occurs **twice**) and "A local time that falls in the gap is called
*missing*" (spring-forward: the hour is skipped, so the local time occurs **never**),
with the invariant that "The `fromutc()` method should never produce a time in the
gap." Decide the rule explicitly: for an **ambiguous** time pick the earlier or later
occurrence deliberately (PEP 495's `fold`); for a **missing** time, map it forward to
the post-transition instant or reject it — never leave the choice to a library default.
A scheduler that fires a "2:30 am" job on the spring-forward night, or runs a
fold-hour job twice or zero times, is the finding (same root as the cron DST
double/zero-run in `domain-w.md`).

## The tz database is a dependency that goes stale

Time-zone rules are **data** (the IANA `tz` database, or the platform's ICU), not code,
and change with little notice — so a **future** timestamp converted *before* a rule
change is silently wrong *after* it. IANA's own theory file: "The `tz` database
predicts future timestamps, and current predictions will be incorrect after future
governments change the rules ... if today someone schedules a meeting for 13:00 next
October 1, Dublin time, and tomorrow Ireland changes its daylight saving rules,
software can mess up after the rule change if it blithely relies on conversions made
before the change." Check: the tzdata / ICU version is **pinned and has a real update
path** (a refreshed base image, bundled ICU, or vendored tzdata — not a frozen copy),
and future wall-clock commitments are **re-resolved after a tzdata update**, not frozen
to an instant at creation.

## Durations: monotonic, and not 86,400-per-day

Measure **elapsed time** with a **monotonic** clock, never wall-clock subtraction — a
wall clock can jump backward or forward (an NTP step, a DST change, a leap second) and
yield a negative or wildly wrong duration. Do not assume a **calendar day** is exactly
86,400 seconds — a DST-transition day is 23 or 25 hours (and a leap second adds one), so
"one day later" is not reliably `+86,400 s`, nor an hour always 3,600. A leap second also
breaks fixed-second arithmetic, and one common
mitigation is a **leap smear** — Google "'smeared' the extra second across the hours
before and after each leap" — but a review confirms the approach is **chosen and
consistent** across the fleet (a smeared client against a stepped server disagree by up
to a second), not that `86400` was hard-coded.

## Epoch & field-width limits — time as a stored value can overflow

A timestamp is also a **stored value with a width**, and the width can overflow — a scheduled, dated
failure. A signed **32-bit `time_t`** (seconds since 1970) overflows on **2038-01-19T03:14:07Z** and wraps
negative (the *Year 2038 problem*) — still live in 32-bit builds, embedded/IoT, and older on-disk/wire
formats. Related width bombs: a **millisecond epoch in a 32-bit int** overflows in weeks; a
database/interchange field too **narrow for a far-future date** (a fixed-width or 4-digit-year format, a
`DATE` capped by the UI) silently truncates or rejects a date a user can legitimately enter (a 100-year
lease, a long-dated expiry); and a **duration/deadline computed in 32-bit seconds** overflows on a large
interval. Check: time is stored/transmitted in a **64-bit** (or wider) type end to end (DB column,
serialization, language type, FFI boundary), user-enterable future dates are representable, and any 32-bit
`time_t` dependency (an old lib, an embedded target, a legacy format) has a remediation path. **🚩** a
32-bit `time_t`/`int` holding seconds or ms since epoch; a fixed-width date field narrower than the dates
the domain allows.

## A timestamp is not a unique key — don't use it as a strict-inequality cursor

A "what changed since the last checkpoint" diff that sets its cursor to a **record's own
timestamp** and filters `record.ts > cursor` silently drops the newest change whenever two records
share that timestamp: the newest record's timestamp **equals** the cursor, so strict `>` excludes
it and the diff reports a false "nothing changed." Ties are ordinary, not exotic — one `now()`
reused for several rows in one transaction, a second- or day-granularity column under any real
write rate, or a backfill that stamps a batch with one synthetic time. The fix is a **strictly-monotonic tiebreak** — a sequence id / auto-increment compared as the
composite `(ts, seq)` — not a strict-inequality comparison against a **non-unique** value. An
**ordinal / positional cursor** ("this record's index in the sorted history is strictly after the
cursor's index") also works, but **only** for a genuinely append-only, never-resorted log: a
backfill that inserts a row sorting *earlier* than an already-consumed index (one of the tie-causes
above) silently reintroduces the drop, whereas a monotonic id does not. Same root cause as the
incremental-sync-cursor trap in `domain-a.md` — that is the **paginated /
bulk-fetch face** (drops or double-reads rows at a page boundary); this is the **single-comparison /
since-checkpoint face** (drops the one newest record on a tie). This hides behind code that is
otherwise scrupulously honest: a module that documents "never fabricate an absence" and correctly
handles the truly-empty case (fewer than two records) still renders a false absence on the tie,
because a tie *looks* like the "nothing to compare" empty case when it is really "something to
compare, compared with the wrong operator." The adversarial input is 2+ records with a deliberately
engineered identical timestamp, in the stable-sort order the code produces — not the 0/1-record
empty boundary a reviewer usually tests.

## A pinned test `NOW` fed to code that reads the real clock is a dated failure

The general clock-seam rule lives in `testing-and-evals.md` (*Deterministic & hermetic*); this is its dated failure.

A test pins `NOW = datetime(<fixed date>)` and derives fixtures from it (`released = NOW - 1h`), then
passes them to an entry point that takes no injected clock and measures age against the **real** clock.
The margin argued relative to `NOW` holds only while `real_now - NOW < threshold`; on the day it closes,
every branch goes red at once with no diff to blame, which reads as a flaky gate. For each fixture time,
check **which clock the code compares it against**: a pinned `NOW` is safe only when every clock read in
the exercised path uses that same injected value; otherwise derive the fixture from the real clock at test
time or inject the clock into that entry point too. A test mixing a pinned constant with an un-injected
entry point is a finding even when a comment argues the margin is large. With the clock injected, pin the
threshold itself: one fixture just before, one exactly at, and one just after the boundary. Cheap catch: a CI job that runs
the suite with the clock advanced (+30 and +365 days via a faketime-style shim). When it fires fleet-wide,
treat it as agentic-delivery's `red-gate-triage.md` *fleet-wide finding*: one owner lands one fix while
other lanes hold pushes, then they resync (issues #1140, #1141).

**🚩 red flags**: a recurring wall-clock event stored as one fixed UTC instant; a
future local time whose offset is frozen at creation; a local↔instant conversion with
no fold/gap (ambiguous/missing) handling; `now()`/`datetime.now()` naive (no tz);
`new Date('YYYY-MM-DD')` / `Date.parse` on a bare calendar-day string (parses as UTC,
renders a day early for viewers behind UTC); a timestamp **ingested** with no offset
(the parser guesses the sender's zone); a **civil** date (DOB / invoice / holiday /
all-day event) stored in a `TIMESTAMP`/epoch column instead of a date-only type;
wall-clock subtraction for a duration or timeout; a hard-coded `86400` / `3600*24`;
tzdata/ICU with no version pin or no update path; a blanket "store everything in UTC"
applied to a wall-clock-anchored recurrence; a test fixture built from a pinned `NOW` passed to
an entry point that reads the real clock.

**Validate a calendar-day input with a strict real-day check, not a lenient parse.** `Date.parse` / `new Date(...)` (and any lenient parser) can accept or roll over an impossible day: `2026-02-31` becomes a March date, so a bad value silently lands as a different valid day. At a trust boundary, match the `YYYY-MM-DD` shape, then round-trip it (build the date and confirm year, month and day come back unchanged) or use a strict date-only type. Finding: a date field validated only by "the parser did not return NaN". Test: `2026-02-31`, `2026-04-31` and `2025-02-29` are rejected; `2024-02-29` is accepted.
