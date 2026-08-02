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
| Spend | **Per run, yes; as a live balance, no** | Recorded spend is on the run and reported by the discovery surface. **`limit_remaining` is deliberately not surfaced** — see the note below the table |
| Metrics (time series) | No | No store, no query surface, nobody to read them. Revisit only if a real question needs a trend |
| Distributed tracing | No | Two processes with no request/response between them. There is no distributed call to trace |
| Uptime monitoring (external) | No | Follows from the operator's alerting decision below |

> **On `limit_remaining`, and why this row shrank (2026-08-02).** The Spend row
> read "**Yes** — read from the authority | `GET /api/v1/key` → `limit_remaining`".
> No surface exposes that figure: the client can read it, and nothing in the
> services, HTTP or MCP layers calls the reader. More importantly it should not be
> the budget indicator even once something does — it lags by minutes, and was
> observed reporting credit remaining while live calls were already being refused.
> A panel built from it would tell the operator they had money at the exact moment
> spending stopped working. **Do not ship it as the budget signal**; the honest
> ones are the recorded per-run spend and the `halted_by_budget` outcome. Surfacing
> it as a lagging advisory figure is a decision someone may still make — with the
> lag stated on screen. (`operational-spec.md` § Troubleshooting corrected the same
> claim the same day; this artifact was the copy that sweep did not reach.)

**Both planes use stdlib `logging`, and neither takes a dependency for it.**

> **Corrected 2026-07-27.** This section previously said "`3tears-observe` is
> available on the curation plane and carries structured logging plus
> OpenTelemetry at no infrastructure cost — take the structured logging". The
> 2026-07-27 technology amendment withdrew every 3tears dependency, and nothing
> replaced this claim: `curation/pyproject.toml` does not declare the package, its
> explicit "deliberately not pinned yet" list does not mention it, and the plane
> ships stdlib logging. So the artifact naming structured logs as the primary
> signal rested on a package no manifest carries. The withdrawal was swept through
> the dependency lists and not through here, which is the repo's own recorded
> obligation — retiring a claim is a repo-wide grep, not a local edit.

**Curation's shape is one JSON object per line, and the run id is bound rather
than passed** (built 2026-08-02, `curation/src/curation/logs.py`). This discharges
the debt this section recorded: the plane previously emitted
`"%(asctime)s %(levelname)s %(name)s %(message)s"`, which was enough for startup,
refusals and reconciliation and not enough for the per-run correlation below.

Two decisions worth not re-deriving:

- **JSON, not logfmt.** Both are structured; the deciding case is free text. An
  intent is the curator's own words and goes in a log line, and quoting it into a
  key=value stream is a rule every call site has to get right. A traceback is
  carried as one field for the same reason — multi-line output would break the
  one-line-one-object property the whole shape rests on.
- **`run_id` rides a context variable and is stamped by a filter**, so a module
  that logs inside a run carries the key without knowing runs exist. Threading
  the id through every call site that might log is a discipline, and one
  forgotten site defeats it — the lines lost that way are the ones emitted from
  deep inside a failure, which are the ones worth having.

The OTel question does not reopen: an exporter with no collector is machinery
pretending to be observability.

> **A finding worth keeping, from building it.** The first implementation cleared
> every root handler to make `configure()` idempotent. That silently disabled the
> test harness's own capture, and it failed as *"nothing was logged"* rather than
> as *"your logging setup removed my handler"* — a library evicting handlers it
> did not install is this product's characteristic failure shape in miniature. It
> now removes only its own, and both halves are pinned by test.

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
technically logged, practically invisible. *(Restated 2026-08-01: this said
"Critic-enforced preference; converted on touch", and both halves changed on
2026-07-27. It is now a **linter** rule — ruff `T20` in both `pyproject.toml`s —
and its disposition for the eight legacy modules is a **dated waiver, not
convert-on-touch**: they die with the 2024 modules at the legacy retirement,
because convert-on-touch had no mechanism behind it and all eight were touched without a
single call being converted. Do not convert them against that waiver, and do not
report their survival as a defect. The authority is `project-preferences.md`'s
`T20` row.)*

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
manifest. It carries: the moment it was written, the manifest version currently
loaded, the work currently displayed, TV connectivity state, e-paper state, and
the last error if any.

**Two names in it are a contract, not a suggestion, because the reader is already
built** (`curation/manifest/heartbeat.py`): the file is `display-heartbeat.json`
under `ART_ROOT`, and the timestamp key is **`reported_at`**, an ISO-8601 instant.
The reader treats any other spelling as an unreadable heartbeat and says so — so a
writer that calls the field `timestamp` produces a plane that looks *down* to
curation while running perfectly. That is this product's defining failure mode
manufactured by the mechanism built to detect it, which is why the key is named
here rather than left to the writer. Everything else in the document is the
writer's to shape: the reader hands the whole object through untouched.

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
| Budget exhausted | `halted_by_budget` outcome on the run, and the refusal text names the cause. *(Corrected 2026-08-02: this also promised "`limit_remaining` at zero in the UI" — a figure no surface exposes, and one that lags badly enough to read non-zero while calls are already being refused. See the note under the signals table.)* |
| Disk nearly full | Guarded *before* acquisition starts, not discovered as an exception during it |
| A work silently absent from a theme | **The manifest build reports exclusions** with a per-work reason — see `architecture.md`. Not a log line: a first-class UI surface |
| Mat colour degraded to the dominant-colour fallback | Recorded on the record itself (`MatColor.method`), not merely logged. The 2024 code degrades invisibly |
| Curation killed mid-run (OOM, deploy restart, crash) | **Startup reconciliation logs one line per run it moves to `interrupted`**, at WARNING, with the run id and its prior status. This is the only signal that a run died — the dying process cannot report its own death, and the operator's next clue would otherwise be `resolve_images` refusing work ids. Silence here means reconciliation did not run, which is itself the bug (`data-model.md` → State Machines) |
