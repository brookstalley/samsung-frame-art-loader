"""Stub payloads for the browser suite, built from the API's own response models.

**Never hand-written dicts.** A dict invents a shape, and stops describing the
server the moment a field is added or renamed — leaving these tests green while
the page they drive breaks. Every builder here constructs the real `*Out` model
and dumps it, so a change to a response either reaches the client through these
tests or fails loudly at construction.

A sibling module rather than fixtures on the conftest: these are values, and
threading half a dozen builder fixtures through every signature would say
nothing the import does not.
"""

from curation.http.models import (
    CandidateWorkOut,
    EstimateOut,
    ImageOut,
    RunOut,
    RunTallyOut,
    RunViewOut,
    SearchUsageOut,
    SpendOut,
    WorkOut,
    WorkPageOut,
)
from curation.persistence.discovery_records import (
    InitiatedBy,
    ResolutionStatus,
    RunKind,
    RunStatus,
    Verdict,
    WorkProvenance,
)
from curation.persistence.records import ArtworkStatus


def a_catalogue_work(**overrides) -> WorkOut:
    """A work as the grid receives it, defaulting to one holding no image."""
    fields = {
        "artwork_id": "artwork-1",
        "title": "Nighthawks",
        "artist": None,
        "date_created": "1942",
        "medium": None,
        "dimensions": None,
        "description": None,
        "rights": None,
        "status": ArtworkStatus.ACCEPTED.value,
        "fit": None,
        "fit_note": None,
        "image": ImageOut(available=False, source_kind=None, note="No image held."),
    }
    return WorkOut(**(fields | overrides))


def a_listing(works, *, total=None, truncated=False, offset=0) -> dict:
    """One page of the catalogue, as `/api/works` answers it."""
    works = list(works)
    return WorkPageOut(
        works=works,
        total=len(works) if total is None else total,
        limit=100,
        offset=offset,
        truncated=truncated,
    ).model_dump(mode="json")


def a_run(**overrides) -> RunOut:
    """A run, defaulting to one stopped at the approval gate."""
    fields = {
        "run_id": "run-under-test",
        "kind": RunKind.DISCOVERY.value,
        "status": RunStatus.AWAITING_APPROVAL.value,
        "is_terminal": False,
        "initiated_by": InitiatedBy.WEB_UI.value,
        "intent": "Something by Dalí",
        "strategy": None,
        "approval_required": True,
        "estimated_cost_usd": None,
        "actual_cost_usd": None,
        "unresolved_work_count": None,
        "parent_run_id": None,
        "started_at": "2026-08-05T10:00:00+00:00",
        "completed_at": None,
    }
    return RunOut(**(fields | overrides))


def a_candidate(**overrides) -> CandidateWorkOut:
    """A candidate work, defaulting to one the run asked for and resolved."""
    fields = {
        "work_id": "work-1",
        "title": "The Persistence of Memory",
        "artist": "Salvador Dalí",
        "rationale": "Named in the intent.",
        "provenance": WorkProvenance.PROPOSED.value,
        "verdict": Verdict.PENDING.value,
        "resolution_status": ResolutionStatus.RESOLVED.value,
        "unresolved_reason": None,
    }
    return CandidateWorkOut(**(fields | overrides))


def a_run_view(run: RunOut | None = None, works: list[CandidateWorkOut] | None = None, **overrides) -> dict:
    """The whole `/api/runs/{id}` payload, as JSON the client will receive.

    The tally is computed from the works rather than passed in. The client's run
    sentence reads both, so a fixture free to disagree with itself could assert a
    sentence no server could ever have produced.
    """
    run = run or a_run()
    works = [] if works is None else list(works)
    proposed = [w for w in works if w.provenance == WorkProvenance.PROPOSED.value]
    resolved = [w for w in works if w.resolution_status == ResolutionStatus.RESOLVED.value]
    tally = RunTallyOut(
        total=len(works),
        proposed=len(proposed),
        offered=len(works) - len(proposed),
        resolved=len(resolved),
        resolved_proposals=len([w for w in proposed if w.resolution_status == ResolutionStatus.RESOLVED.value]),
        unresolved=len([w for w in works if w.resolution_status == ResolutionStatus.UNRESOLVED.value]),
        pending=len([w for w in works if w.resolution_status == ResolutionStatus.PENDING.value]),
    )
    view = RunViewOut(
        run=run,
        tally=tally,
        works=works,
        searches=SearchUsageOut(used=1, allowance=10, exhausted=False),
        image_resolution_available=True,
        **overrides,
    )
    return view.model_dump(mode="json")


def an_estimate(**overrides) -> dict:
    fields = {
        "phase": "phase_2",
        "estimated_cost_usd": "0.00",
        "basis": "Phase 2 asks museum APIs, which charge nothing.",
        "run_id": "run-under-test",
    }
    return EstimateOut(**(fields | overrides)).model_dump(mode="json")


def a_spend(**overrides) -> dict:
    fields = {
        "scope": "run_family",
        "cost_usd": "0.0134",
        "run_id": "run-under-test",
        "run_direct_cost_usd": "0.0134",
        "year": None,
        "month": None,
    }
    return SpendOut(**(fields | overrides)).model_dump(mode="json")
