"""Composing a proposed work the way a curator judging it needs to see it.

The gate this surface implements is the product's only protection for the people
who never opted in and see whatever is on the wall, and its whole content is that
the reviewing surface shows the image. So these tests are mostly about what
travels *beside* the picture — because a thumbnail alone is precisely the failure
mode: a 900-pixel scan and a 6000-pixel one are indistinguishable in a grid and
are not the same thing on a wall.
"""

import pytest
from PIL import Image

from curation.persistence.discovery_records import RunKind
from curation.services.errors import ServiceError
from curation.services.previews import INLINE_MAX_EDGE_PX, inline_preview
from curation.services.review import MAX_REVIEW_LIMIT


@pytest.fixture
def preview(settings):
    """Write a decodable preview into the art tree and return its catalogue path.

    Paths in a record are relative to `ART_ROOT`; the file has to be at the
    absolute location that resolves to, which is the pairing every test here
    depends on and nothing else would catch if it broke.
    """

    def _write(name="a.jpg", *, width=800, height=600, color=(90, 70, 140)):
        relative = f"previews/{name}"
        target = settings.art_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (width, height), color).save(target, format="JPEG", quality=90)
        return relative

    return _write


# -- what a thumbnail cannot convey -------------------------------------------


def test_an_instance_reports_the_size_it_would_render_at_on_this_wall(services, resolved_work, add_image):
    # 900x700 is `api-contract.md`'s own worked example — "would show at 8.6
    # inches" — so this pins the surface against the number the artifact
    # promises a curator, not against whatever the arithmetic happens to give.
    work = resolved_work()
    add_image(work, url="https://museum.example/small", estimated_width=900, estimated_height=700)

    listing = services.review.list_images(work.id)
    small = next(view for view in listing.instances if view.image.url.endswith("/small"))

    assert small.fit is not None
    assert round(small.fit.rendered_long_edge_inches, 1) == 8.6
    assert str(small.fit.fit) == "below_floor"


def test_a_below_floor_instance_is_offered_rather_than_withheld(services, propose, add_image):
    # Shown, labelled, and selectable — never hidden. The curator may take it
    # anyway, and that judgement is the product. What it is excluded from is
    # being chosen *for* them, which is why nothing is on offer here.
    work = propose()
    add_image(work, estimated_width=600, estimated_height=450)

    listing = services.review.list_images(work.id)
    view = services.review.get_work(work.id).view

    assert [str(instance.fit.fit) for instance in listing.instances] == ["below_floor"]
    assert view.shown_is_on_offer is False, "a below-floor instance is never selected automatically"
    # But it is still pictured. A row that carried no image because nothing was
    # auto-selected would hide it one level above where "never hidden" is written.
    assert view.shown is not None
    assert view.instances_held == 1


def test_an_instance_whose_dimensions_were_never_recorded_says_so_rather_than_reporting_a_size(services, propose, add_image):
    # "We do not know how big it is" and "we know it is too small" lead to
    # opposite decisions. A card that reported no size because nothing measured
    # the image must not read like a card whose work is small.
    work = propose()
    add_image(work, estimated_width=None, estimated_height=None)

    only = services.review.list_images(work.id).instances[0]

    assert only.fit is None
    assert only.fit_note is not None
    assert "not the same as knowing it is small" in only.fit_note


# -- the picture itself --------------------------------------------------------


def test_a_cached_preview_travels_with_the_instance_inside_the_size_cap(services, propose, add_image, preview):
    work = propose()
    add_image(work, preview_path=preview(width=2400, height=1800), estimated_width=2400, estimated_height=1800)

    only = services.review.list_images(work.id).instances[0]

    assert only.preview is not None
    assert only.preview_note is None
    assert max(only.preview.width, only.preview.height) == INLINE_MAX_EDGE_PX
    assert only.preview.media_type == "image/jpeg"


def test_an_instance_with_no_cached_copy_is_still_listed_and_says_why(services, propose, add_image):
    work = propose()
    add_image(work, preview_path=None)

    only = services.review.list_images(work.id).instances[0]

    assert only.preview is None
    assert "No local copy" in only.preview_note
    # The instance is real and still carries the address a curator can look at
    # themselves; losing the work over a missing thumbnail is the tail wagging
    # the dog.
    assert only.image.url


def test_a_preview_that_will_not_decode_costs_its_picture_and_nothing_else(services, propose, add_image, settings):
    work = propose()
    corrupt = settings.art_root / "previews/corrupt.jpg"
    corrupt.parent.mkdir(parents=True, exist_ok=True)
    corrupt.write_bytes(b"this is not an image")
    add_image(work, preview_path="previews/corrupt.jpg", estimated_width=3000, estimated_height=2000)

    only = services.review.list_images(work.id).instances[0]

    assert only.preview is None
    assert "could not be read" in only.preview_note
    # Everything a curator judges resolution by survives the unreadable file.
    assert only.fit is not None
    assert str(only.fit.fit) == "native"


def test_a_preview_that_is_not_a_jpeg_is_re_encoded_as_one(services, propose, add_image, settings):
    # Museums serve PNG and the occasional TIFF alongside JPEG. Everything is
    # re-encoded on the way out so a caller's cost per image tracks the picture
    # rather than the institution's choice of format — and so a client never has
    # to handle a media type this surface did not promise.
    work = propose()
    relative = "previews/alpha.png"
    target = settings.art_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGBA", (500, 400), (10, 20, 30, 128)).save(target, format="PNG")
    add_image(work, preview_path=relative)

    only = services.review.list_images(work.id).instances[0]

    assert only.preview is not None
    assert only.preview.media_type == "image/jpeg"


def test_inline_preview_reports_absence_for_a_file_that_is_not_there(tmp_path):
    assert inline_preview(tmp_path / "nothing.jpg") is None


# -- what stands for the work --------------------------------------------------


def test_a_work_with_a_selection_shows_that_instance_and_says_it_is_on_offer(services, propose, add_image, preview):
    work = propose()
    add_image(
        work,
        url="https://museum.example/best",
        preview_path=preview("best.jpg"),
        confidence=0.95,
        estimated_width=4000,
        estimated_height=3000,
    )
    add_image(
        work,
        url="https://museum.example/other",
        preview_path=preview("other.jpg"),
        confidence=0.4,
        estimated_width=4000,
        estimated_height=3000,
    )

    view = services.review.get_work(work.id).view

    assert view.shown.image.url == "https://museum.example/best"
    assert view.shown_is_on_offer is True


def test_a_work_nothing_could_be_selected_for_is_still_pictured(services, propose, add_image, preview):
    # Every instance is below the floor, so none may be chosen automatically —
    # and the work must still arrive with a picture. `api-contract.md` requires a
    # below-floor instance to be shown, labelled and selectable, never hidden;
    # a row that carried no image because nothing was auto-selected would defeat
    # that one level above where the rule is written, and the curator would see a
    # title with no way to know a picture exists at all.
    work = propose()
    for index in range(3):
        add_image(
            work,
            url=f"https://museum.example/{index}",
            preview_path=preview(f"{index}.jpg"),
            confidence=0.5 + index / 10,
            estimated_width=600,
            estimated_height=450,
        )

    view = services.review.get_work(work.id).view

    assert view.instances_held == 3
    assert view.shown is not None, "a work with instances is never shown picture-less"
    assert view.shown_is_on_offer is False
    # The best of the set by the one ranking there is, not whichever sorted
    # first: a second ordering here is how the card and the automatic choice come
    # to disagree about which scan is best.
    assert view.shown.image.url == "https://museum.example/2"


def test_a_work_whose_every_instance_was_rejected_shows_nothing(services, discovery, propose, add_image, preview):
    # The one case where a picture-less row is correct. A rejected scan is
    # excluded from re-selection, so there is genuinely nothing left to offer —
    # and `instances_held` against `instances_surviving` is what tells this apart
    # from a work nothing was ever found for.
    work = propose()
    only = add_image(work, preview_path=preview())
    discovery.reject_image(only.id)

    view = services.review.get_work(work.id).view

    assert view.shown is None
    assert (view.instances_held, view.instances_surviving) == (1, 0)


def test_a_rejected_instance_stays_on_the_card_labelled(services, discovery, propose, add_image):
    work = propose()
    first = add_image(work, url="https://museum.example/first", confidence=0.9)
    add_image(work, url="https://museum.example/second", confidence=0.5)
    discovery.reject_image(first.id)

    listing = services.review.list_images(work.id)
    by_url = {view.image.url: view for view in listing.instances}

    # Kept rather than dropped: it is the evidence of a judgement already made,
    # and a re-search returning fewer instances than before with no explanation
    # is how a curator concludes the surface lost something.
    assert by_url["https://museum.example/first"].rejected is True
    assert by_url["https://museum.example/second"].rejected is False
    assert services.review.get_work(work.id).view.instances_surviving == 1


# -- paging, and the bound on the pictures --------------------------------------


def test_a_page_names_its_place_and_what_it_left_behind(services, run, propose, add_image):
    for index in range(5):
        add_image(propose(f"Work {index}", dedup_key=f"w{index}"))

    page = services.review.list_works(run.id, limit=2, offset=2)

    assert [view.work.proposed_title for view in page.entries] == ["Work 2", "Work 3"]
    assert (page.total, page.limit, page.offset, page.truncated) == (5, 2, 2, True)


def test_the_last_page_is_not_reported_as_truncated(services, run, propose, add_image):
    for index in range(3):
        add_image(propose(f"Work {index}", dedup_key=f"w{index}"))

    page = services.review.list_works(run.id, limit=2, offset=2)

    assert len(page.entries) == 1
    assert page.truncated is False


def test_a_limit_past_the_picture_budget_is_refused_with_the_bound(services, run):
    # The cap exists because every row carries an image, and images dominate the
    # result. Refusing names the number rather than silently clamping, so a
    # caller asking for 200 works learns the surface will not do it.
    with pytest.raises(ServiceError, match=f"between 1 and {MAX_REVIEW_LIMIT}"):
        services.review.list_works(run.id, limit=MAX_REVIEW_LIMIT + 1)


def test_a_negative_offset_is_refused(services, run):
    with pytest.raises(ServiceError, match="offset cannot be negative"):
        services.review.list_works(run.id, offset=-1)


def test_works_with_an_image_lead_the_page(services, run, propose, add_image, discovery):
    # A curator can act on a resolved work and can do nothing about an
    # unresolved one but re-search it, so the judgeable ones come first. The
    # order is a total one, which is what makes a page boundary reproducible.
    found = propose("Alpha", dedup_key="alpha")
    add_image(found)
    discovery.record_resolution(found.id)
    missing = propose("Beta", dedup_key="beta")
    discovery.record_resolution(missing.id)

    titles = [view.work.proposed_title for view in services.review.list_works(run.id).entries]

    assert titles == ["Alpha", "Beta"]
    assert titles == [view.work.proposed_title for view in services.review.list_works(run.id).entries]


def test_an_unknown_run_is_refused_rather_than_answered_with_an_empty_page(services):
    with pytest.raises(ServiceError, match="does-not-exist"):
        services.review.list_works("does-not-exist")


def test_a_resolve_run_lists_the_works_it_covers(services, discovery, propose, add_image, run):
    # A re-search holds its works by coverage rather than by provenance, so a
    # listing that read `discovery_run_id` would report a resolve run as empty —
    # and the curator watching one would see nothing to review.
    work = propose()
    add_image(work)
    discovery.record_resolution(work.id)
    discovery.reject_image(services.review.list_images(work.id).instances[0].image.id)
    resolve = discovery.start_resolve_run(candidate_work_ids=[work.id], initiated_by="mcp_client")

    page = services.review.list_works(resolve.id)

    assert page.run.kind is RunKind.RESOLVE
    assert [view.work.id for view in page.entries] == [work.id]
