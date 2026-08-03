"""What the curator's decision does, driven over a real MCP client.

The service layer already holds the rules — a verdict is final, only rejecting an
instance reaches `awaiting_better_image`, acceptance mints an artwork and promotes
every scan into a source — and the unit suite pins each of them. What these tests
cover is the half that only exists once the actions are on the surface: that a
caller holding nothing but ids the previous response gave them can reach a
decision, that the decision lands in the catalogue, and that a refusal arrives as
something a model can act on rather than as a fault.

**The explicit-ids rule is a surface property and is checked here.**
`api-contract.md` § set_verdict decides that acceptance names its works, so the
accepted set appears in the transcript where the curator sees it. Nothing below
this layer can enforce that: a service method takes the id it is given, and the
bar is that no action exists which would accept without one.
"""

import json

import pytest
from fakes import FakeImageSearch, a_work, an_image

from curation.discovery.engine import WorkList
from curation.persistence.discovery_records import Verdict
from curation.persistence.records import ArtworkStatus
from curation.services.container import Services
from curation.services.previews import PreviewSettings


async def call(server_url: str, tool: str, **arguments) -> tuple[dict, bool]:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async with streamable_http_client(f"{server_url}/mcp") as (read, write, _):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(tool, arguments)
    return json.loads("".join(block.text for block in result.content if block.type == "text")), bool(result.isError)


@pytest.fixture
def museum() -> FakeImageSearch:
    return FakeImageSearch(
        holdings={"The Elephants": (an_image("The Elephants", url="https://artic.edu/elephants"),)},
    )


@pytest.fixture
def services(store, discovery_store, wall, thumbnail_settings, settings, engine, museum) -> Services:
    engine.result = WorkList(works=(a_work("The Elephants"),))
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


@pytest.fixture
def reviewable(services, propose, add_image):
    """A proposed work with the instances a test names, ready to be judged.

    Seeded rather than discovered: what these tests exercise is the decision, and
    driving a run to produce the work would put a museum and two engines between
    the test and the thing it is about. The contract suite drives the whole route
    for real.
    """

    def _reviewable(*, title="The Elephants", instances=1, artist="Salvador Dalí", previews=False, **fields):
        work = propose(title, dedup_key=title.lower(), proposed_artist=artist, **fields)
        images = [
            add_image(
                work,
                url=f"https://artic.edu/{title.lower().replace(' ', '-')}/{index}",
                confidence=0.9 - index / 10,
                estimated_width=6000,
                estimated_height=4000,
                preview_path=f"previews/{title.lower().replace(' ', '-')}-{index}.jpg" if previews else None,
            )
            for index in range(instances)
        ]
        return work, images

    return _reviewable


# -- acceptance reaches the catalogue -----------------------------------------


async def test_an_accepted_work_arrives_in_the_catalogue_with_its_artist(server_url, services, reviewable):
    """The promotion, end to end through the tool that triggers it.

    `art_catalogue` is asked afterwards rather than the service, because the
    claim is that acceptance produces a *catalogued* work — one the surface a
    curator browses can find — and reading it back through the layer that wrote
    it would prove only that the write happened.
    """
    work, _images = reviewable()

    accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

    assert errored is False
    assert accepted["verdict"] == "accepted"
    assert accepted["artwork_id"] is not None, "the handle the next call needs, not a lookup they have to do"

    found, _errored = await call(server_url, "art_catalogue", action="get", artwork_id=accepted["artwork_id"])
    assert found["artwork"]["title"] == "The Elephants"
    # Q9 — who painted it, for the physical label — answerable for a work that
    # arrived through discovery. Before the artist was resolved at promotion, an
    # accepted candidate carried its painter only as the free text phase 1 wrote.
    assert found["artwork"]["artist"]["name"] == "Salvador Dalí"


async def test_acceptance_promotes_every_scan_into_a_source_with_the_chosen_one_primary(server_url, services, reviewable):
    """Promotion is a mirror, not a filter: the alternates are kept.

    Read through the service for the sources themselves, because no action on
    the catalogue tool returns them — acquisition is their only consumer so far,
    and inventing a reader here would be this chunk widening a different tool's
    contract. What the surface is asked for is the fact it does publish: the
    artwork exists and is the one this candidate became.
    """
    work, images = reviewable(instances=3)

    accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

    assert errored is False
    sources = services.catalogue.list_sources(accepted["artwork_id"])
    assert {source.url for source in sources} == {image.url for image in images}, "every scan, none dropped"
    assert [source.is_primary for source in sources].count(True) == 1
    primary = next(source for source in sources if source.is_primary)
    assert primary.url == images[0].url, "the instance that was on offer"
    assert services.catalogue.get_artwork(accepted["artwork_id"]).artwork.status is ArtworkStatus.ACCEPTED


async def test_a_rejection_records_the_reason_and_mints_nothing(server_url, services, reviewable):
    work, _images = reviewable()

    rejected, errored = await call(
        server_url,
        "art_review",
        action="set_verdict",
        work_id=work.id,
        verdict="rejected",
        reason="Already hanging in the study.",
    )

    assert errored is False
    assert rejected["verdict"] == "rejected"
    assert rejected["artwork_id"] is None
    assert rejected["minted_artist"] is None
    assert services.discovery.get_candidate_work(work.id).rejected_reason == "Already hanging in the study."


async def test_a_second_verdict_on_a_decided_work_is_refused(server_url, reviewable):
    work, _images = reviewable()
    await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="rejected")

    payload, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

    assert errored is True
    assert "final" in payload["error"]


# -- the artist, and the merge that is deliberately not made ------------------


async def test_a_near_miss_on_an_artist_is_reported_rather_than_merged(server_url, services, reviewable):
    """A duplicate row is visible and mergeable; a wrong merge is neither.

    The service decides this and the unit suite pins the rule. What is checked
    here is that the decision *reaches the curator* — it is the one part of a
    promotion they can neither see in the accepted work nor undo from it, so a
    payload that carried it in no field and no sentence would leave the catalogue
    quietly holding one painter twice.
    """
    services.catalogue.add_artist(name="Jacob van Ruisdael")
    work, _images = reviewable(title="The Windmill", artist="Jacob Isaacksz van Ruisdael")

    accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

    assert errored is False
    assert accepted["minted_artist"]["name"] == "Jacob Isaacksz van Ruisdael"
    assert [artist["name"] for artist in accepted["possible_duplicate_artists"]] == ["Jacob van Ruisdael"]
    assert "may be the same painter" in accepted["notice"]


async def test_an_exact_match_reuses_the_artist_and_says_nothing(server_url, services, reviewable):
    # A painter the seeded catalogue does not already hold, so the row this test
    # matches against is the one it created. Reusing a seeded name would pass
    # against a match this test did not set up, and would keep passing if the
    # matching stopped working for names added at runtime.
    held = services.catalogue.add_artist(name="Remedios Varo")
    work, _images = reviewable(title="Creation of the Birds", artist="Remedios Varo")

    accepted, _errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

    assert accepted["minted_artist"] is None
    # Reported as empty rather than omitted: a key a caller sees only sometimes
    # teaches them to read its absence as "nothing happened".
    assert accepted["possible_duplicate_artists"] == []
    assert accepted["notice"] is None
    assert services.catalogue.get_artwork(accepted["artwork_id"]).artist.id == held.id


# -- rejecting a scan ----------------------------------------------------------


async def test_rejecting_a_scan_moves_the_work_and_names_the_paid_call_that_replaces_it(server_url, services, reviewable):
    """`reject_image` does not search, and the payload is where that is said.

    A caller arrives at this action having decided the scan is not good enough,
    and the thing that finds a better one is a different tool that spends money.
    A result that merely confirmed the rejection would leave a model waiting for
    a replacement nothing is looking for.
    """
    work, images = reviewable(instances=2)

    payload, errored = await call(server_url, "art_review", action="reject_image", image_id=images[0].id)

    assert errored is False
    assert payload["verdict"] == "awaiting_better_image"
    assert "resolve_images" in payload["notice"]
    surviving = [image for image in services.discovery.list_candidate_images(work.id) if image.rejected_at is None]
    assert [image.id for image in surviving] == [images[1].id]
    assert next(image for image in surviving if image.is_selected).id == images[1].id, "the selection fell through"


async def test_a_curator_is_never_blocked_on_a_re_search_they_have_not_asked_for(server_url, services, reviewable):
    """Accepting from `awaiting_better_image` is the point of the source/target split.

    `set_verdict` refuses that value as a *target* and permits it as a source
    state, so a curator who turned down the best scan can still take the next
    one — or give up — without waiting for a background job.
    """
    work, images = reviewable(instances=2)
    await call(server_url, "art_review", action="reject_image", image_id=images[0].id)

    accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")

    assert errored is False
    assert accepted["verdict"] == "accepted"
    sources = services.catalogue.list_sources(accepted["artwork_id"])
    primary = next(source for source in sources if source.is_primary)
    assert primary.url == images[1].url, "the scan they did not turn down"


async def test_asking_for_awaiting_better_image_teaches_the_action_that_sets_it(server_url, reviewable):
    work, _images = reviewable()

    payload, errored = await call(
        server_url, "art_review", action="set_verdict", work_id=work.id, verdict="awaiting_better_image"
    )

    assert errored is True
    assert "awaiting_better_image" in payload["error"]
    assert payload["valid_values"] == {"verdict": ["accepted", "rejected"]}
    # The naming is the requirement, not the enumeration. `api-contract.md`
    # § set_verdict cannot set `awaiting_better_image` asks the refusal to point
    # at `reject_image`, and it is the *schema* that refuses here — validation
    # runs before dispatch, so the service's own teaching error never fires
    # through this path. A caller asking for that verdict has not mistyped a
    # value; they want what another action does, and a valid-set enumeration
    # alone would send them away without it.
    assert "reject_image" in payload["error"]


# -- choosing among the scans --------------------------------------------------


async def test_a_curator_can_choose_a_scan_the_floor_withheld(server_url, services, propose, add_image):
    """The decision the resolution floor exists to force.

    Automatic selection declines every instance below the floor, so a work found
    only in small scans arrives with nothing on offer and cannot be accepted.
    Choosing one explicitly is the whole remedy, and it is this action.
    """
    work = propose("The Elephants", dedup_key="elephants")
    small = add_image(work, estimated_width=400, estimated_height=300)
    assert not services.discovery.list_candidate_images(work.id)[0].is_selected

    chosen, errored = await call(
        server_url,
        "art_review",
        action="set_canonical",
        image_id=small.id,
        rationale="Only scan in existence; small but genuine.",
    )

    assert errored is False
    assert chosen["work_id"] == work.id
    # Asked of the record rather than of the payload: what makes this action
    # worth having is that the instance really is on offer afterwards, and a
    # field in the reply saying so could only ever agree with itself.
    assert services.discovery.list_candidate_images(work.id)[0].is_selected
    accepted, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict="accepted")
    assert errored is False, "a work with a scan chosen explicitly can be accepted"
    primary = next(source for source in services.catalogue.list_sources(accepted["artwork_id"]) if source.is_primary)
    assert primary.selection_rationale == "Only scan in existence; small but genuine."


async def test_a_scan_already_turned_down_cannot_be_chosen_again(server_url, reviewable):
    work, images = reviewable(instances=2)
    await call(server_url, "art_review", action="reject_image", image_id=images[0].id)

    payload, errored = await call(server_url, "art_review", action="set_canonical", image_id=images[0].id)

    assert errored is True
    assert "rejected" in payload["error"]


async def test_choosing_an_alternate_moves_the_offer_to_it(server_url, services, reviewable):
    work, images = reviewable(instances=3)

    chosen, errored = await call(server_url, "art_review", action="set_canonical", image_id=images[2].id)

    assert errored is False
    assert chosen["image_id"] == images[2].id
    selected = [image for image in services.discovery.list_candidate_images(work.id) if image.is_selected]
    assert [image.id for image in selected] == [images[2].id], "one instance is on offer, and it is the chosen one"


# -- the explicit-ids rule -----------------------------------------------------


async def test_there_is_no_way_to_accept_without_naming_the_work(server_url):
    """The accepted set appears in the transcript, or nothing is accepted.

    Checked as the absence of an action rather than the presence of a guard:
    `security-model.md` records that an injected instruction has a verdict tool
    within reach, and what bounds it is that acceptance enumerates its works
    where the curator can see them. An `accept_all` would look identical in the
    happy path and hollow that out.
    """
    payload, errored = await call(server_url, "art_review", action="help")

    assert errored is False
    verdict = next(action for action in payload["actions"] if action["action"] == "set_verdict")
    assert [param["name"] for param in verdict["required_parameters"]] == ["work_id", "verdict"]
    assert not [action for action in payload["actions"] if "all" in action["action"]]


async def test_a_verdict_with_no_work_named_is_refused_before_anything_is_written(server_url):
    payload, errored = await call(server_url, "art_review", action="set_verdict", verdict="accepted")

    assert errored is True
    assert "work_id" in payload["error"]


async def test_an_unknown_work_is_refused_by_name(server_url):
    payload, errored = await call(server_url, "art_review", action="set_verdict", work_id="not-a-work", verdict="accepted")

    assert errored is True
    assert "not-a-work" in payload["error"]


# -- what the whole surface promises ------------------------------------------


async def test_the_review_tool_still_reports_that_it_never_spends(server_url):
    """The write half arrived without a cost, and the summary still says so.

    `art_discovery` is the one tool that spends, and the design rests on it:
    a review action that reached a museum would put a cost inside the tool a
    curator clicks through, which is the boundary `api-contract.md` § Rejecting
    an image does not re-search exists to hold.
    """
    payload, errored = await call(server_url, "art_review", action="help")

    assert errored is False
    assert "Never spends" in payload["summary"]


@pytest.mark.parametrize("verdict", [Verdict.ACCEPTED, Verdict.REJECTED])
async def test_a_decided_works_previews_become_reclaimable(server_url, services, reviewable, verdict, settings):
    """The verdict is what arms the sweep, and before this chunk nothing could arm it.

    `operational-spec.md` § Add disk headroom recorded that the sweep would
    reclaim nothing whatever it did, because no shipped surface could set a
    terminal verdict. This is the test that the sentence is now out of date —
    and it is deliberately driven over the tool rather than the service, since
    the surface being able to arm it is the whole of what changed.
    """
    work, images = reviewable(previews=True)
    target = settings.art_root / images[0].preview_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"cached bytes")
    assert services.sweep.run().retained == 1, "held while the work is under review"

    _payload, errored = await call(server_url, "art_review", action="set_verdict", work_id=work.id, verdict=str(verdict))

    assert errored is False
    assert services.sweep.run().deleted == 1
    assert not target.exists()
