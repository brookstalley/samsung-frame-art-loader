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

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Final

from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass, VocabularyKind


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

    `UNRESOLVED` is a first-class outcome, not an absent row. Dropping such a work
    from the batch discards a real signal, and attaching a low-confidence
    near-match actively launders it. **What the signal says depends on which route
    reached it** — see `UnresolvedReason`, which is set on the same write. Only
    `NOT_HELD` is evidence that phase 1 may have invented the work; the others mean
    the collection has it and cannot offer it in a usable form, or that the curator
    has already turned down what it offered.
    """

    PENDING = "pending"
    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"


class WorkProvenance(StrEnum):
    """Who put this work in front of the curator — the model, or the collection.

    **The distinction is a promise, not a label.** A `PROPOSED` work is one phase
    1 named and phase 2 tried to confirm; an `OFFERED` work is one a wired
    collection holds, drawn by filtering that collection and carrying its own
    title and attribution verbatim. Presenting the second as the first is exactly
    the confident near-match this product forbids — the curator would be shown a
    work the model never named, under a name it did — so the two are held apart
    at the record rather than at each surface that renders them.

    `PROPOSED` is the default everywhere it is absent, which is what lets rows
    written before the column existed read correctly: every one of them came from
    phase 1, because nothing else could write a candidate work then.
    """

    PROPOSED = "proposed"
    OFFERED = "offered"


class UnresolvedReason(StrEnum):
    """Which kind of nothing an unresolved work came back with.

    A bare `UNRESOLVED` cannot distinguish a title nobody holds from a scan too
    small for the wall, and neither a curator nor anyone diagnosing a run
    afterwards can act without knowing which. The routes are not interchangeable:
    `NOT_HELD` is a fact about the collection, `IDENTITY_REFUSED` about two
    spellings of a name, `SIZE_UNKNOWN` and `BELOW_FLOOR` about the record, and
    `ALL_REJECTED` about the curator.

    **The value is derived, never asserted by a caller.** It records decisions the
    judgement already makes and would otherwise throw away, so it cannot disagree
    with what is actually stored — the same reason the status beside it is read
    from a work's instances rather than passed in.

    `depth` is how far a work got before it was refused, and it is what settles a
    work whose results were refused at several different gates: the deepest gate
    any of them reached is the most informative thing that is true. It is a
    property here rather than an ordering written at the derivation site because a
    sixth member added without a depth is then a failure at definition rather than
    a silent tie broken by whichever result the provider happened to return first.
    """

    NOT_HELD = "not_held"
    IDENTITY_REFUSED = "identity_refused"
    SIZE_UNKNOWN = "size_unknown"
    BELOW_FLOOR = "below_floor"
    ALL_REJECTED = "all_rejected"

    @property
    def depth(self) -> int:
        """How far the work got before this gate refused it. Higher is further."""
        return _REFUSAL_DEPTH[self]


#: Ordered shallowest to deepest, which is the precedence when several apply.
#:
#: **Only the first three are ever ranked**, and they are the three a search can
#: refuse a result at. `BELOW_FLOOR` and `ALL_REJECTED` are read from rows the work
#: already holds, which the derivation consults *before* it looks at any refusal at
#: all — so their entries here are never compared against anything. They are listed
#: for totality, so that `depth` is defined for every member and a sixth one cannot
#: be added without deciding where it sits; their equal value records that ranking
#: them against each other would be meaningless, since rejected instances are
#: filtered out before the floor applies and a work can only ever be one of them.
_REFUSAL_DEPTH: Final[dict[UnresolvedReason, int]] = {
    UnresolvedReason.NOT_HELD: 0,
    UnresolvedReason.IDENTITY_REFUSED: 1,
    UnresolvedReason.SIZE_UNKNOWN: 2,
    UnresolvedReason.BELOW_FLOOR: 3,
    UnresolvedReason.ALL_REJECTED: 3,
}


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

    `CONVERSATION_TOKENS` is intent-forming spend, and it is deliberately **not**
    attributed to the run a conversation eventually seeds. "What did talking
    cost" and "what did asking for Kandinsky cost" are separate questions, and
    folding the first into the second would make a run's `estimated_cost_usd`
    unfalsifiable against its actuals — the estimate never covered the
    conversation.
    """

    DISCOVERY_TOKENS = "discovery_tokens"
    WEB_SEARCH = "web_search"
    IMAGE_RESEARCH = "image_research"
    MAT_COLOR_VISION = "mat_color_vision"
    CONVERSATION_TOKENS = "conversation_tokens"


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
    #: Whether the model named this work or a wired collection offered it. Not
    #: optional and not nullable in the record, because every work has one: a row
    #: whose provenance nobody set is a row phase 1 proposed, that being the only
    #: thing that could write one before collections were browsable. The *column*
    #: is nullable so the widening step can add it to files already on disk, and
    #: a null read back means `PROPOSED` for the same reason.
    provenance: WorkProvenance = WorkProvenance.PROPOSED
    resolution_status: ResolutionStatus = ResolutionStatus.PENDING
    verdict: Verdict = Verdict.PENDING
    artwork_id: str | None = None
    proposed_artist: str | None = None
    #: The browse query that produced an offered work, and how many works that
    #: query matched in the collection. `None` on a proposed work, which no query
    #: produced — and a set value on a proposed row is a bug.
    #:
    #: **Null does not mean proposed. `provenance` is the only thing that says
    #: which a work is.** An offered row written before these columns existed
    #: carries nulls too, so `offered_for_artist is not None` reads as "offered"
    #: for new rows and mislabels every older one. The reader below spells out the
    #: same thing from the other side; both are here because this is precisely the
    #: inference a reader makes on seeing two fields only one provenance ever
    #: sets.
    #:
    #: **Held as facts rather than folded into `rationale`.** The sentence they
    #: belong to is about the query, not the work: `product-brief.md` requires a
    #: curator to be able to tell being offered one work out of four hundred from
    #: one out of one, and asks that it be said once where the query's works are.
    #: Composing it per work put a per-group fact on a per-work field, which is
    #: how one run came to print the same thirty-word sentence twelve times.
    #:
    #: **`matched` is the collection's total and is never capped.** The per-run
    #: bound is applied after the browse, so a capped value would silently become
    #: the same number as the cards on screen and destroy the very comparison the
    #: requirement exists for.
    offered_for_artist: str | None = None
    offered_artist_matched: int | None = None
    #: Which kind of nothing, when `resolution_status` is `UNRESOLVED`; `None`
    #: otherwise. The two travel together on every write, so a work can never
    #: report that it found nothing without saying what kind of nothing it was.
    unresolved_reason: UnresolvedReason | None = None
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
    #: Set for intent-forming spend, and **nulled rather than cascaded when the
    #: conversation is deleted**: the money was spent whatever became of the
    #: thread, and a ledger whose totals fall when somebody tidies a transcript
    #: is the under-reporting this table exists to prevent.
    conversation_turn_id: str | None = None


class AffinitySentiment(StrEnum):
    """How warmly the curator holds a thing.

    Four values rather than a number, and **warmth is only half of a judgment** —
    `Affinity.open_to_more` carries the other half. "Meh on Magritte, but open to
    learning more" is two facts, and a single scalar renders it as a low value
    indistinguishable from "never show me this again".
    """

    LOVES = "loves"
    LIKES = "likes"
    COOL = "cool"
    DECLINES = "declines"


class AffinityDerivation(StrEnum):
    """Where a claim about the curator's taste came from.

    Deliberately *not* `FacetDerivation`, which is a different question with two
    answers about where a claim about a *work* came from. Only `VocabularyKind`
    is shared between the two sides; folding the derivations together would offer
    `observed` to a facet and `sourced` to a taste.

    **`OBSERVED` is a claim only the review path can honestly make**, and no
    caller may write it: it means the product read the judgment out of accept and
    reject behaviour, and a row asserting behaviour that never happened is
    indistinguishable afterwards from one the product earned.

    **`INFERRED` and `OBSERVED` both require a `rationale`.** It is the only
    evidence that survives a deleted conversation — `source_turn_id` is nulled
    rather than cascaded — and an inferred judgment with neither turn nor
    rationale is one the product can neither explain nor revisit.
    """

    STATED = "stated"
    INFERRED = "inferred"
    OBSERVED = "observed"


@dataclass(frozen=True, slots=True)
class Affinity:
    """One standing judgment about a thing the curator has reacted to.

    Retained across conversations by design, and the thing a new conversation
    opens knowing. Unique on (`kind`, `value`): one live judgment per thing,
    corrected in place rather than accumulating a history of contradictions the
    product would then have to arbitrate between. The history that matters is the
    turns, which are retained separately.

    **`value` is a string and never a foreign key, and that is this record's
    central decision.** The product exists to surface artists the curator could
    not have named, so the overwhelmingly common case at the moment an affinity is
    written is an artist with no row in this catalogue at all. An FK would make
    the taste model unable to hold exactly the judgments it exists to hold, and
    would invert the flow: you could only love an artist you already owned.
    `artist_id` *follows* the name where a match happens to exist, and its absence
    means nothing.

    **`source_turn_id` may be null on an `inferred` row, and that is a legal state
    rather than a corruption.** Deleting a conversation nulls it. The rule that an
    inferred judgment cites a turn is an invariant on the **write path** — see
    `services/taste.py` — and building it into the file would make the delete
    impossible, which is the opposite of what the deletion ruling asks for.
    """

    id: str
    kind: VocabularyKind
    value: str
    sentiment: AffinitySentiment
    #: Whether to keep offering this. **Independent of `sentiment`**, so a
    #: lukewarm reaction cannot silently blacklist an artist the curator
    #: explicitly asked to keep hearing about.
    open_to_more: bool
    derivation: AffinityDerivation
    created_at: datetime
    updated_at: datetime
    #: The account of the judgment in the curator's terms. Null is normal for
    #: `stated`, where the curator's own words are the account; required by the
    #: write path for the other two, where it is the only evidence a deleted
    #: thread leaves behind.
    rationale: str | None = None
    #: The turn this was derived from, where one is cited and still exists.
    source_turn_id: str | None = None
    #: Set only where `kind` is `artist` **and** the name resolves to a catalogue
    #: artist. Derived and re-derivable; never the identity.
    artist_id: str | None = None


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


class TurnRole(StrEnum):
    """Who spoke a turn — the product's own two words, not the provider's.

    `CURATOR` and `SYSTEM`, never `user`/`assistant`. The distinction is not
    pedantry: the provider refuses a role it does not know (measured — *"curator
    is not one of ['system', 'assistant', 'user', 'tool', 'function']"*), so the
    translation to its vocabulary happens once, at the client seam, and the
    transcript a curator reads back is in the product's terms rather than in a
    chat API's.
    """

    CURATOR = "curator"
    SYSTEM = "system"


@dataclass(frozen=True, slots=True)
class Conversation:
    """One intent-forming session.

    **Not a run, and never confused with one:** it acquires nothing, writes no
    `Artwork`, and reaches no museum API to *resolve* anything. It ends by
    seeding a `DiscoveryRun` or by ending.

    `summary` is a short account of where the conversation got to, written at
    rest for the list. **Never read back as taste** — `Affinity` is the only
    thing the product consults for that, and a summary consulted as one would be
    a second, prose-shaped opinion about a curator free to drift from the
    recorded one.
    """

    id: str
    started_at: datetime
    #: Orders the conversation list, and indexed for it. Distinct from
    #: `started_at` because a thread returned to a week later is the one a
    #: curator is looking for, and the day it began says nothing about that.
    last_turn_at: datetime
    summary: str | None = None


@dataclass(frozen=True, slots=True)
class ConversationTurn:
    """One thing said in a conversation, and what it offered.

    `ordinal` orders the thread and is unique per conversation. **Not a
    timestamp**: two turns can share a second — the curator's question and the
    answer to it routinely do, since the answer is written in the same request —
    and an order derived from time would then be a coin toss.

    `text` is verbatim and required. A model turn that was cut off arrives from
    the provider as `content: null`, and storing that null is what would make the
    *next* turn fail with a refusal about a required content field rather than
    about anything that went wrong. So the column cannot hold one, and the empty
    string is what a turn with nothing in it holds.

    `committed_run_id` is the seam. It is set on the turn where the curator
    committed a direction, and it is the only edge from this side of the product
    to a `DiscoveryRun`.
    """

    id: str
    conversation_id: str
    ordinal: int
    role: TurnRole
    text: str
    created_at: datetime
    #: What this turn offered, as `[{kind, value, samples}]`. Denormalised on
    #: purpose: a record of *what was said*, not a live index — so a thread read
    #: back next month shows the pictures it showed at the time rather than
    #: whatever the collection would answer today.
    suggested: Sequence[Mapping[str, Any]] | None = None
    committed_run_id: str | None = None
