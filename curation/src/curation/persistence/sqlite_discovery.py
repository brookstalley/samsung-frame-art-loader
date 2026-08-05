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
    CandidateImage,
    CandidateWork,
    DiscoveryRun,
    InitiatedBy,
    ResolutionStatus,
    ResolveRunWork,
    RunKind,
    RunStatus,
    SpendCategory,
    SpendRecord,
    UnresolvedReason,
    Verdict,
)
from curation.persistence.durable import OrderBy
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass

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

CREATE TABLE IF NOT EXISTS spend_records (
    id                TEXT PRIMARY KEY,
    discovery_run_id  TEXT REFERENCES discovery_runs(id),
    artwork_id        TEXT REFERENCES artworks(id),
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

    # -- spend ----------------------------------------------------------------

    def add_spend_record(self, record: SpendRecord) -> None:
        self._add("spend_records", _spend_row(record), subject=f"spend record {record.id!r}")

    def list_spend_records(
        self,
        *,
        run_id: str | None = None,
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
        filters = None if run_id is None else {"discovery_run_id": run_id}
        records = self._list("spend_records", filters, _BY_OCCURRENCE, _spend)
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


def _spend_row(record: SpendRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "discovery_run_id": record.discovery_run_id,
        "artwork_id": record.artwork_id,
        "category": str(record.category),
        "model_id": record.model_id,
        "input_tokens": record.input_tokens,
        "output_tokens": record.output_tokens,
        "units": record.units,
        "cost_usd": to_money(record.cost_usd),
        "occurred_at": to_iso(record.occurred_at),
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
    )


def _coverage(row: Mapping[str, Any]) -> ResolveRunWork:
    return ResolveRunWork(resolve_run_id=row["resolve_run_id"], candidate_work_id=row["candidate_work_id"])
