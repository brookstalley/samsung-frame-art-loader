"""What the pipeline before acceptance stores: its enumerations and its records.

The counterpart to `records.py`, split the same way the services are: a work that
has been accepted is a catalogue record, and everything it went through to get
there is one of these. They share a file and a transaction, never a table.

**A work is distinct from an image of it, at every stage.** `CandidateWork` is a
work discovery proposed; `CandidateImage` is one image instance found for it, of
which there are usually many. Collapsing them would present a curator with ten
copies of one painting and ask them to approve one — the product failing at the
thing it exists to do, with nothing erroring.

Costs are `Decimal`, never `float`. A tenth of a cent that cannot be represented
exactly is a rounding error in a running total that nobody will ever reconcile
against the provider's own figure.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass


class RunKind(StrEnum):
    """Which of the two phases a run performs.

    A `RESOLVE` run is the re-search behind `resolve_images` — phase 2 on its
    own, over works some earlier run proposed. It is the same entity rather than
    a weaker handle beside it, which is what gives a paid, minutes-long operation
    a status to poll, a cancel, a cost of its own, and a guard against the same
    work being submitted to two of them at once.
    """

    DISCOVERY = "discovery"
    RESOLVE = "resolve"


class InitiatedBy(StrEnum):
    """Which surface started a run.

    Recorded because an agent can start one without the curator watching, so "why
    did forty Dalí candidates appear, and who asked for them" has to be
    answerable from the data — and because it makes agent spend attributable per
    surface rather than only per month.

    It is **not** an authorisation input. Every surface has identical authority;
    branching behaviour on this field would reintroduce the parity split the MCP
    requirement exists to prevent.
    """

    WEB_UI = "web_ui"
    WEB_UI_AGENT = "web_ui_agent"
    MCP_CLIENT = "mcp_client"


class RunStatus(StrEnum):
    """Where a run is, including the six ways it can end.

    **Each terminal state describes a different thing and none may absorb
    another.** `COMPLETED` finished, `FAILED` broke, `HALTED_BY_BUDGET` hit the
    provider's cap, `DECLINED` was priced and refused by the curator, `CANCELLED`
    was stopped on request mid-flight, and `INTERRUPTED` had its process stopped
    underneath it. Collapsing any of them makes a deliberate choice
    indistinguishable from a malfunction: an interrupted run is simply re-run,
    a failed one is investigated.
    """

    RESOLVING_WORKS = "resolving_works"
    AWAITING_APPROVAL = "awaiting_approval"
    RESOLVING_IMAGES = "resolving_images"
    COMPLETED = "completed"
    FAILED = "failed"
    DECLINED = "declined"
    CANCELLED = "cancelled"
    HALTED_BY_BUDGET = "halted_by_budget"
    INTERRUPTED = "interrupted"

    @property
    def is_terminal(self) -> bool:
        """Whether the run is over, however it ended.

        This is what coverage of a work by a resolve run is keyed on, so a state
        wrongly counted as live would refuse those work ids forever.
        """
        return self not in _ACTIVE

    @property
    def is_process_held(self) -> bool:
        """Whether the run only advances while the process that owns it is alive.

        `AWAITING_APPROVAL` is deliberately excluded even though it is active.
        That state advances when the *curator* calls approve; it is durable,
        human-held state that is supposed to outlive a restart. Reconciling it
        would let a `systemctl restart` — the documented deploy step — destroy a
        pending decision along with the phase-1 spend already incurred to produce
        it. A rule justified by process liveness must apply only to the states
        process liveness actually governs.
        """
        return self in _PROCESS_HELD


#: The states a run can still leave under its own power.
_ACTIVE = frozenset({RunStatus.RESOLVING_WORKS, RunStatus.AWAITING_APPROVAL, RunStatus.RESOLVING_IMAGES})

#: The states that only advance while the owning process lives. See `is_process_held`.
_PROCESS_HELD = frozenset({RunStatus.RESOLVING_WORKS, RunStatus.RESOLVING_IMAGES})


class ResolutionStatus(StrEnum):
    """Whether the latest attempt to find an image for a work found one.

    Tracks the **latest** attempt, whether that was the original phase 2 or a
    later re-search — which is what gives a failed re-search a terminal
    representation without adding a verdict value for it.

    `UNRESOLVED` is a first-class outcome, not an absent row: phase 2 finding no
    credible instance is the signal that phase 1 may have invented the work.
    Dropping it from the batch discards that signal, and attaching a
    low-confidence near-match actively launders it.
    """

    PENDING = "pending"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class Verdict(StrEnum):
    """What the curator decided about a proposed work.

    `AWAITING_BETTER_IMAGE` is the verdict an accept/reject binary cannot express
    — "I want this work; this instance is not good enough; find another". It is
    not terminal, and it must never write dedup-key suppression: modelling it as
    a rejection would silently lose a painting the curator explicitly asked to
    keep. It means exactly one thing, a statement of intent, and intent does not
    change when a re-search starts or finishes.
    """

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    AWAITING_BETTER_IMAGE = "awaiting_better_image"

    @property
    def is_terminal(self) -> bool:
        """Whether the curator has finished with this work.

        A resolve run completing must not write over one of these: only the
        curator's verdict is authoritative, and overwriting an acceptance would
        leave a work holding an `artwork_id` and a non-accepted verdict, which
        nothing else in this model can produce or repair.
        """
        return self in _DECIDED


#: The verdicts that are the curator's final word. See `Verdict.is_terminal`.
_DECIDED = frozenset({Verdict.ACCEPTED, Verdict.REJECTED})


class SpendCategory(StrEnum):
    """What a cost was incurred doing.

    `WEB_SEARCH` is separate because it is billed per search rather than per
    token, so a token-only breakdown would misattribute it. `IMAGE_RESEARCH` is
    re-search spend and attributes to the resolve run that incurred it, rolling
    up to the original intent through the run's parent.
    """

    DISCOVERY_TOKENS = "discovery_tokens"
    WEB_SEARCH = "web_search"
    IMAGE_RESEARCH = "image_research"
    MAT_COLOR_VISION = "mat_color_vision"


@dataclass(frozen=True, slots=True)
class DiscoveryRun:
    """One invocation of the discovery flow, and what it cost.

    `intent_text` is the curator's words verbatim, and a resolve run has none of
    its own — it inherits the parent's, which is what keeps "what did asking for
    Dalí actually cost" answerable once spend is spread across a chain of runs.

    `approval_required` is stored rather than re-derived because the threshold it
    was judged against is configuration, and configuration changes. A run that
    stopped for approval last month must still read as "this stopped for
    approval", not as whatever today's threshold would imply.

    There is no `target_candidate_count`: the phase-1 work list *is* the count,
    and it is a reviewable, trimmable list rather than a number guessed in
    advance.
    """

    id: str
    kind: RunKind
    initiated_by: InitiatedBy
    status: RunStatus
    approval_required: bool
    started_at: datetime
    parent_run_id: str | None = None
    intent_text: str | None = None
    strategy: str | None = None
    estimated_cost_usd: Decimal | None = None
    actual_cost_usd: Decimal | None = None
    unresolved_work_count: int | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CandidateWork:
    """A work discovery proposed, and the curator's verdict on it.

    Distinct from Artwork because most candidate works never become one, and
    because a proposed title may be wrong or invented — a model asked for an
    artist's famous works will occasionally produce a plausible one that does not
    exist.

    `work_dedup_key` is the normalised work identity that stops discovery
    re-proposing declined works forever. How it is derived is a separate decision
    with its own evidence to gather; the column is here now because retrofitting
    suppression after rejections have accumulated makes the early ones
    unrecoverable.
    """

    id: str
    discovery_run_id: str
    proposed_title: str
    rationale: str
    work_dedup_key: str
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING
    verdict: Verdict = Verdict.PENDING
    artwork_id: str | None = None
    proposed_artist: str | None = None
    rejected_reason: str | None = None
    decided_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class CandidateImage:
    """One image instance found for a candidate work. Many per work, one selected.

    `confidence` and `quality_score` are separate because they conflict: a
    museum's own page is maximum confidence and may be lower resolution than a
    gigapixel scan elsewhere. Collapsing them into one number makes the trade
    invisible and the choice unexplainable, which is what `selection_rationale`
    exists to show a curator asking *why this one*.

    Losing instances are retained, never deleted. They are what makes an
    over-eager merge inspectable, they are the alternates the review card offers,
    and on acceptance they become the work's non-primary sources — which is what
    makes re-acquisition robust when an institution reorganises its site.

    **"The alternates the review card offers" is a claim about retention, and it
    is correct wherever it appears.** Recorded here, once, because the sentence is
    repeated in several layers and reads like the *ordering* claim that was
    retired across this surface — that a card leads with the choice, that what it
    omits ranks lowest, that its rows are the offerable ones. Those are false in
    states this model allows and were removed. This one only says a losing
    instance is kept and remains available to be chosen, which no cap or ordering
    changes. Whoever next audits that vocabulary can stop here rather than
    re-deriving the distinction.

    `preview_path` is a cached local copy because review must not depend on a
    museum server being reachable. It is disposable: safe to delete once the work
    reaches a terminal verdict, and deleting it never affects the catalogue,
    whose imagery comes from acquisition rather than from a preview.

    `acquisition_method` is carried here rather than decided at acceptance
    because it is knowable only where the instance was found: the search reached
    it through a provider that either offers tiles, a direct file, or an API, and
    nothing downstream can recover which. Without it, promoting an instance into
    a source would have to guess the one field of a source that says how to fetch
    the bytes — and a wrong guess is a re-acquisition that fails at the moment
    every derived file has already been lost.
    """

    id: str
    candidate_work_id: str
    url: str
    provider: str
    source_class: SourceClass
    acquisition_method: AcquisitionMethod
    confidence: float
    is_selected: bool = False
    preview_url: str | None = None
    preview_path: str | None = None
    estimated_width: int | None = None
    estimated_height: int | None = None
    rights_status: RightsStatus | None = None
    quality_score: float | None = None
    selection_rationale: str | None = None
    rejected_at: datetime | None = None


@dataclass(frozen=True, slots=True)
class SpendRecord:
    """What was spent, on what, by which surface. Attribution and history.

    **This does not hold the ceiling and nothing consults it before spending.**
    The cap is a provider-side per-key credit limit that refuses calls once
    exhausted; a local sum that fails open is indistinguishable from one that
    works — no error, no alert, just a bill. What this is for is per-run and
    per-surface attribution, "what did this run cost", and monthly reporting,
    none of which is enforcement.
    """

    id: str
    category: SpendCategory
    cost_usd: Decimal
    occurred_at: datetime
    discovery_run_id: str | None = None
    artwork_id: str | None = None
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    units: int | None = None


@dataclass(frozen=True, slots=True)
class ResolveRunWork:
    """Which candidate works a resolve run covers. A join, nothing more.

    Deliberately not a `resolve_run_id` column on the work: a nullable column
    there would be a second copy of status living beside the run row, free to
    drift from it, and it would lose the history of earlier resolve attempts. A
    join records a fact about the run's *scope*, which does not change when the
    run's status does — so these rows are never deleted, and coverage is released
    by the run reaching a terminal state rather than by the row going away.
    """

    resolve_run_id: str
    candidate_work_id: str
