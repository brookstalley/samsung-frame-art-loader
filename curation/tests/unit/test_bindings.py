"""The MCP bindings' own behaviour — the formatting a binding is allowed to do.

A binding unpacks arguments, calls one service method, and shapes the result for
a model to read. The shaping is the part worth testing here, because it is the
only part a binding decides, and because a message that gives a caller advice it
cannot act on is a defect the service layer cannot see.

Separate from `test_catalogue_service.py`, which declares itself independent of
any surface: the binding layer is where the thin-binding norm is enforced, and
scattering its tests into a file that disclaims it is how that boundary stops
being legible.
"""

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from curation.mcp.bindings import _run_notice, _truncation_notice
from curation.persistence.discovery_records import CandidateWork, DiscoveryRun, InitiatedBy, ResolutionStatus, RunKind, RunStatus
from curation.services.catalogue import MAX_LIST_LIMIT
from curation.services.runner import RunView


def test_a_complete_page_gets_no_notice(seeded_service):
    """Saying nothing is the honest answer when nothing was left behind."""
    assert _truncation_notice(seeded_service.list_artworks()) is None


def test_a_notice_names_the_limit_that_produced_the_page(seeded_service):
    """ "Raise limit" is advice a caller cannot act on without knowing the current one.

    A caller who passed no limit at all is looking at a default it never chose.
    """
    notice = _truncation_notice(seeded_service.list_artworks(limit=1))

    assert notice == "showing 1-1 of 3 at limit 1; raise limit or page with offset, or narrow with status to see the rest"


def test_at_the_ceiling_the_notice_stops_recommending_a_limit_that_cannot_rise(service):
    """`MAX_LIST_LIMIT` is enforced in the service and declared in the tool schema.

    So a caller already at the maximum who follows "raise limit" gets a refusal.
    `offset` is the affordance that works there, and it is on the same action.
    """
    for index in range(MAX_LIST_LIMIT + 1):
        service.add_artwork(title=f"Work {index:03d}")

    at_ceiling = _truncation_notice(service.list_artworks(limit=MAX_LIST_LIMIT))

    assert at_ceiling is not None
    assert "the maximum" in at_ceiling
    assert "raise limit" not in at_ceiling
    assert "page with offset" in at_ceiling


def test_a_notice_says_where_in_the_set_the_page_sits(service):
    """A message that steers a caller to `offset` must change when they use it.

    Reporting only "showing 20 of 84" reads identically at every offset, so the
    one signal a caller needs — that paging moved — is the one it withholds.
    """
    for index in range(10):
        service.add_artwork(title=f"Work {index:03d}")

    first_page = _truncation_notice(service.list_artworks(limit=4))
    second_page = _truncation_notice(service.list_artworks(limit=4, offset=4))

    assert first_page.startswith("showing 1-4 of 10")
    assert second_page.startswith("showing 5-8 of 10")


def test_the_last_page_reached_by_paging_carries_no_notice(service):
    """Truncation is about what the page leaves behind, not about where it starts."""
    for index in range(10):
        service.add_artwork(title=f"Work {index:03d}")

    assert _truncation_notice(service.list_artworks(limit=4, offset=8)) is None


# -- what a run's state means to whoever asked ----------------------------------


def _works(*, resolved: int = 0, unresolved: int = 0, pending: int = 0) -> tuple[CandidateWork, ...]:
    """Works in the three resolution states, which is what a view's tallies count.

    Built rather than asserted as numbers, because the view derives its counts
    from the works themselves — a fixture that supplied both could describe a run
    with three resolved works and an empty list.
    """
    counts = (
        (ResolutionStatus.RESOLVED, resolved),
        (ResolutionStatus.UNRESOLVED, unresolved),
        (ResolutionStatus.PENDING, pending),
    )
    return tuple(
        CandidateWork(
            id=f"w{status}{index}",
            discovery_run_id="r1",
            proposed_title=f"Work {index}",
            rationale="Central to what was asked for.",
            work_dedup_key=f"key-{status}-{index}",
            resolution_status=status,
        )
        for status, count in counts
        for index in range(count)
    )


@pytest.mark.parametrize("status", list(RunStatus))
def test_every_state_a_run_can_be_read_in_carries_guidance(status):
    """A state name says what happened; the notice says what to do about it.

    Parametrised over the enum rather than over a list written here, so a state
    added later arrives already covered instead of silently falling through to
    whatever the default says. That matters most for the states nobody expects
    to meet: an agent reading an unfamiliar one has the notice and nothing else.
    """
    view = RunView(
        run=DiscoveryRun(
            id="r1",
            kind=RunKind.DISCOVERY,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=status,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        ),
        works=_works(resolved=1, unresolved=1),
        searches_used=3,
        search_allowance=14,
        image_resolution_available=True,
    )

    notice = _run_notice(view)

    assert notice.strip(), f"{status} carries no guidance"
    assert notice.endswith("."), f"{status}'s guidance is not a sentence"


@pytest.mark.parametrize(
    ("status", "must_say"),
    [
        (RunStatus.HALTED_BY_BUDGET, "retrying will fail"),
        (RunStatus.INTERRUPTED, "nothing to investigate"),
        (RunStatus.FAILED, "worth investigating"),
    ],
)
def test_the_three_endings_an_agent_must_tell_apart_each_say_what_to_do_next(status, must_say):
    """Stop, run it again, and investigate are three different instructions.

    An agent that reads them as one will either retry a real fault forever or
    escalate a routine deploy restart as a bug. The state alone distinguishes
    them; this is the sentence that says why it matters.
    """
    view = RunView(
        run=DiscoveryRun(
            id="r1",
            kind=RunKind.DISCOVERY,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=status,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
        ),
        works=(),
        searches_used=0,
        search_allowance=10,
        image_resolution_available=True,
    )

    assert must_say in _run_notice(view)


def _resolving(kind: RunKind) -> RunView:
    return RunView(
        run=DiscoveryRun(
            id="r1",
            kind=kind,
            initiated_by=InitiatedBy.MCP_CLIENT,
            status=RunStatus.RESOLVING_IMAGES,
            approval_required=False,
            started_at=datetime(2026, 8, 2, 9, 0, tzinfo=UTC),
            parent_run_id="r0" if kind is RunKind.RESOLVE else None,
        ),
        works=_works(pending=2),
        searches_used=0,
        search_allowance=4,
        image_resolution_available=True,
    )


def test_a_re_search_is_not_told_its_work_list_has_settled():
    """The two run kinds share this state and reached it by different routes.

    A re-search never ran phase 1 — the curator named its works — so the
    sentence written for a discovery run describes a step this run did not
    perform, on the state a client sees for the whole time it is working.
    """
    discovery_notice = _run_notice(_resolving(RunKind.DISCOVERY))
    resolve_notice = _run_notice(_resolving(RunKind.RESOLVE))

    assert "work list" in discovery_notice
    assert "work list" not in resolve_notice
    assert "re-search" in resolve_notice
    assert "2 works it covers" in resolve_notice


def test_a_deployment_with_no_provider_says_so_whichever_kind_of_run_is_asking():
    """The absent capability outranks the run kind: neither can advance, for one reason."""
    for kind in RunKind:
        view = _resolving(kind)
        notice = _run_notice(replace(view, image_resolution_available=False))

        assert "no image provider is configured" in notice
