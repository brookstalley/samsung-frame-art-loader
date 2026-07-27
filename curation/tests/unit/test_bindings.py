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

from curation.mcp.bindings import _truncation_notice
from curation.services.catalogue import MAX_LIST_LIMIT


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
