"""The review surface driven by a real MCP client over real HTTP.

**This is where the product's one real safety control is checked**, and it can
only be checked here. `security-model.md` § Content Appropriateness makes the
review gate the whole protection for the household — people with no interface who
never opted in and see whatever is on the wall — and states its content exactly:
every surface on which a work can be accepted must display the image first,
including an agent's. What this surface can guarantee is narrower than "a human
looked": it is that the image was *in the transcript*, present at the moment of
judgement. A tool result carrying metadata and no thumbnail defeats the gate while
appearing to honour it, and nothing below the wire can tell the difference — the
payload looks identical. So the assertions here are about `result.content`, the
protocol's own blocks, rather than about anything the service returned.

The other half is the budget. An image costs a client tokens whether or not it is
looked at, and a listing that overflows is truncated by the client rather than by
us — which is the one failure mode that removes the images while leaving the rows.
"""

import json
from io import BytesIO

import pytest
from fakes import FakeImageSearch, a_work, an_image
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from PIL import Image

from curation.config import DEFAULT_RESOLUTION_FLOOR_INCHES
from curation.discovery.engine import WorkList
from curation.persistence.discovery_records import RunStatus
from curation.services.container import Services
from curation.services.previews import PreviewSettings
from curation.services.review import DEFAULT_REVIEW_LIMIT, MAX_INSTANCES_LISTED, MAX_REVIEW_LIMIT

#: The client's two thresholds for a tool result, per `api-contract.md` § Token
#: budget. They are different failures and the surface holds them with different
#: knobs: above the cap the result is truncated — which removes the pictures and
#: leaves the rows, defeating the gate — while the warning merely complains.
HARD_CAP_TOKENS = 25_000
WARN_THRESHOLD_TOKENS = 10_000


#: What an image costs a client, per `api-contract.md` § Token budget. Not a
#: heuristic — it is the published relation, and it is why the page cap is a
#: number of *pictures* rather than a number of rows.
def image_tokens(width: int, height: int) -> float:
    return width * height / 750


#: Rough tokens-per-character for JSON text. A heuristic, named as one: it is
#: used only to show the text is not what would blow the budget, and the margin
#: below is wide enough that a factor-of-two error in it changes nothing.
CHARS_PER_TOKEN = 4


def a_jpeg(width: int = 1200, height: int = 900) -> bytes:
    """Preview bytes a museum could really have served, and that Pillow can open.

    The shipped fake returns a stub that is not decodable, which is right for
    tests about *caching* bytes and wrong for every test here: a preview that
    cannot be decoded produces no image block, so the whole surface would look
    broken for a reason that is the fixture's.
    """
    buffer = BytesIO()
    Image.new("RGB", (width, height), (84, 66, 132)).save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


async def call(server_url: str, tool: str, **arguments):
    """Call a tool and return the whole result, blocks included.

    Deliberately not the `call` helper the other integration modules use. That
    one returns `content[0].text` and the payload, which is exactly the view in
    which a result with no image looks identical to one with forty.
    """
    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            return await session.call_tool(tool, arguments)


def payload_of(result) -> dict:
    return json.loads("".join(block.text for block in result.content if block.type == "text"))


def images_of(result) -> list:
    return [block for block in result.content if block.type == "image"]


async def finished(server_url: str, run_id: str) -> dict:
    for _ in range(8):
        result = await call(server_url, "art_discovery", action="status", run_id=run_id)
        payload = payload_of(result)
        if RunStatus(payload["status"]).is_terminal:
            return payload
    raise AssertionError(f"run {run_id} never finished: {payload}")


@pytest.fixture
def preview_file(settings):
    """Write a decodable preview into the art tree and return its catalogue path."""

    def _write(name: str, *, width: int = 1200, height: int = 900) -> str:
        relative = f"previews/{name}"
        target = settings.art_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(a_jpeg(width, height))
        return relative

    return _write


@pytest.fixture
def museum() -> FakeImageSearch:
    holdings = {
        "The Elephants": (an_image("The Elephants", url="https://artic.edu/elephants", width=6949, height=8400),),
        "Swans Reflecting Elephants": (
            an_image("Swans Reflecting Elephants", url="https://artic.edu/swans", width=900, height=700),
        ),
    }
    found = FakeImageSearch(holdings=holdings)
    found.preview_bytes = a_jpeg()
    return found


@pytest.fixture
def services(store, discovery_store, wall, thumbnail_settings, settings, engine, museum) -> Services:
    """The whole plane, wired the way a deployment with an image provider is."""
    engine.result = WorkList(works=(a_work("The Elephants"), a_work("Swans Reflecting Elephants")))
    return Services.bind(
        catalogue=store,
        discovery=discovery_store,
        wall=wall,
        thumbnails=thumbnail_settings,
        artwork_box=settings.tv_artwork_box,
        engine=engine,
        discovery_settings=settings.discovery_settings,
        image_search=museum,
        previews=PreviewSettings(art_root=settings.art_root, directory=settings.previews_path),
    )


# -- the gate ------------------------------------------------------------------


async def test_a_curator_reaches_the_images_from_nothing_but_the_surface(server_url):
    """The acceptance criterion: run, find the run, read the works, see the pictures.

    Every id is threaded out of the previous response. An action whose argument
    has no reachable source is one a model cannot invoke, and the only way to
    know the chain closes is to walk it without touching a service.
    """
    started = payload_of(await call(server_url, "art_discovery", action="start", intent="Dalí, elephants"))
    await finished(server_url, started["run_id"])

    listed = payload_of(await call(server_url, "art_discovery", action="list_runs"))
    run_id = listed["runs"][0]["run_id"]

    result = await call(server_url, "art_review", action="list_works", run_id=run_id)
    payload = payload_of(result)

    assert payload["success"] is True
    assert {work["title"] for work in payload["works"]} == {"The Elephants", "Swans Reflecting Elephants"}
    # The claim the gate rests on: the pictures are in the transcript.
    assert len(images_of(result)) == 2
    assert all(block.mimeType == "image/jpeg" and block.data for block in images_of(result))


async def test_every_work_a_curator_could_accept_arrives_with_its_picture(server_url):
    """No accept-capable row may be picture-less while a picture exists for it.

    Stated over the rows rather than as a count, because the failure this guards
    is one work in forty silently losing its image — a total that happens to
    match is exactly what that looks like.
    """
    started = payload_of(await call(server_url, "art_discovery", action="start", intent="Dalí, elephants"))
    await finished(server_url, started["run_id"])

    result = await call(server_url, "art_review", action="list_works", run_id=started["run_id"])
    payload = payload_of(result)
    blocks = images_of(result)

    for work in payload["works"]:
        shown = work["shown_image"]
        assert shown is not None, f"{work['title']} arrived with no picture at all"
        index = shown["image_block_index"]
        assert index is not None, f"{work['title']} could be judged with no image shown"
        assert 0 <= index < len(blocks), f"{work['title']} points at a block that is not there"


async def test_a_rows_index_names_its_own_block_when_another_row_has_no_picture(server_url, services, museum):
    """Position in the listing is *not* position in the blocks, and the rows must know it.

    The protocol gives an image block no identity, so a row can only name its
    picture by index — and the blocks carry only the instances that had a local
    copy. A caller pairing row *n* with block *n* is right until one work has no
    preview and wrong for every row after it, which is how the wrong picture gets
    accepted as the right painting.
    """
    started = payload_of(await call(server_url, "art_discovery", action="start", intent="Dalí, elephants"))
    await finished(server_url, started["run_id"])

    # Take the local copy away from whichever work sorts first, leaving the
    # second work's picture at block 0 while its row is second.
    first_title = payload_of(await call(server_url, "art_review", action="list_works", run_id=started["run_id"]))
    leading = first_title["works"][0]
    stripped = services.discovery.list_candidate_images(leading["work_id"])[0]
    (services.review._art_root / stripped.preview_path).unlink()

    result = await call(server_url, "art_review", action="list_works", run_id=started["run_id"])
    works = payload_of(result)["works"]

    assert len(images_of(result)) == 1
    assert works[0]["shown_image"]["image_block_index"] is None
    assert works[0]["shown_image"]["preview_note"] is not None
    # The surviving picture is block 0 even though its row is second.
    assert works[1]["shown_image"]["image_block_index"] == 0


async def test_each_row_points_at_its_own_picture_and_not_another_works(server_url, services, propose, add_image, settings):
    """Every index resolves to *that* work's picture — checked by looking at it.

    The test above pins the *offset* case, and a listing with one block cannot
    tell a correct index from a constant zero. This one gives each work a preview
    of a different shape and decodes the block each row points at, so a row that
    named its neighbour's picture fails. That is the failure with real
    consequences: the payload is entirely plausible, and the curator accepts the
    wrong painting having looked straight at the right-looking image.

    Found by mutation — returning a constant 0 from the index allocator left every
    other assertion in this file green.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    # Aspect ratios that survive the downscale as distinct shapes, so a decoded
    # block identifies its work without carrying any marker of its own.
    shapes = {"Work A": (800, 400), "Work B": (400, 800), "Work C": (600, 600)}
    for title, (width, height) in shapes.items():
        relative = f"previews/{title.replace(' ', '-')}.jpg"
        target = settings.art_root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(a_jpeg(width, height))
        work = propose(title, run_id=run.id, dedup_key=title)
        add_image(work, preview_path=relative, estimated_width=4000, estimated_height=3000)

    result = await call(server_url, "art_review", action="list_works", run_id=run.id)
    works = payload_of(result)["works"]
    blocks = images_of(result)

    assert len(blocks) == len(shapes)
    assert len({work["shown_image"]["image_block_index"] for work in works}) == len(shapes), "indices are not distinct"
    for work in works:
        source_width, source_height = shapes[work["title"]]
        pictured = Image.open(BytesIO(_decoded(blocks[work["shown_image"]["image_block_index"]])))
        # Compared as an aspect ratio rather than exact pixels: the downscale
        # rounds, and what identifies the picture is its shape.
        assert pictured.width / pictured.height == pytest.approx(
            source_width / source_height, rel=0.01
        ), f"{work['title']} points at a block that is not its own picture"


async def test_one_work_in_full_carries_one_picture_and_the_record_behind_it(server_url):
    """`get_work` is the detail view: the whole instance, the rationale, one block.

    The block *count* is the load-bearing half. This view is composed from
    different helpers than the listing, and assigning a picture's index is what
    appends it — so a detail view assembled by widening the listing shape emits
    the same picture twice, charging the caller for both. Nothing else in this
    file would notice: the payload reads correctly and every index is valid.

    Found by mutation; before this test, `get_work` had no assertion over the
    wire at all.
    """
    started = payload_of(await call(server_url, "art_discovery", action="start", intent="Dalí, elephants"))
    await finished(server_url, started["run_id"])
    listed = payload_of(await call(server_url, "art_review", action="list_works", run_id=started["run_id"]))
    chosen = next(work for work in listed["works"] if work["title"] == "The Elephants")

    result = await call(server_url, "art_review", action="get_work", work_id=chosen["work_id"])
    work = payload_of(result)["work"]

    assert len(images_of(result)) == 1, "one instance, one picture"
    assert work["shown_image"]["image_block_index"] == 0
    # The fields a listing row deliberately leaves out.
    assert work["shown_image"]["url"] == "https://artic.edu/elephants"
    assert work["shown_image"]["confidence"] is not None
    assert work["rationale"]
    # The run reaches the caller as a property of the work, and only there.
    assert work["discovery_run_id"] == started["run_id"]


async def test_the_size_a_work_would_render_at_reaches_the_caller(server_url):
    """The number a thumbnail cannot convey, on the wire.

    Two works of very different resolution look the same in a grid. If this were
    absent the gate would still appear to work, and the wall would collect
    postage stamps.
    """
    started = payload_of(await call(server_url, "art_discovery", action="start", intent="Dalí, elephants"))
    await finished(server_url, started["run_id"])

    payload = payload_of(await call(server_url, "art_review", action="list_works", run_id=started["run_id"]))
    by_title = {work["title"]: work for work in payload["works"]}

    big = by_title["The Elephants"]["shown_image"]
    assert big["display_fit"] == "native"
    assert big["is_on_offer"] is True
    # A 6949x8400 scan is portrait, so the box's *height* is what binds and it
    # renders well short of the panel's width — which is the whole reason the
    # figure is computed against this deployment's geometry rather than guessed
    # from a pixel count.
    assert big["renders_at_inches"] > DEFAULT_RESOLUTION_FLOOR_INCHES, "a gallery scan clears the floor"

    # 900x700 is `api-contract.md`'s own worked example of the case the gate
    # exists to catch: shown and labelled, never chosen automatically, and never
    # hidden — so it is pictured in the listing while not being on offer.
    small = by_title["Swans Reflecting Elephants"]["shown_image"]
    assert small["is_on_offer"] is False, "a below-floor instance is not selected for the curator"
    assert small["display_fit"] == "below_floor"
    assert small["renders_at_inches"] == 8.6
    assert small["image_block_index"] is not None, "labelled, but still shown"


# -- the budget ----------------------------------------------------------------


@pytest.fixture
def a_run_of(services, propose, add_image, settings):
    """A run of `count` works, each holding one instance with a real preview.

    Seeded directly rather than driven through discovery: what is measured below
    is the *result*, and forty round trips to a fake museum would measure the
    fixture instead. The run is a real one and the call over HTTP is a real one.
    """

    def _seeded(count: int):
        run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
        source = settings.art_root / "previews/seed.jpg"
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(a_jpeg())
        for index in range(count):
            work = propose(f"Work {index:02d}", run_id=run.id, dedup_key=f"seed-{index}")
            add_image(work, preview_path="previews/seed.jpg", estimated_width=4000, estimated_height=3000)
        return run

    return _seeded


def cost_of(result) -> tuple[float, float]:
    """What this result costs a client: its pictures, and its text.

    The text is taken as it actually goes over the wire — indented, as the
    envelope writes it. Re-serialising the parsed payload measures a smaller
    document than the client is charged for, which is the version of this
    measurement that passes while the real result does not.
    """
    pictures = sum(image_tokens(*Image.open(BytesIO(_decoded(block))).size) for block in images_of(result))
    text = len("".join(block.text for block in result.content if block.type == "text")) / CHARS_PER_TOKEN
    return pictures, text


async def test_a_full_review_listing_stays_inside_the_token_budget(server_url, a_run_of):
    """The ceiling holds against the limit that would actually lose the images.

    Above 25,000 the client truncates, and truncation takes the pictures while
    leaving the rows — the one failure that turns this surface into the metadata
    listing the safety control exists to forbid. Asking for the maximum is a
    caller's decision and it is served; what may never happen is serving it and
    having the images dropped underneath.
    """
    run = a_run_of(MAX_REVIEW_LIMIT)

    result = await call(server_url, "art_review", action="list_works", run_id=run.id, limit=MAX_REVIEW_LIMIT)
    payload = payload_of(result)
    pictures, text = cost_of(result)

    assert len(payload["works"]) == MAX_REVIEW_LIMIT
    assert len(images_of(result)) == MAX_REVIEW_LIMIT
    assert pictures + text < HARD_CAP_TOKENS, f"images {pictures:.0f} + text {text:.0f} tokens"


async def test_a_page_the_caller_did_not_size_does_not_trip_the_clients_warning(server_url, a_run_of):
    """The default is chosen to sit under the *other* threshold.

    A caller who names no limit has not opted into anything, and should not have
    to know a warning threshold exists to avoid it. This is the assertion that
    makes `DEFAULT_REVIEW_LIMIT` a measured number rather than a guess — raise it
    to the ceiling and this fails, which is what happened when it was the ceiling.
    """
    run = a_run_of(MAX_REVIEW_LIMIT)

    result = await call(server_url, "art_review", action="list_works", run_id=run.id)
    payload = payload_of(result)
    pictures, text = cost_of(result)

    assert payload["limit"] == DEFAULT_REVIEW_LIMIT
    assert payload["truncated"] is True, "the run is larger than a default page, so this measures a full one"
    assert pictures + text < WARN_THRESHOLD_TOKENS, f"images {pictures:.0f} + text {text:.0f} tokens"


async def test_a_truncated_page_says_so_and_names_a_remedy_that_exists(server_url, services, propose, add_image):
    """Truncation is always explicit — and here, unlike a run's status view, escapable.

    A run's status caps its work list and can only report the omission, because
    it takes no offset. This listing does, so the notice names paging rather than
    leaving a caller holding a short list with nowhere to go.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    for index in range(4):
        add_image(propose(f"Work {index}", run_id=run.id, dedup_key=f"page-{index}"))

    payload = payload_of(await call(server_url, "art_review", action="list_works", run_id=run.id, limit=2))

    assert payload["truncated"] is True
    assert payload["count"] == 2
    assert payload["total"] == 4
    assert "Showing 1-2 of 4" in payload["notice"]
    assert "raise limit" in payload["notice"], "below the ceiling, a bigger page is still available"
    assert "offset" in payload["notice"]


async def test_at_the_ceiling_the_notice_stops_advising_a_bigger_page(server_url, a_run_of):
    """Advice a caller cannot follow is worse than none.

    Below the cap, "raise limit" is the cheapest remedy and the notice says so.
    At the cap it is a refusal waiting to happen — the very next thing that
    caller does is ask for 41 and get the bounds error. So the notice drops it
    and names the one that still works.
    """
    run = a_run_of(MAX_REVIEW_LIMIT + 5)

    payload = payload_of(await call(server_url, "art_review", action="list_works", run_id=run.id, limit=MAX_REVIEW_LIMIT))

    assert payload["truncated"] is True
    assert "raise limit" not in payload["notice"]
    assert "the maximum" in payload["notice"]
    assert "offset" in payload["notice"]


async def test_a_result_with_no_pictures_at_all_says_so_rather_than_going_quiet(server_url, services, propose, add_image):
    """Silence about the images is the one thing this surface may never do.

    A listing whose rows carry no picture is indistinguishable, to a model, from
    one whose pictures the client dropped — and the second is the failure the
    whole gate is built against. So the notice states the absence and the rows
    each say why, rather than the result simply arriving with no blocks and no
    comment.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    for index in range(2):
        add_image(propose(f"Work {index}", run_id=run.id, dedup_key=f"bare-{index}"), preview_path=None)

    result = await call(server_url, "art_review", action="list_works", run_id=run.id)
    payload = payload_of(result)

    assert images_of(result) == []
    assert "No images accompany this result" in payload["notice"]
    for work in payload["works"]:
        assert work["shown_image"]["image_block_index"] is None
        assert work["shown_image"]["preview_note"]


async def test_the_alternates_arrive_in_full_each_with_its_own_picture(server_url, services, propose, add_image, preview_file):
    """`list_images` executed end to end — the action that shows what else was found.

    The chunk's own criterion is that every result a curator could judge from
    carries the image block, and this is the result they judge *alternates* from.
    It also carries the fields a listing row deliberately drops, which is the
    whole reason the two shapes differ; asserting them here is what stops the
    narrow shape being applied to both.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    work = propose("A work with alternates", run_id=run.id, dedup_key="alts")
    # Distinct aspect ratios, so each block identifies its own row. Identical
    # previews would let a binding emit the blocks in a different order than the
    # rows and still satisfy `image_block_index == [0, 1, 2]` — which is the exact
    # hazard this action carries: the wrong scan of the right painting.
    shapes = [(800, 400), (400, 800), (600, 600)]
    for index, (confidence, (width, height)) in enumerate(zip((0.9, 0.6, 0.3), shapes, strict=True)):
        add_image(
            work,
            url=f"https://museum.example/scan-{index}",
            confidence=confidence,
            preview_path=preview_file(f"scan-{index}.jpg", width=width, height=height),
            estimated_width=4000,
            estimated_height=3000,
        )

    result = await call(server_url, "art_review", action="list_images", work_id=work.id)
    payload = payload_of(result)

    assert payload["count"] == 3
    assert payload["held"] == 3
    assert payload["truncated"] is False
    assert len(images_of(result)) == 3, "every alternate is shown, not just the one on offer"

    # Best first, and only the best is on offer.
    assert [image["url"] for image in payload["images"]] == [
        "https://museum.example/scan-0",
        "https://museum.example/scan-1",
        "https://museum.example/scan-2",
    ]
    assert [image["is_on_offer"] for image in payload["images"]] == [True, False, False]
    assert [image["image_block_index"] for image in payload["images"]] == [0, 1, 2]

    # And each index resolves to *that* row's picture, checked by looking at it.
    blocks = images_of(result)
    for row, (source_width, source_height) in zip(payload["images"], shapes, strict=True):
        pictured = Image.open(BytesIO(_decoded(blocks[row["image_block_index"]])))
        assert pictured.width / pictured.height == pytest.approx(
            source_width / source_height, rel=0.01
        ), f"{row['url']} points at a block that is not its own picture"

    # The fields the listing shape leaves out, which is why this shape exists.
    leading = payload["images"][0]
    assert leading["image_id"]
    assert leading["provider"] == "artic"
    assert leading["confidence"] == 0.9
    assert leading["rejected_for_this_work"] is False
    assert leading["renders_at_pixels"]
    assert leading["display_fit"] == "native"


async def test_a_card_with_more_scans_than_it_can_carry_says_what_it_dropped(
    server_url, services, propose, add_image, preview_file
):
    """The bound on the one collection 17A adds that nothing else limits.

    A work accumulates instances across every re-search and rejected ones stay,
    so this list grows with exactly the action a dissatisfied curator takes. The
    cut falls on the scans a caller cannot choose, so the notice explains rather
    than offering an offset that does not exist.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    work = propose("A much re-searched work", run_id=run.id, dedup_key="many")
    for index in range(MAX_INSTANCES_LISTED + 4):
        add_image(
            work,
            url=f"https://museum.example/many-{index}",
            # Descending, so the ones dropped are the lowest-ranked.
            confidence=1.0 - index / 100,
            preview_path=preview_file(f"many-{index}.jpg"),
            estimated_width=4000,
            estimated_height=3000,
        )

    result = await call(server_url, "art_review", action="list_images", work_id=work.id)
    payload = payload_of(result)

    assert payload["count"] == MAX_INSTANCES_LISTED
    assert payload["held"] == MAX_INSTANCES_LISTED + 4
    assert payload["truncated"] is True
    assert len(images_of(result)) == MAX_INSTANCES_LISTED, "a card never carries more pictures than rows"
    assert f"Showing {MAX_INSTANCES_LISTED} of {MAX_INSTANCES_LISTED + 4}" in payload["notice"]
    assert f"this work has {MAX_INSTANCES_LISTED + 4} scans you could still choose" in payload["notice"]
    assert f"the card holds the {MAX_INSTANCES_LISTED} best of them" in payload["notice"]
    assert "no paging" in payload["notice"]
    # What was dropped is the tail of the ranking, never the instance on offer.
    assert payload["images"][0]["is_on_offer"] is True

    # **The cap's own arithmetic, measured rather than asserted in prose.** This
    # is the third capped result on the surface and the first whose justification
    # was only a docstring — which is precisely how the page cap went wrong: it
    # was sized from the pictures and the rows came to nearly as much again. A
    # full card is a wide shape (every field, not the listing's subset), so it
    # gets the same treatment as the two page budgets.
    pictures, text = cost_of(result)
    assert pictures + text < WARN_THRESHOLD_TOKENS, f"a full card costs images {pictures:.0f} + text {text:.0f}"


async def test_a_cardful_of_rejections_never_crowds_out_a_scan_still_on_offer(
    server_url, services, propose, add_image, preview_file
):
    """The state that made the cap a defect rather than a bound.

    Rejections gather at the *top* of a confidence ranking: the scan a curator
    turns down is the best one on offer, and turning it down does not make the
    picture worse, while each re-search appends its finds below. So a card that
    sliced the store's order would, past a cardful of rejections, show only scans
    already refused — and the instances still choosable would be exactly the ones
    it omitted, with no second way to reach their ids, since this action is the
    only enumerator of a work's instances anywhere in the product.

    Nothing in the ranking is wrong here; every rejected scan really is the
    highest-confidence one. The bug is treating "worst" and "not choosable" as
    the same question.

    **Two survivors, not one, and that is what makes this test reach the defect.**
    A single survivor is the selected instance, and `is_selected DESC` leads the
    store's order — so it rides at the top of even a naive slice and the card
    looks correct while the rule is unenforced. The first version of this test had
    one survivor, passed against the unfixed code, and defended nothing. The
    instance that falls off is the *unselected* alternate: still choosable, still
    the thing `set_canonical` exists to let a curator pick, and outranked on
    confidence by every scan they already refused.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    work = propose("A much re-searched work", run_id=run.id, dedup_key="rejected-lead")
    rejected = []
    for index in range(MAX_INSTANCES_LISTED):
        rejected.append(
            add_image(
                work,
                url=f"https://museum.example/turned-down-{index}",
                # The best scans, which is why they were the ones offered and
                # turned down. They outrank everything found afterwards.
                confidence=0.99 - index / 1000,
                preview_path=preview_file(f"turned-down-{index}.jpg"),
                estimated_width=4000,
                estimated_height=3000,
            )
        )
    for image in rejected:
        services.discovery.reject_image(image.id)
    survivors = [
        add_image(
            work,
            url=f"https://museum.example/still-on-offer-{index}",
            confidence=0.2 - index / 1000,
            preview_path=preview_file(f"survivor-{index}.jpg"),
            estimated_width=4000,
            estimated_height=3000,
        )
        for index in range(2)
    ]

    result = await call(server_url, "art_review", action="list_images", work_id=work.id)
    payload = payload_of(result)

    assert payload["truncated"] is True
    shown = [image["image_id"] for image in payload["images"]]
    for survivor in survivors:
        assert survivor.id in shown, "a scan the curator can still choose fell off the card"
    assert payload["count"] == MAX_INSTANCES_LISTED
    # The rejected scans are still evidence and still shown — they simply yield
    # their slots to the instances that can still be chosen.
    assert sum(1 for image in payload["images"] if image["rejected_for_this_work"]) == MAX_INSTANCES_LISTED - 2
    assert "all 2 scans still open to you are on this card" in payload["notice"]

    # **The rows are ranked, not grouped, and the notice must not say otherwise.**
    # Filling by preference and ordering by rank are different operations: the
    # selected survivor leads on `is_selected`, the refused scans follow on
    # confidence, and the unselected alternate — the one this whole fix exists to
    # keep reachable — lands last. A notice promising the choosable scans "first"
    # would send a curator to the top of the card, where exactly one of the two
    # is. Asserted by position because that is the thing a sentence can lie about.
    choosable_positions = [index for index, image in enumerate(payload["images"]) if not image["rejected_for_this_work"]]
    assert choosable_positions == [0, MAX_INSTANCES_LISTED - 1], "a choosable scan sits at each end, refused ones between"
    assert "first" not in payload["notice"], "the notice must claim nothing about row order"
    assert "rather than its position" in payload["notice"]


async def test_a_card_that_cannot_hold_every_choosable_scan_says_so_instead(
    server_url, services, propose, add_image, preview_file
):
    """The other truncation case, which the first wording of the notice got wrong.

    Giving choosable scans first claim on the slots does not make them fit. When
    they alone outrun the cap the card really does withhold something actionable,
    and a notice saying "every scan still open to you is on this card" would be
    false — so it says which of the two situations this is rather than asserting
    the reassuring one.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    work = propose("A work with many good scans", run_id=run.id, dedup_key="many-good")
    for index in range(MAX_INSTANCES_LISTED + 3):
        add_image(
            work,
            url=f"https://museum.example/all-good-{index}",
            confidence=0.9 - index / 1000,
            preview_path=preview_file(f"all-good-{index}.jpg"),
            estimated_width=4000,
            estimated_height=3000,
        )

    # **The refused scan that makes this state falsifiable.** Once the choosable
    # scans alone fill the card, no refused scan is on it — the fill loop never
    # runs — so every one is omitted. And a refused scan is typically the
    # *highest*-confidence one there is, because being the best on offer is why it
    # was offered and turned down. A notice claiming the omitted scans rank below
    # the shown ones is false exactly here, and a fixture with no rejections at
    # all cannot tell.
    outranking = add_image(
        work,
        url="https://museum.example/turned-down-but-best",
        confidence=0.99,
        preview_path=preview_file("turned-down-but-best.jpg"),
        estimated_width=4000,
        estimated_height=3000,
    )
    services.discovery.reject_image(outranking.id)

    payload = payload_of(await call(server_url, "art_review", action="list_images", work_id=work.id))

    assert payload["truncated"] is True
    assert all(
        not image["rejected_for_this_work"] for image in payload["images"]
    ), "the choosable scans fill the card, so no refused one is on it"
    assert outranking.id not in [image["image_id"] for image in payload["images"]]
    assert f"{MAX_INSTANCES_LISTED + 3} scans you could still choose" in payload["notice"]
    assert "rank below every scan shown" in payload["notice"], "true of the omitted choosable scans"
    assert (
        "every scan you have already turned down" in payload["notice"]
    ), "the omitted refused scans are named separately, because they do not rank below what is shown"
    assert "still open to you are on this card" not in payload["notice"]


async def test_a_work_whose_every_scan_was_turned_down_is_not_reassured_about_it(
    server_url, services, propose, add_image, preview_file
):
    """The empty case of "every choosable scan is on this card".

    True, and the wrong thing to say: there is nothing left to choose, and the
    curator's next move is not on this surface at all. The notice names the paid
    action that finds more rather than reporting a full card of dead ends as
    completeness.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    work = propose("A work nothing survived for", run_id=run.id, dedup_key="all-refused")
    for index in range(MAX_INSTANCES_LISTED + 2):
        image = add_image(
            work,
            url=f"https://museum.example/all-refused-{index}",
            confidence=0.9 - index / 1000,
            preview_path=preview_file(f"all-refused-{index}.jpg"),
            estimated_width=4000,
            estimated_height=3000,
        )
        services.discovery.reject_image(image.id)

    payload = payload_of(await call(server_url, "art_review", action="list_images", work_id=work.id))

    assert payload["truncated"] is True
    assert all(image["rejected_for_this_work"] for image in payload["images"])
    assert "none of these are still open to you" in payload["notice"]
    assert "resolve_images" in payload["notice"], "the curator is pointed at what actually finds more"
    assert "all 0 scans" not in payload["notice"]


async def test_a_work_no_image_was_ever_found_for_says_what_to_do_about_it(server_url, services, propose):
    """An empty instance list is a reportable outcome, not an empty success.

    "We looked and found nothing" is the signal that a proposed work may not
    exist, and it has a remedy the curator can act on. Returning an empty array
    with no comment would read as a surface that failed to load something.
    """
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")
    work = propose("A work with no scans", run_id=run.id, dedup_key="none")

    result = await call(server_url, "art_review", action="list_images", work_id=work.id)
    payload = payload_of(result)

    assert payload["success"] is True
    assert payload["images"] == []
    assert payload["count"] == 0
    assert "No image instances have been found" in payload["notice"]
    assert "resolve_images" in payload["notice"], "the remedy is named, and it is on the tool that owns it"


async def test_a_limit_beyond_the_page_cap_reports_the_bounds(server_url, services):
    run = services.discovery.start_discovery_run(intent_text="Everything", initiated_by="mcp_client")

    result = await call(server_url, "art_review", action="list_works", run_id=run.id, limit=MAX_REVIEW_LIMIT + 1)
    payload = payload_of(result)

    assert payload["success"] is False
    assert payload["parameter_range"] == {"limit": {"minimum": 1, "maximum": MAX_REVIEW_LIMIT}}


# -- the payload does not carry what the blocks do ------------------------------


async def test_no_base64_reaches_the_json_or_the_structured_content(server_url):
    """Image data goes out once, as blocks. Twice more would triple the cost.

    The payload is serialised into the text *and* into `structuredContent`, so a
    picture left in it is paid for twice on top of the block — and it would be
    unreadable in both. This is the invariant that makes the private key safe.
    """
    started = payload_of(await call(server_url, "art_discovery", action="start", intent="Dalí, elephants"))
    await finished(server_url, started["run_id"])

    result = await call(server_url, "art_review", action="list_works", run_id=started["run_id"])
    text = "".join(block.text for block in result.content if block.type == "text")

    assert images_of(result), "the rest of this assertion is vacuous without a block to compare against"
    for block in images_of(result):
        assert block.data not in text
        assert block.data not in json.dumps(result.structuredContent)
    # And the carrier itself never reaches a caller under any name.
    assert "_image_blocks" not in text
    assert "_image_blocks" not in json.dumps(result.structuredContent)


def _decoded(block) -> bytes:
    import base64

    return base64.b64decode(block.data)
