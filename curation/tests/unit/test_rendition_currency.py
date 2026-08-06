"""One rule for "is this render still current", and every surface following it.

The rule decides three things that a curator sees side by side: whether the
review grid badges a render current, which image a thumbnail is made from, and
whether a work reaches the wall or is excluded as `stale_rendition`. It was
written twice — once in `CatalogueService.list_renditions` and once inline in
the manifest builder — so a change to what "current" means would have landed in
one and not the other, and the grid would have shown a green badge on a work the
wall silently dropped. That is the silent shortfall the exclusion report exists
to break, arriving by the one path that did not consult the shared rule.

So these tests do not assert the rule's *content*. They assert that the two
surfaces cannot disagree about it, across every state a work can be in, and that
where both must pick one of several renders they pick the same one.
"""

import pytest

from curation.manifest.builder import ExclusionReason, assess, tv_rendition_of
from curation.persistence.records import FetchStatus, RenditionKind, is_current, tv_renditions_newest_first


def _grid_says_current(service, artwork_id) -> bool:
    """What the review grid would badge: the newest TV render's own verdict."""
    views = {view.rendition.id: view for view in service.list_renditions(artwork_id)}
    chosen = tv_rendition_of([view.rendition for view in views.values()])
    return chosen is not None and not views[chosen.id].stale


def _wall_says_current(display, artwork_id) -> bool:
    """What the manifest would decide: no exclusion, or one that is not staleness."""
    excluded = assess(display._gather(artwork_id))
    return excluded is None or excluded.reason is not ExclusionReason.STALE_RENDITION


class TestTheGridAndTheWallCannotDisagree:
    """The matrix, driven through both real surfaces rather than through the rule."""

    def test_a_freshly_rendered_work_is_current_to_both(self, service, display, ready_work):
        work = ready_work()

        assert _grid_says_current(service, work.id) is True
        assert _wall_says_current(display, work.id) is True

    def test_a_work_re_acquired_since_its_render_is_stale_to_both(self, service, display, ready_work):
        """The case the rule exists for: the render describes an image no longer held."""
        work = ready_work()
        source = service.list_sources(work.id)[0]
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=f"raw/{work.id}.tif",
            width=6000,
            height=4000,
            byte_size=90_000_000,
            content_hash="a-later-acquisition",
            fetch_status=FetchStatus.OK,
        )

        assert _grid_says_current(service, work.id) is False
        assert _wall_says_current(display, work.id) is False

    def test_a_work_with_no_render_at_all_is_current_to_neither(self, service, display, ready_work):
        """The neighbouring exclusion, kept apart from staleness on both surfaces.

        `no_rendition` and `stale_rendition` are acted on differently — render
        it, versus render it again — so a surface that collapsed them would send
        a curator after the wrong thing.
        """
        work = ready_work(rendition=False)

        assert _grid_says_current(service, work.id) is False
        assert assess(display._gather(work.id)).reason is ExclusionReason.NO_RENDITION


class TestBothTieBreaksPickTheSameRender:
    """Two television renders at different geometries, and one right answer.

    The unique index is on `(artwork_id, kind, target_width, target_height)`, so
    a work can hold more than one television render. The manifest took the most
    recently generated; the thumbnail service took the first current one the
    store happened to return. On a work with two, they would have shown
    different pictures with nothing on screen saying which was right.
    """

    @pytest.fixture
    def two_renders(self, service, settings, decodable_jpeg, ready_work):
        """A work whose newest render is deliberately *not* the store's first.

        The narrow geometry is recorded first and the wide one second, because
        the store returns renditions ordered by `(kind, target_width,
        target_height, id)` while the wall wants the most recently generated.
        Recorded the other way round the two orders coincide, the old and new
        code pick the same file, and the test below passes while proving
        nothing — which is what the first draft of it did.

        The fixture asserts the divergence rather than assuming it, so a change
        to the store's `ORDER BY` makes this fail loudly instead of quietly
        going vacuous.
        """
        work = ready_work()
        for width, height in ((1920, 1080), (3840, 2160)):
            relative = f"ready/{work.id}-{width}x{height}.jpg"
            decodable_jpeg(settings.art_root / relative, width=width, height=height)
            service.record_rendition(
                artwork_id=work.id,
                kind=RenditionKind.TV_DISPLAY,
                target_width=width,
                target_height=height,
                path=relative,
            )

        in_store_order = [view.rendition for view in service.list_renditions(work.id)]
        newest_first = tv_renditions_newest_first(in_store_order)
        assert newest_first[0].id != in_store_order[0].id, "this fixture no longer sets up the disagreement it exists to expose"
        return work

    def test_the_wall_and_a_thumbnail_choose_the_same_file(self, two_renders, service, display, thumbnails, settings):
        work = two_renders

        entry_path = display.build_manifest(self._theme_holding(display, work.id)).entries[0].render_path
        thumbnail_source = thumbnails.source_for(work.id)

        assert thumbnail_source.kind == RenditionKind.TV_DISPLAY.value
        assert (
            thumbnail_source.path == settings.art_root / entry_path
        ), "the wall and the review card picked different renders of the same work"

    def test_the_order_is_total_so_two_renders_of_one_instant_cannot_reshuffle(self, two_renders, service):
        """Ties break on id, so the answer does not depend on store iteration order."""
        work = two_renders
        renditions = [view.rendition for view in service.list_renditions(work.id)]

        forwards = tv_renditions_newest_first(renditions)
        backwards = tv_renditions_newest_first(list(reversed(renditions)))

        assert [rendition.id for rendition in forwards] == [rendition.id for rendition in backwards]

    @staticmethod
    def _theme_holding(display, artwork_id) -> str:
        theme = display.add_theme(name="Under test")
        display.add_to_theme(theme_id=theme.id, artwork_id=artwork_id)
        return theme.id


class TestTheRuleItself:
    """The predicate's own contract, so its callers are testing agreement and not it."""

    def test_a_render_made_from_the_held_image_is_current(self, service, ready_work):
        work = ready_work()
        rendition = service.list_renditions(work.id)[0].rendition

        assert is_current(rendition, service.get_original(work.id)) is True

    def test_a_render_with_no_original_at_all_is_not_current(self, service, ready_work):
        work = ready_work()
        rendition = service.list_renditions(work.id)[0].rendition

        assert is_current(rendition, None) is False

    def test_a_stale_render_is_still_returned_by_the_ordering(self, service, ready_work):
        """Currency is not filtered here, and that is load-bearing.

        `assess` needs a stale render in hand to say "needs regenerating"
        (`stale_rendition`) rather than "never rendered" (`no_rendition`) — two
        exclusions a curator acts on differently. An ordering that dropped stale
        rows would tell them to render a work that has been rendered.
        """
        work = ready_work()
        source = service.list_sources(work.id)[0]
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=f"raw/{work.id}.tif",
            width=6000,
            height=4000,
            byte_size=90_000_000,
            content_hash="a-later-acquisition",
            fetch_status=FetchStatus.OK,
        )
        renditions = [view.rendition for view in service.list_renditions(work.id)]

        assert tv_renditions_newest_first(renditions) != []
        assert tv_rendition_of(renditions) is not None
