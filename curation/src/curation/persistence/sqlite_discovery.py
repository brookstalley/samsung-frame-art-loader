"""A `DiscoveryStore` over the same SQLite file the catalogue uses.

The counterpart to `sqlite.py`: it owns the pipeline's tables, the mapping
between its records and rows, and the ordering that makes each listing stable.
Both adapters run over one `SqliteDurableStore`, which is what lets acceptance
write on both sides of the pipeline boundary in one transaction.

Ordering is decided here rather than below because it is a product judgement.
Runs read newest first because a run list is a history. Instances read with the
selected one first where a selection exists, so the automatic choice and any
surface showing it cannot come to disagree about which scan is on offer.

**That ordering is not a statement about which instances are offerable.** A work
whose scans are all below the floor or all turned down has no selection, and then
the leading row is simply the highest-ranked — which may be one already refused,
since refusing a scan does not change how good the picture is. `is_selected` and
`rejected_at` are what answer those questions; position is not. A reader who takes
this order as an offerability guarantee writes a surface that shows a curator
scans they cannot choose.

**The unique index below does not replace the service layer's rules.** Every rule
is applied in the service layer, where a refusal can be phrased for whoever
asked; the index catches the case where some path forgets to, and its message
names only the table.
"""

import json
from collections.abc import Mapping, Sequence
from datetime import datetime
from typing import Any, Final

from curation.persistence.adapter import (
    BY_ID,
    TableAdapter,
    from_iso,
    from_money,
    require_datetime,
    require_money,
    to_iso,
    to_money,
)
from curation.persistence.discovery_records import (
    Affinity,
    AffinityDerivation,
    AffinitySentiment,
    CandidateImage,
    CandidateWork,
    Conversation,
    ConversationTurn,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    ResolveRunWork,
    RunKind,
    RunStatus,
    SpendCategory,
    SpendRecord,
    TurnRole,
    UnresolvedReason,
    Verdict,
    WorkProvenance,
)
from curation.persistence.durable import OrderBy
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass, VocabularyKind

DISCOVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS discovery_runs (
    id                     TEXT PRIMARY KEY,
    kind                   TEXT NOT NULL,
    -- A resolve run's parent is the run that originally proposed these works.
    -- Cost rolls up through this chain, which is what keeps "what did asking for
    -- Dali cost" answerable once spend is spread across several runs.
    parent_run_id          TEXT REFERENCES discovery_runs(id),
    intent_text            TEXT,
    strategy               TEXT,
    initiated_by           TEXT NOT NULL,
    status                 TEXT NOT NULL,
    estimated_cost_usd     TEXT,
    actual_cost_usd        TEXT,
    approval_required      INTEGER NOT NULL,
    unresolved_work_count  INTEGER,
    started_at             TEXT NOT NULL,
    completed_at           TEXT
);

-- Startup reconciliation reads runs by status, on every process start.
CREATE INDEX IF NOT EXISTS discovery_runs_by_status ON discovery_runs(status);
CREATE INDEX IF NOT EXISTS discovery_runs_by_parent ON discovery_runs(parent_run_id);

CREATE TABLE IF NOT EXISTS candidate_works (
    id                 TEXT PRIMARY KEY,
    discovery_run_id   TEXT NOT NULL REFERENCES discovery_runs(id),
    artwork_id         TEXT REFERENCES artworks(id),
    proposed_title     TEXT NOT NULL,
    proposed_artist    TEXT,
    rationale          TEXT NOT NULL,
    work_dedup_key     TEXT NOT NULL,
    -- Nullable so the widening step can add it to files written before
    -- collections could be browsed. A null is `proposed`: nothing but phase 1
    -- could mint a candidate work then, so the absent value has one meaning.
    provenance         TEXT,
    -- Which browse query produced an offered work, and how many works that query
    -- matched in the collection. Both null for a proposed work, which no query
    -- produced. They are stored as facts rather than composed into `rationale`
    -- because the sentence they belong to is per-QUERY: `product-brief.md` asks
    -- that a curator be able to tell one-of-four-hundred from one-of-one, and the
    -- surface says that once for the group. `matched` is the collection's total
    -- and is deliberately not capped by `offered_works_per_run` — the cap is what
    -- the reader reconciles it against, so capping it here would destroy the
    -- comparison the requirement exists for.
    offered_for_artist     TEXT,
    offered_artist_matched INTEGER,
    resolution_status  TEXT NOT NULL,
    unresolved_reason  TEXT,
    verdict            TEXT NOT NULL,
    rejected_reason    TEXT,
    decided_at         TEXT
);

-- Work-scoped suppression is a lookup by this key on every proposal, and it
-- spans runs on purpose: a work declined in March must not return in April.
CREATE INDEX IF NOT EXISTS candidate_works_by_dedup_key ON candidate_works(work_dedup_key);
CREATE INDEX IF NOT EXISTS candidate_works_by_run ON candidate_works(discovery_run_id);

CREATE TABLE IF NOT EXISTS candidate_images (
    id                   TEXT PRIMARY KEY,
    candidate_work_id    TEXT NOT NULL REFERENCES candidate_works(id),
    url                  TEXT NOT NULL,
    preview_url          TEXT,
    preview_path         TEXT,
    provider             TEXT NOT NULL,
    source_class         TEXT NOT NULL,
    acquisition_method   TEXT NOT NULL,
    estimated_width      INTEGER,
    estimated_height     INTEGER,
    rights_status        TEXT,
    confidence           REAL NOT NULL,
    quality_score        REAL,
    selection_rationale  TEXT,
    is_selected          INTEGER NOT NULL,
    rejected_at          TEXT
);

CREATE INDEX IF NOT EXISTS candidate_images_by_work ON candidate_images(candidate_work_id);

-- Which instance a work is represented by is a single fact about the work.
CREATE UNIQUE INDEX IF NOT EXISTS candidate_images_one_selected
    ON candidate_images(candidate_work_id) WHERE is_selected = 1;

-- One intent-forming session. Upstream of a run and never one: nothing here
-- acquires, and a conversation ends by seeding a run or by ending.
CREATE TABLE IF NOT EXISTS conversations (
    id             TEXT PRIMARY KEY,
    started_at     TEXT NOT NULL,
    last_turn_at   TEXT NOT NULL,
    summary        TEXT
);

-- The list is ordered by the last thing said, not by when the thread began.
CREATE INDEX IF NOT EXISTS conversations_by_last_turn ON conversations(last_turn_at);

CREATE TABLE IF NOT EXISTS conversation_turns (
    id               TEXT PRIMARY KEY,
    conversation_id  TEXT NOT NULL REFERENCES conversations(id),
    -- Order within the thread, and not a timestamp: a question and the answer
    -- written in the same request share a second, so time cannot order them.
    ordinal          INTEGER NOT NULL,
    role             TEXT NOT NULL,
    text             TEXT NOT NULL,
    -- `[{kind, value, samples}]` as JSON text. A record of what was said rather
    -- than a live index, which is why the sample pictures are frozen into it.
    suggested        TEXT,
    -- The seam, and the only edge from this side of the product to a run.
    committed_run_id TEXT REFERENCES discovery_runs(id),
    created_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS conversation_turns_by_conversation ON conversation_turns(conversation_id);

-- A partial-free unique index rather than a table constraint, because
-- `CREATE UNIQUE INDEX IF NOT EXISTS` reaches a file written before it and a
-- column clause does not. Two turns claiming one position is a thread that
-- reads differently depending on the tie-break, so the file refuses it.
CREATE UNIQUE INDEX IF NOT EXISTS conversation_turns_one_per_ordinal
    ON conversation_turns(conversation_id, ordinal);

-- What the curator has reacted to, and how. Retained across conversations, and
-- the thing a new conversation opens knowing.
CREATE TABLE IF NOT EXISTS affinities (
    id             TEXT PRIMARY KEY,
    kind           TEXT NOT NULL,
    -- The thing itself as it was named, and a string rather than a foreign key.
    -- The artists a conversation surfaces are the ones the curator could not
    -- have named, so the common case at the moment a judgment is written is a
    -- name with no row in this catalogue at all.
    value          TEXT NOT NULL,
    sentiment      TEXT NOT NULL,
    -- Independent of `sentiment`, because one scalar is a bug: "meh on Magritte,
    -- but open to learning more" is two facts, and collapsing them silently
    -- blacklists an artist the curator asked to keep hearing about.
    open_to_more   INTEGER NOT NULL,
    derivation     TEXT NOT NULL,
    -- Required by the write path for `inferred` and `observed`, and NOT NULL
    -- here would say the same thing wrongly: it is a rule about which
    -- derivations need evidence, not about the column.
    rationale      TEXT,
    -- **Nullable, with no ON DELETE clause, and neither is an oversight.** The
    -- delete nulls this column: a NOT NULL would forbid the delete outright and
    -- a cascade would destroy the judgment the delete is required to leave
    -- standing. The rule that an `inferred` row cites a turn is enforced on the
    -- write path, in `services/taste.py`, and cannot be enforced here without
    -- making the deletion ruling unimplementable.
    source_turn_id TEXT REFERENCES conversation_turns(id),
    artist_id      TEXT REFERENCES artists(id),
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL
);

-- One live judgment per thing, corrected in place. An index rather than a table
-- constraint for the reason the turn ordinal's is: `CREATE UNIQUE INDEX IF NOT
-- EXISTS` reaches a file written before it and a column clause does not.
CREATE UNIQUE INDEX IF NOT EXISTS affinities_one_per_thing ON affinities(kind, value);

-- The read behind detaching a deleted conversation, and behind the provenance
-- link a curator follows from a judgment back to the turn that produced it.
CREATE INDEX IF NOT EXISTS affinities_by_turn ON affinities(source_turn_id);

CREATE TABLE IF NOT EXISTS spend_records (
    id                TEXT PRIMARY KEY,
    discovery_run_id  TEXT REFERENCES discovery_runs(id),
    artwork_id        TEXT REFERENCES artworks(id),
    -- Nulled, never cascaded, when a conversation is deleted: the money was
    -- spent whatever became of the thread. No `ON DELETE` clause here for that
    -- reason — the nulling is an act somebody takes, not a consequence the file
    -- applies behind them.
    conversation_turn_id TEXT REFERENCES conversation_turns(id),
    category          TEXT NOT NULL,
    model_id          TEXT,
    input_tokens      INTEGER,
    output_tokens     INTEGER,
    units             INTEGER,
    -- Decimal text rather than a REAL. This column is money, and SQLite's only
    -- numeric types are integers and IEEE doubles.
    cost_usd          TEXT NOT NULL,
    occurred_at       TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS spend_records_by_time ON spend_records(occurred_at);
CREATE INDEX IF NOT EXISTS spend_records_by_run ON spend_records(discovery_run_id);
-- The read behind detaching a deleted conversation's ledger entries. Without it
-- the delete is a table scan per turn, on the one operation that must not be
-- tempted into cascading for want of a cheap way to find the rows.
CREATE INDEX IF NOT EXISTS spend_records_by_turn ON spend_records(conversation_turn_id);

-- Which works a resolve run covers. Rows are never deleted: coverage records a
-- fact about the run's scope, which does not change when the run's status does,
-- and the history of earlier resolve attempts is worth keeping.
CREATE TABLE IF NOT EXISTS resolve_run_works (
    resolve_run_id     TEXT NOT NULL REFERENCES discovery_runs(id),
    candidate_work_id  TEXT NOT NULL REFERENCES candidate_works(id),
    PRIMARY KEY (resolve_run_id, candidate_work_id)
);

CREATE INDEX IF NOT EXISTS resolve_run_works_by_work ON resolve_run_works(candidate_work_id);
"""

#: The join's own key. A work appears at most once per resolve run.
_COVERAGE_KEY: Final[tuple[str, ...]] = ("resolve_run_id", "candidate_work_id")

#: Newest first: a run list is a history, and the run someone is asking about is
#: almost always the last one.
_BY_START: Final[tuple[OrderBy, ...]] = (OrderBy("started_at", descending=True), OrderBy("id"))

#: What a curator scans by, then a tie-break that makes the order repeatable.
_BY_TITLE: Final[tuple[OrderBy, ...]] = (OrderBy("proposed_title", ignore_case=True), OrderBy("id"))

#: The chosen instance leads where one exists. Rejected instances keep their place
#: in this order rather than sorting last, so a surface that caps this list decides
#: for itself which rows a curator can still act on — see `services/review.py`.
_BY_SELECTION: Final[tuple[OrderBy, ...]] = (
    OrderBy("is_selected", descending=True),
    OrderBy("confidence", descending=True),
    OrderBy("id"),
)

#: Newest first, because spend is read as a history and as a running total.
_BY_OCCURRENCE: Final[tuple[OrderBy, ...]] = (OrderBy("occurred_at", descending=True), OrderBy("id"))

#: A join with no fields of its own; the key is the only stable order it has.
_BY_COVERAGE: Final[tuple[OrderBy, ...]] = (OrderBy("resolve_run_id"), OrderBy("candidate_work_id"))

#: Newest activity first: the thread a curator is looking for is the one they
#: last said something in, which the day it began says nothing about.
_BY_LAST_TURN: Final[tuple[OrderBy, ...]] = (OrderBy("last_turn_at", descending=True), OrderBy("id"))

#: The thread's own order. Ascending, because a transcript is read downwards.
_BY_ORDINAL: Final[tuple[OrderBy, ...]] = (OrderBy("ordinal"),)

#: Taste reads as a list a curator scans for a name, so it is ordered by the
#: name — grouped by kind first, because the screen groups by kind and an order
#: the screen has to re-impose is an order that can disagree with it.
_BY_THING: Final[tuple[OrderBy, ...]] = (OrderBy("kind"), OrderBy("value", ignore_case=True), OrderBy("id"))


class SqliteDiscovery(TableAdapter):
    """The pre-acceptance pipeline, persisted alongside the catalogue."""

    # -- runs -----------------------------------------------------------------

    def add_run(self, run: DiscoveryRun) -> None:
        self._add("discovery_runs", _run_row(run), subject=f"discovery run {run.id!r}")

    def get_run(self, run_id: str) -> DiscoveryRun | None:
        return self._get("discovery_runs", {"id": run_id}, _run)

    def update_run(self, run: DiscoveryRun) -> None:
        self._update("discovery_runs", BY_ID, _run_row(run), subject=f"discovery run {run.id!r}")

    def list_runs(self, *, status: RunStatus | None = None, kind: RunKind | None = None) -> Sequence[DiscoveryRun]:
        filters: dict[str, Any] = {}
        if status is not None:
            filters["status"] = str(status)
        if kind is not None:
            filters["kind"] = str(kind)
        return self._list("discovery_runs", filters or None, _BY_START, _run)

    # -- candidate works ------------------------------------------------------

    def add_candidate_work(self, work: CandidateWork) -> None:
        self._add("candidate_works", _candidate_work_row(work), subject=f"candidate work {work.id!r}")

    def get_candidate_work(self, candidate_work_id: str) -> CandidateWork | None:
        return self._get("candidate_works", {"id": candidate_work_id}, _candidate_work)

    def update_candidate_work(self, work: CandidateWork) -> None:
        self._update("candidate_works", BY_ID, _candidate_work_row(work), subject=f"candidate work {work.id!r}")

    def list_candidate_works(self, run_id: str) -> Sequence[CandidateWork]:
        return self._list("candidate_works", {"discovery_run_id": run_id}, _BY_TITLE, _candidate_work)

    def list_candidate_works_by_dedup_key(self, work_dedup_key: str) -> Sequence[CandidateWork]:
        return self._list("candidate_works", {"work_dedup_key": work_dedup_key}, _BY_TITLE, _candidate_work)

    # -- candidate images -----------------------------------------------------

    def add_candidate_image(self, image: CandidateImage) -> None:
        self._add("candidate_images", _candidate_image_row(image), subject=f"candidate image {image.id!r}")

    def get_candidate_image(self, candidate_image_id: str) -> CandidateImage | None:
        return self._get("candidate_images", {"id": candidate_image_id}, _candidate_image)

    def update_candidate_image(self, image: CandidateImage) -> None:
        self._update("candidate_images", BY_ID, _candidate_image_row(image), subject=f"candidate image {image.id!r}")

    def list_candidate_images(self, candidate_work_id: str) -> Sequence[CandidateImage]:
        return self._list("candidate_images", {"candidate_work_id": candidate_work_id}, _BY_SELECTION, _candidate_image)

    # -- conversations --------------------------------------------------------

    def add_conversation(self, conversation: Conversation) -> None:
        self._add("conversations", _conversation_row(conversation), subject=f"conversation {conversation.id!r}")

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        return self._get("conversations", {"id": conversation_id}, _conversation)

    def update_conversation(self, conversation: Conversation) -> None:
        self._update("conversations", BY_ID, _conversation_row(conversation), subject=f"conversation {conversation.id!r}")

    def list_conversations(self) -> Sequence[Conversation]:
        return self._list("conversations", None, _BY_LAST_TURN, _conversation)

    def add_conversation_turn(self, turn: ConversationTurn) -> None:
        self._add("conversation_turns", _turn_row(turn), subject=f"conversation turn {turn.id!r}")

    def get_conversation_turn(self, turn_id: str) -> ConversationTurn | None:
        return self._get("conversation_turns", {"id": turn_id}, _turn)

    def list_conversation_turns(self, conversation_id: str) -> Sequence[ConversationTurn]:
        return self._list("conversation_turns", {"conversation_id": conversation_id}, _BY_ORDINAL, _turn)

    def delete_conversation_turn(self, turn_id: str) -> None:
        self._delete("conversation_turns", {"id": turn_id})

    def delete_conversation(self, conversation_id: str) -> None:
        self._delete("conversations", {"id": conversation_id})

    # -- affinities -----------------------------------------------------------

    def add_affinity(self, affinity: Affinity) -> None:
        self._add("affinities", _affinity_row(affinity), subject=f"affinity {affinity.kind}/{affinity.value!r}")

    def get_affinity(self, affinity_id: str) -> Affinity | None:
        return self._get("affinities", {"id": affinity_id}, _affinity)

    def find_affinity(self, *, kind: VocabularyKind, value: str) -> Affinity | None:
        """The one live judgment about this thing, by the handle a caller has.

        (`kind`, `value`) rather than an id, because the thing being judged is a
        name in a sentence rather than a row anybody fetched — which is what makes
        the write an upsert.
        """
        found = self._list("affinities", {"kind": str(kind), "value": value}, _BY_THING, _affinity)
        return found[0] if found else None

    def update_affinity(self, affinity: Affinity) -> None:
        self._update("affinities", BY_ID, _affinity_row(affinity), subject=f"affinity {affinity.id!r}")

    def delete_affinity(self, affinity_id: str) -> None:
        self._delete("affinities", {"id": affinity_id})

    def list_affinities(
        self,
        *,
        kind: VocabularyKind | None = None,
        sentiment: AffinitySentiment | None = None,
        derivation: AffinityDerivation | None = None,
        source_turn_id: str | None = None,
    ) -> Sequence[Affinity]:
        """Every matching judgment, grouped by kind and then by name.

        `source_turn_id` is the detach read and is deliberately a filter here
        rather than a method of its own: it is the same question every other
        narrowing asks — which rows carry this value — and a second method would
        be a second place for the order to be decided.
        """
        filters: dict[str, Any] = {}
        if kind is not None:
            filters["kind"] = str(kind)
        if sentiment is not None:
            filters["sentiment"] = str(sentiment)
        if derivation is not None:
            filters["derivation"] = str(derivation)
        if source_turn_id is not None:
            filters["source_turn_id"] = source_turn_id
        return self._list("affinities", filters or None, _BY_THING, _affinity)

    # -- spend ----------------------------------------------------------------

    def add_spend_record(self, record: SpendRecord) -> None:
        self._add("spend_records", _spend_row(record), subject=f"spend record {record.id!r}")

    def update_spend_record(self, record: SpendRecord) -> None:
        """Overwrite a stored cost with this one.

        **The ledger's amounts are never revised**, and this exists for the one
        edit that is not a revision: nulling `conversation_turn_id` when the
        thread it cites is deleted. What was spent does not change; only the
        citation goes.
        """
        self._update("spend_records", BY_ID, _spend_row(record), subject=f"spend record {record.id!r}")

    def list_spend_records(
        self,
        *,
        run_id: str | None = None,
        conversation_turn_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
    ) -> Sequence[SpendRecord]:
        """Return matching costs newest first, `since` inclusive and `until` exclusive.

        The window is applied here rather than in SQL because the durable store's
        contract is equality filters and a deterministic order, deliberately — it
        is the shape a collection layer can sit on. A household's spend table
        holds a few hundred rows a year, so narrowing the read is not worth
        widening that contract; the day it is, this method is where the change
        lands and no caller sees it.
        """
        filters: dict[str, Any] = {}
        if run_id is not None:
            filters["discovery_run_id"] = run_id
        if conversation_turn_id is not None:
            filters["conversation_turn_id"] = conversation_turn_id
        records = self._list("spend_records", filters or None, _BY_OCCURRENCE, _spend)
        return [
            record
            for record in records
            if (since is None or record.occurred_at >= since) and (until is None or record.occurred_at < until)
        ]

    # -- resolve-run coverage -------------------------------------------------

    def add_coverage(self, coverage: ResolveRunWork) -> None:
        self._add(
            "resolve_run_works",
            _coverage_row(coverage),
            subject=f"candidate work {coverage.candidate_work_id!r} on resolve run {coverage.resolve_run_id!r}",
            key=_COVERAGE_KEY,
        )

    def list_coverage_by_run(self, resolve_run_id: str) -> Sequence[ResolveRunWork]:
        return self._list("resolve_run_works", {"resolve_run_id": resolve_run_id}, _BY_COVERAGE, _coverage)

    def list_coverage_by_work(self, candidate_work_id: str) -> Sequence[ResolveRunWork]:
        return self._list("resolve_run_works", {"candidate_work_id": candidate_work_id}, _BY_COVERAGE, _coverage)


# -- record to row ------------------------------------------------------------


def _run_row(run: DiscoveryRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "kind": str(run.kind),
        "parent_run_id": run.parent_run_id,
        "intent_text": run.intent_text,
        "strategy": run.strategy,
        "initiated_by": str(run.initiated_by),
        "status": str(run.status),
        "estimated_cost_usd": to_money(run.estimated_cost_usd),
        "actual_cost_usd": to_money(run.actual_cost_usd),
        "approval_required": int(run.approval_required),
        "unresolved_work_count": run.unresolved_work_count,
        "started_at": to_iso(run.started_at),
        "completed_at": to_iso(run.completed_at),
    }


def _candidate_work_row(work: CandidateWork) -> dict[str, Any]:
    return {
        "id": work.id,
        "discovery_run_id": work.discovery_run_id,
        "artwork_id": work.artwork_id,
        "proposed_title": work.proposed_title,
        "proposed_artist": work.proposed_artist,
        "rationale": work.rationale,
        "work_dedup_key": work.work_dedup_key,
        "provenance": str(work.provenance),
        "offered_for_artist": work.offered_for_artist,
        "offered_artist_matched": work.offered_artist_matched,
        "resolution_status": str(work.resolution_status),
        "unresolved_reason": str(work.unresolved_reason) if work.unresolved_reason else None,
        "verdict": str(work.verdict),
        "rejected_reason": work.rejected_reason,
        "decided_at": to_iso(work.decided_at),
    }


def _candidate_image_row(image: CandidateImage) -> dict[str, Any]:
    return {
        "id": image.id,
        "candidate_work_id": image.candidate_work_id,
        "url": image.url,
        "preview_url": image.preview_url,
        "preview_path": image.preview_path,
        "provider": image.provider,
        "source_class": str(image.source_class),
        "acquisition_method": str(image.acquisition_method),
        "estimated_width": image.estimated_width,
        "estimated_height": image.estimated_height,
        "rights_status": None if image.rights_status is None else str(image.rights_status),
        "confidence": image.confidence,
        "quality_score": image.quality_score,
        "selection_rationale": image.selection_rationale,
        "is_selected": int(image.is_selected),
        "rejected_at": to_iso(image.rejected_at),
    }


def _conversation_row(conversation: Conversation) -> dict[str, Any]:
    return {
        "id": conversation.id,
        "started_at": to_iso(conversation.started_at),
        "last_turn_at": to_iso(conversation.last_turn_at),
        "summary": conversation.summary,
    }


def _turn_row(turn: ConversationTurn) -> dict[str, Any]:
    return {
        "id": turn.id,
        "conversation_id": turn.conversation_id,
        "ordinal": turn.ordinal,
        "role": str(turn.role),
        "text": turn.text,
        # `None` rather than `"null"` for an absent value, so the column's own
        # nullability is what says "this turn offered nothing" — a JSON null in a
        # text column would be a second spelling of the same absence.
        "suggested": None if turn.suggested is None else json.dumps(list(turn.suggested)),
        "committed_run_id": turn.committed_run_id,
        "created_at": to_iso(turn.created_at),
    }


def _spend_row(record: SpendRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "discovery_run_id": record.discovery_run_id,
        "artwork_id": record.artwork_id,
        "conversation_turn_id": record.conversation_turn_id,
        "category": str(record.category),
        "model_id": record.model_id,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "units": record.units,
        "cost_usd": to_money(record.cost_usd),
        "occurred_at": to_iso(record.occurred_at),
    }


def _affinity_row(affinity: Affinity) -> dict[str, Any]:
    return {
        "id": affinity.id,
        "kind": str(affinity.kind),
        "value": affinity.value,
        "sentiment": str(affinity.sentiment),
        "open_to_more": int(affinity.open_to_more),
        "derivation": str(affinity.derivation),
        "rationale": affinity.rationale,
        "source_turn_id": affinity.source_turn_id,
        "artist_id": affinity.artist_id,
        "created_at": to_iso(affinity.created_at),
        "updated_at": to_iso(affinity.updated_at),
    }


def _coverage_row(coverage: ResolveRunWork) -> dict[str, Any]:
    return {"resolve_run_id": coverage.resolve_run_id, "candidate_work_id": coverage.candidate_work_id}


# -- row to record ------------------------------------------------------------


def _run(row: Mapping[str, Any]) -> DiscoveryRun:
    return DiscoveryRun(
        id=row["id"],
        kind=RunKind(row["kind"]),
        initiated_by=InitiatedBy(row["initiated_by"]),
        status=RunStatus(row["status"]),
        approval_required=bool(row["approval_required"]),
        started_at=require_datetime(row["started_at"], "started_at"),
        parent_run_id=row["parent_run_id"],
        intent_text=row["intent_text"],
        strategy=row["strategy"],
        estimated_cost_usd=from_money(row["estimated_cost_usd"]),
        actual_cost_usd=from_money(row["actual_cost_usd"]),
        unresolved_work_count=row["unresolved_work_count"],
        completed_at=from_iso(row["completed_at"]),
    )


def _candidate_work(row: Mapping[str, Any]) -> CandidateWork:
    return CandidateWork(
        id=row["id"],
        discovery_run_id=row["discovery_run_id"],
        proposed_title=row["proposed_title"],
        rationale=row["rationale"],
        work_dedup_key=row["work_dedup_key"],
        # A row written before the column existed is a work phase 1 proposed —
        # nothing else could write one — so the absent value has a single honest
        # reading rather than being a third state.
        provenance=WorkProvenance(row["provenance"]) if row["provenance"] else WorkProvenance.PROPOSED,
        # Absent on every row written before offered works carried their query,
        # and absent for ever on proposed works. `None` is the honest reading in
        # both cases — no query produced them — so no default is invented here.
        offered_for_artist=row["offered_for_artist"],
        offered_artist_matched=row["offered_artist_matched"],
        resolution_status=ResolutionStatus(row["resolution_status"]),
        unresolved_reason=UnresolvedReason(row["unresolved_reason"]) if row["unresolved_reason"] else None,
        verdict=Verdict(row["verdict"]),
        artwork_id=row["artwork_id"],
        proposed_artist=row["proposed_artist"],
        rejected_reason=row["rejected_reason"],
        decided_at=from_iso(row["decided_at"]),
    )


def _candidate_image(row: Mapping[str, Any]) -> CandidateImage:
    return CandidateImage(
        id=row["id"],
        candidate_work_id=row["candidate_work_id"],
        url=row["url"],
        provider=row["provider"],
        source_class=SourceClass(row["source_class"]),
        acquisition_method=AcquisitionMethod(row["acquisition_method"]),
        confidence=row["confidence"],
        is_selected=bool(row["is_selected"]),
        preview_url=row["preview_url"],
        preview_path=row["preview_path"],
        estimated_width=row["estimated_width"],
        estimated_height=row["estimated_height"],
        rights_status=None if row["rights_status"] is None else RightsStatus(row["rights_status"]),
        quality_score=row["quality_score"],
        selection_rationale=row["selection_rationale"],
        rejected_at=from_iso(row["rejected_at"]),
    )


def _spend(row: Mapping[str, Any]) -> SpendRecord:
    return SpendRecord(
        id=row["id"],
        category=SpendCategory(row["category"]),
        cost_usd=require_money(row["cost_usd"], "cost_usd"),
        occurred_at=require_datetime(row["occurred_at"], "occurred_at"),
        discovery_run_id=row["discovery_run_id"],
        artwork_id=row["artwork_id"],
        model_id=row["model_id"],
        input_tokens=row["input_tokens"],
        output_tokens=row["output_tokens"],
        units=row["units"],
        conversation_turn_id=row["conversation_turn_id"],
    )


def _affinity(row: Mapping[str, Any]) -> Affinity:
    return Affinity(
        id=row["id"],
        kind=VocabularyKind(row["kind"]),
        value=row["value"],
        sentiment=AffinitySentiment(row["sentiment"]),
        open_to_more=bool(row["open_to_more"]),
        derivation=AffinityDerivation(row["derivation"]),
        created_at=require_datetime(row["created_at"], "created_at"),
        updated_at=require_datetime(row["updated_at"], "updated_at"),
        rationale=row["rationale"],
        # Null here is a legal state rather than a defect: an `inferred` row whose
        # conversation was deleted keeps its judgment and loses its citation.
        source_turn_id=row["source_turn_id"],
        artist_id=row["artist_id"],
    )


def _conversation(row: Mapping[str, Any]) -> Conversation:
    return Conversation(
        id=row["id"],
        started_at=require_datetime(row["started_at"], "started_at"),
        last_turn_at=require_datetime(row["last_turn_at"], "last_turn_at"),
        summary=row["summary"],
    )


def _turn(row: Mapping[str, Any]) -> ConversationTurn:
    return ConversationTurn(
        id=row["id"],
        conversation_id=row["conversation_id"],
        ordinal=row["ordinal"],
        role=TurnRole(row["role"]),
        text=row["text"],
        created_at=require_datetime(row["created_at"], "created_at"),
        suggested=None if row["suggested"] is None else json.loads(row["suggested"]),
        committed_run_id=row["committed_run_id"],
    )


def _coverage(row: Mapping[str, Any]) -> ResolveRunWork:
    return ResolveRunWork(resolve_run_id=row["resolve_run_id"], candidate_work_id=row["candidate_work_id"])
