---
artifact: observability-strategy
version: 1
depends_on:
  - artifact: product-brief
  - artifact: architecture
  - artifact: nonfunctional-requirements
last_validated: null
---

# Observability Strategy

**The defining constraint: failure is silent by construction.** The only feedback
channel the household has is a picture on a wall, and a stalled loader is
indistinguishable from a working one showing a static image. Everything below
exists to make "down" distinguishable from "up", because nothing about the
product's own behaviour does that.

Scaled to a medium-risk single-household product: **structured logs, one health
surface, and no backends.** No metrics store, no tracing collector, no dashboards.
Naming what is deliberately absent matters as much as what is present — a future
reader should not conclude these were forgotten.

## Signals

| Signal | Present? | Where |
|---|---|---|
| Structured logs | **Yes** — the primary signal | Both planes, to the systemd journal |
| Health/heartbeat state | **Yes** | Display writes it; the curation UI reads and displays it |
| Spend | **Yes** — read from the authority | `GET /api/v1/key` → `limit_remaining` |
| Metrics (time series) | No | No store, no query surface, nobody to read them. Revisit only if a real question needs a trend |
| Distributed tracing | No | Two processes with no request/response between them. There is no distributed call to trace |
| Uptime monitoring (external) | No | Follows from the operator's alerting decision below |

`3tears-observe` is available on the curation plane and carries structured logging
plus OpenTelemetry at no infrastructure cost. **Take the structured logging; leave
the OTel export unconfigured** — an exporter with no collector is machinery
pretending to be observability. The display plane does not depend on 3tears at all
and uses stdlib `logging` with the same structured shape.

## Two Defects to Fix, Not Inherit

These are named specifically because they exist in the 2024 code and are the exact
shape of failure this strategy exists to prevent.

**`upload_file` catches every exception, logs it, and returns success anyway** —
recording a null content id while the retry loop sets `success = True`. This is
worse than no logging: it produces a log line *and* a false success, so the system
actively asserts a thing that did not happen. The rule it violates is already a
recorded norm (never report success on a failed operation), and it is why the
"catch specific exceptions" preference has an advisory audit home rather than a
janitor one.

**`print()` is used for operational output throughout** (`ai.py`, `display.py`,
others), producing journal lines with no level and no timestamp. Under systemd
that means failures are present in the journal but unfilterable and unsortable —
technically logged, practically invisible. Already a Critic-enforced preference;
converted on touch.

## Correlation

Deliberately minimal, because the topology does not need more.

- **`run_id`** — a discovery run's correlation key, on every log line emitted
  during that run on the curation plane. This is the one place where a single user
  action fans out across minutes and many external calls, so it is the one place a
  correlation key earns its keep. **This covers re-searches too**, since
  `resolve_images` creates a `DiscoveryRun` with `kind='resolve'` (2026-07-20) —
  before that decision the product's second paid, minutes-long fan-out emitted log
  lines with no correlation key at all. Where a resolve run's lineage matters, it is
  `parent_run_id`, not a second field on the log line.
- **`work_id`** — the only identifier that spans both planes. It appears in
  curation logs, in the theme manifest, and in display logs. That is sufficient to
  answer "why is this artwork behaving oddly" across the process boundary.
- **`run_id` deliberately does not cross into display.** The manifest is a
  statement of *current state*, not a record of the run that produced it. Carrying
  a run id into it would imply a provenance relationship the manifest does not
  have.

There is no request-id propagation between planes because there are no requests
between planes.

## The Health Surface

**Display writes a heartbeat; curation reads and displays it.**

The display plane writes a small status document to the shared directory on a
regular interval, using the same atomic write-and-rename discipline as the
manifest. It carries: timestamp, the manifest version currently loaded, the work
currently displayed, TV connectivity state, e-paper state, and the last error if
any.

> `[DECISION: display writes a heartbeat file rather than curation reading
> display-state.sqlite directly | a file keeps the planes' schemas decoupled and
> reuses a discipline already proven for the manifest, where a cross-process read
> of another plane's database would couple curation to display's internal schema |
> user can veto/override]`

This does not violate the manifest-only norm, which governs the curation → display
direction. The heartbeat runs display → curation, and it creates no availability
dependency for the display plane: display writes it and never checks whether
anyone read it.

### The panel shows staleness in absolute terms

**Never a green dot.** The health panel displays "last heartbeat: 4 days ago", not
a status light. A green indicator that is green because nothing checked is exactly
this product's characteristic failure wearing a UI, and it would be worse than no
panel at all because it manufactures false confidence.

The same rule applies to every derived status the panel shows: state the
observation and its age, not a verdict.

### Accepted detection latency, stated as a number

**Alerting decision, 2026-07-20:** the operator chose the curation UI health panel
as the only alerting surface — no push notifications, no email, no external
monitor.

The consequence, recorded honestly rather than left implicit: **mean time to
detection is bounded by how often the curator opens the UI**, which for a leisure
activity done in short sessions may be days. Nothing detects a stalled display
plane in the meantime.

This was stress-tested and holds up. If the display plane stalls, the TV keeps
showing the last selected work — the household sees art, just not rotating.
Budget exhaustion and disk-full are self-announcing at the next curation session,
because that is when they block something. The one failure that is genuinely bad
while undetected is **the label disagreeing with the artwork**, which shows guests
confidently wrong information; it is minor, and it is the thing to watch if this
decision is ever revisited.

Deferred rather than rejected: a push notification path (self-hosted ntfy or
similar) for the small set of conditions that would want a human now. Revisit
trigger: if undetected staleness turns out to be annoying in practice, or if
unattended/scheduled discovery is ever added — the latter removes the curator from
the session, which is what makes self-announcing failures self-announcing.

## Spend as an Observability Signal

Spend is a *signal* here, not only a cost control: the hard cap cannot be trusted
to fail closed without something reading it.

**Read from the authority, never from a local tally.** `limit_remaining` from
`GET /api/v1/key` is the budget-left number, and per-generation `cost` is the
actual spend for a run. A local counter would be a second source of truth for a
number the provider owns, and the two would drift — which is the reasoning behind
the ratified provider-enforced-ceilings norm.

Surfaced in two places: before a run (the estimate, so the curator can decline)
and after (the actual). `halted_by_budget` is a first-class outcome that must be
distinguishable in both logs and tool results from an ordinary failure — an agent
has to be able to tell "you are out of money" from "the fetch failed" and stop
rather than retry.

## Sensitive Data in Logs

**No secret may ever reach a log line.** This has unusual force here because the
repository is **public** and log excerpts are exactly what gets pasted into a
GitHub issue. Concretely: no OpenRouter API key, no TV pairing token, no full
`Authorization` header, no `.env` dump on startup.

Beyond credentials there is very little to filter — no PII, no accounts, no user
records. Prompts and model responses may be logged freely; they contain artwork
metadata and curatorial intent, nothing personal.

## What Each Failure Looks Like

The practical test of this strategy — for each failure in `architecture.md`, what
signal exists:

| Failure | Signal |
|---|---|
| Display plane stalled or dead | Heartbeat stops advancing; panel shows its age |
| TV unreachable | Heartbeat carries TV connectivity state; WARNING in the journal |
| Manifest references a missing file | WARNING per work, and the work is skipped — the run continues |
| Manifest major version unrecognised | ERROR, previous manifest retained |
| Budget exhausted | `halted_by_budget` outcome, plus `limit_remaining` at zero in the UI |
| Disk nearly full | Guarded *before* acquisition starts, not discovered as an exception during it |
| A work silently absent from a theme | **The manifest build reports exclusions** with a per-work reason — see `architecture.md`. Not a log line: a first-class UI surface |
| Mat colour degraded to the dominant-colour fallback | Recorded on the record itself (`MatColor.method`), not merely logged. The 2024 code degrades invisibly |
| Curation killed mid-run (OOM, deploy restart, crash) | **Startup reconciliation logs one line per run it moves to `interrupted`**, at WARNING, with the run id and its prior status. This is the only signal that a run died — the dying process cannot report its own death, and the operator's next clue would otherwise be `resolve_images` refusing work ids. Silence here means reconciliation did not run, which is itself the bug (`data-model.md` → State Machines) |
