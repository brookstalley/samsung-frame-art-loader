"""The pipeline's half of the file: its schema, its round trip, its own indexes.

The service tests above cover the rules. These cover the file, because a rule
enforced perfectly against records that do not survive being written and read
back is a rule about nothing. The schema is asserted column by column for the
same reason the catalogue's is: a mapping change shows up one column at a time,
and the backup path restores whatever the file actually holds.
"""

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from curation.persistence.catalogue import StorageError
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
    Verdict,
)
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import AcquisitionMethod, RightsStatus, SourceClass
from curation.persistence.sqlite_discovery import SqliteDiscovery

_EXPECTED_SCHEMA = {
    "discovery_runs": {
        "id",
        "kind",
        "parent_run_id",
        "intent_text",
        "strategy",
        "initiated_by",
        "status",
        "estimated_cost_usd",
        "actual_cost_usd",
        "approval_required",
        "unresolved_work_count",
        "started_at",
        "completed_at",
    },
    "candidate_works": {
        "id",
        "discovery_run_id",
        "artwork_id",
        "proposed_title",
        "proposed_artist",
        "rationale",
        "work_dedup_key",
        "resolution_status",
        "unresolved_reason",
        "verdict",
        "rejected_reason",
        "decided_at",
    },
    "candidate_images": {
        "id",
        "candidate_work_id",
        "url",
        "preview_url",
        "preview_path",
        "provider",
        "source_class",
        "acquisition_method",
        "estimated_width",
        "estimated_height",
        "rights_status",
        "confidence",
        "quality_score",
        "selection_rationale",
        "is_selected",
        "rejected_at",
    },
    "spend_records": {
        "id",
        "discovery_run_id",
        "artwork_id",
        "category",
        "model_id",
        "input_tokens",
        "output_tokens",
        "units",
        "cost_usd",
        "occurred_at",
    },
    "resolve_run_works": {"resolve_run_id", "candidate_work_id"},
}

_STARTED = datetime(2026, 7, 27, 9, 30, tzinfo=UTC)
_FINISHED = datetime(2026, 7, 27, 9, 44, 12, tzinfo=UTC)


def _run(**fields) -> DiscoveryRun:
    return DiscoveryRun(
        id=fields.pop("id", "r1"),
        kind=fields.pop("kind", RunKind.DISCOVERY),
        initiated_by=fields.pop("initiated_by", InitiatedBy.MCP_CLIENT),
        status=fields.pop("status", RunStatus.RESOLVING_WORKS),
        approval_required=fields.pop("approval_required", False),
        started_at=fields.pop("started_at", _STARTED),
        **fields,
    )


def _work(**fields) -> CandidateWork:
    return CandidateWork(
        id=fields.pop("id", "c1"),
        discovery_run_id=fields.pop("discovery_run_id", "r1"),
        proposed_title=fields.pop("proposed_title", "The Persistence of Memory"),
        rationale=fields.pop("rationale", "The best-known Surrealist painting."),
        work_dedup_key=fields.pop("work_dedup_key", "dali::persistence-of-memory"),
        **fields,
    )


def _image(**fields) -> CandidateImage:
    return CandidateImage(
        id=fields.pop("id", "i1"),
        candidate_work_id=fields.pop("candidate_work_id", "c1"),
        url=fields.pop("url", "https://moma.example/79018"),
        provider=fields.pop("provider", "moma"),
        source_class=fields.pop("source_class", SourceClass.INSTITUTIONAL),
        acquisition_method=fields.pop("acquisition_method", AcquisitionMethod.DEZOOMIFY),
        confidence=fields.pop("confidence", 0.97),
        **fields,
    )


def test_the_file_carries_the_schema_the_backup_path_expects(tmp_path):
    path = tmp_path / "catalogue.sqlite"
    open_catalogue_file(path).close()

    connection = sqlite3.connect(path)
    try:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        assert _EXPECTED_SCHEMA.keys() <= tables
        for table, columns in _EXPECTED_SCHEMA.items():
            assert {row[1] for row in connection.execute(f"PRAGMA table_info({table})")} == columns
    finally:
        connection.close()


def test_the_pipeline_survives_the_process_that_wrote_it(tmp_path):
    """Every field, because a mapping change shows up one column at a time."""
    path = tmp_path / "catalogue.sqlite"
    first = open_catalogue_file(path)
    writer = SqliteDiscovery(first)
    writer.add_run(
        _run(
            strategy="Enumerate the artist's best-known works, then verify each.",
            intent_text="Surrealist paintings",
            estimated_cost_usd=Decimal("0.42"),
            actual_cost_usd=Decimal("0.3175"),
            unresolved_work_count=2,
            approval_required=True,
            status=RunStatus.COMPLETED,
            completed_at=_FINISHED,
        )
    )
    writer.add_run(_run(id="r2", kind=RunKind.RESOLVE, parent_run_id="r1", status=RunStatus.RESOLVING_IMAGES))
    writer.add_candidate_work(
        _work(
            proposed_artist="Salvador Dalí",
            resolution_status=ResolutionStatus.RESOLVED,
            verdict=Verdict.REJECTED,
            rejected_reason="Too well known.",
            decided_at=_FINISHED,
        )
    )
    writer.add_candidate_image(
        _image(
            preview_url="https://moma.example/79018/thumb.jpg",
            preview_path="api-cache/previews/79018.jpg",
            estimated_width=6000,
            estimated_height=4000,
            rights_status=RightsStatus.IN_COPYRIGHT,
            quality_score=0.81,
            selection_rationale="The museum's own plate.",
            is_selected=True,
            rejected_at=_FINISHED,
        )
    )
    writer.add_spend_record(
        SpendRecord(
            id="s1",
            category=SpendCategory.WEB_SEARCH,
            cost_usd=Decimal("0.0625"),
            occurred_at=_STARTED,
            discovery_run_id="r1",
            model_id="anthropic/claude-sonnet-4.5",
            input_tokens=1200,
            output_tokens=340,
            units=5,
        )
    )
    writer.add_coverage(ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1"))
    first.close()

    reopened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(reopened)

        run = store.get_run("r1")
        assert (run.kind, run.initiated_by, run.status) == (RunKind.DISCOVERY, InitiatedBy.MCP_CLIENT, RunStatus.COMPLETED)
        assert (run.intent_text, run.strategy) == (
            "Surrealist paintings",
            "Enumerate the artist's best-known works, then verify each.",
        )
        assert (run.estimated_cost_usd, run.actual_cost_usd) == (Decimal("0.42"), Decimal("0.3175"))
        assert (run.approval_required, run.unresolved_work_count) == (True, 2)
        assert (run.started_at, run.completed_at) == (_STARTED, _FINISHED)
        assert run.parent_run_id is None
        assert store.get_run("r2").parent_run_id == "r1"

        work = store.get_candidate_work("c1")
        assert (work.discovery_run_id, work.proposed_title, work.proposed_artist) == (
            "r1",
            "The Persistence of Memory",
            "Salvador Dalí",
        )
        assert (work.rationale, work.work_dedup_key) == ("The best-known Surrealist painting.", "dali::persistence-of-memory")
        assert (work.resolution_status, work.verdict) == (ResolutionStatus.RESOLVED, Verdict.REJECTED)
        assert (work.rejected_reason, work.decided_at, work.artwork_id) == ("Too well known.", _FINISHED, None)

        image = store.list_candidate_images("c1")[0]
        assert (image.url, image.provider, image.source_class) == (
            "https://moma.example/79018",
            "moma",
            SourceClass.INSTITUTIONAL,
        )
        assert image.acquisition_method is AcquisitionMethod.DEZOOMIFY
        assert (image.preview_url, image.preview_path) == ("https://moma.example/79018/thumb.jpg", "api-cache/previews/79018.jpg")
        assert (image.estimated_width, image.estimated_height) == (6000, 4000)
        assert (image.rights_status, image.confidence, image.quality_score) == (RightsStatus.IN_COPYRIGHT, 0.97, 0.81)
        assert (image.selection_rationale, image.is_selected, image.rejected_at) == ("The museum's own plate.", True, _FINISHED)

        spend = store.list_spend_records(run_id="r1")[0]
        assert (spend.category, spend.cost_usd, spend.occurred_at) == (SpendCategory.WEB_SEARCH, Decimal("0.0625"), _STARTED)
        assert (spend.model_id, spend.input_tokens, spend.output_tokens, spend.units) == (
            "anthropic/claude-sonnet-4.5",
            1200,
            340,
            5,
        )
        assert spend.artwork_id is None

        assert store.list_coverage_by_run("r2") == [ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1")]
        assert store.list_coverage_by_work("c1") == [ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1")]
    finally:
        reopened.close()


def test_a_cost_is_stored_as_a_decimal_rather_than_a_float(tmp_path):
    """A binary float cannot hold 0.07 exactly, and money read back wrong is worse
    than money not stored at all — nothing would ever report the drift."""
    path = tmp_path / "catalogue.sqlite"
    opened = open_catalogue_file(path)
    try:
        store = SqliteDiscovery(opened)
        store.add_run(_run())
        for index, amount in enumerate(("0.07", "0.07", "0.07")):
            store.add_spend_record(
                SpendRecord(
                    id=f"s{index}",
                    category=SpendCategory.DISCOVERY_TOKENS,
                    cost_usd=Decimal(amount),
                    occurred_at=_STARTED,
                    discovery_run_id="r1",
                )
            )

        total = sum((record.cost_usd for record in store.list_spend_records(run_id="r1")), Decimal(0))

        assert total == Decimal("0.21")
        assert str(total) == "0.21"
    finally:
        opened.close()


def test_the_file_itself_refuses_a_second_selected_instance(discovery_store):
    """The rule is the service layer's; this is what catches a path that forgets it.

    Enforcement in two places would be a defect if the two could disagree. They
    cannot: the index states strictly less than the rule does — at most one,
    where the rule says exactly one while any instance survives.
    """
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())
    discovery_store.add_candidate_image(_image(is_selected=True))

    with pytest.raises(StorageError, match="already stored"):
        discovery_store.add_candidate_image(_image(id="i2", url="https://other.example/1", is_selected=True))


def test_a_work_is_covered_at_most_once_by_one_resolve_run(discovery_store):
    discovery_store.add_run(_run())
    discovery_store.add_run(_run(id="r2", kind=RunKind.RESOLVE, parent_run_id="r1"))
    discovery_store.add_candidate_work(_work())
    discovery_store.add_coverage(ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1"))

    with pytest.raises(StorageError, match="already stored"):
        discovery_store.add_coverage(ResolveRunWork(resolve_run_id="r2", candidate_work_id="c1"))


def test_a_candidate_cannot_belong_to_a_run_that_does_not_exist(discovery_store):
    with pytest.raises(StorageError, match="not stored"):
        discovery_store.add_candidate_work(_work(discovery_run_id="no-such-run"))


def test_instances_read_with_the_chosen_one_first(discovery_store):
    """The store's ranking puts a work's selected instance first.

    A claim about this read, not about what a review card shows: that card is
    capped and keeps refused scans, so its own leading row is whatever ranks
    first among the ones it kept.
    """
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())
    discovery_store.add_candidate_image(_image(id="i1", confidence=0.4, is_selected=True))
    discovery_store.add_candidate_image(_image(id="i2", url="https://other.example/1", confidence=0.9))

    assert [image.id for image in discovery_store.list_candidate_images("c1")] == ["i1", "i2"]


def test_runs_read_newest_first_because_a_run_list_is_a_history(discovery_store):
    discovery_store.add_run(_run(id="older", started_at=_STARTED))
    discovery_store.add_run(_run(id="newer", started_at=_FINISHED))

    assert [run.id for run in discovery_store.list_runs()] == ["newer", "older"]


def test_a_refusal_about_a_candidate_does_not_call_it_a_catalogue_record(discovery_store):
    """The store cannot see which table it refused, so it must not name one.

    A candidate work is precisely *not* in the catalogue — acceptance is what puts
    one there, and that distinction is the model's spine. A refusal reading "it is
    already in the catalogue" travels through `ServiceError` to whoever asked and
    tells them the opposite of what the model says.
    """
    discovery_store.add_run(_run())
    discovery_store.add_candidate_work(_work())

    with pytest.raises(StorageError) as refused:
        discovery_store.add_candidate_work(_work())

    assert "catalogue" not in str(refused.value)
    assert "candidate work" in str(refused.value)
