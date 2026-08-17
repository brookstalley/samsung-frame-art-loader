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
    AffinityListOut,
    AffinityOut,
    ArtistOut,
    CandidateCardOut,
    CandidatePageOut,
    CandidateWorkOut,
    ConversationListOut,
    ConversationOut,
    ConversationTurnOut,
    ConversationViewOut,
    EstimateOut,
    FacetGroupOut,
    FacetOptionOut,
    FitOut,
    ImageOut,
    InstanceListingOut,
    InstanceOut,
    RunOut,
    RunTallyOut,
    RunViewOut,
    SampleOut,
    SearchUsageOut,
    SpendOut,
    SuggestionOut,
    ThemeDetailOut,
    ThemeOut,
    VerdictOut,
    WorkOut,
    WorkPageOut,
)
from curation.persistence.discovery_records import (
    AffinityDerivation,
    AffinitySentiment,
    InitiatedBy,
    ResolutionStatus,
    RunKind,
    RunStatus,
    TurnRole,
    Verdict,
    WorkProvenance,
)
from curation.persistence.records import ArtworkStatus, VocabularyKind
from curation.services.display_fit import DisplayFit


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
        "commentary": None,
        "rights": None,
        "status": ArtworkStatus.ACCEPTED.value,
        "fit": None,
        "fit_note": None,
        "image": ImageOut(available=False, source_kind=None, note="No image held."),
    }
    return WorkOut(**(fields | overrides))


def a_listing(works, *, total=None, truncated=False, offset=0, facets=()) -> dict:
    """One page of the catalogue, as `/api/works` answers it.

    `facets` defaults to none rather than to all six kinds. The server always
    returns all six, and a builder that invented them would put a vocabulary in
    the test that no catalogue produced — a facet rail asserted against values
    nobody holds. A test about the rail passes the groups it means.
    """
    works = list(works)
    return WorkPageOut(
        works=works,
        total=len(works) if total is None else total,
        limit=100,
        offset=offset,
        truncated=truncated,
        facets=list(facets),
    ).model_dump(mode="json")


def a_facet_option(value, count, *, selected=False, disabled=None) -> FacetOptionOut:
    """One value a facet control offers.

    `disabled` follows the count unless a test names it, because that is the
    service's own rule — an option that would select nothing is returned disabled
    rather than omitted — and a fixture free to disagree with it could assert a
    rail state no server could produce.
    """
    return FacetOptionOut(
        value=value,
        count=count,
        selected=selected,
        disabled=(count == 0) if disabled is None else disabled,
    )


def a_facet_group(kind, options, *, total_values=None, truncated=False) -> FacetGroupOut:
    """One facet kind as the rail renders it."""
    options = list(options)
    return FacetGroupOut(
        kind=kind,
        options=options,
        total_values=len(options) if total_values is None else total_values,
        truncated=truncated,
    )


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
        # Null by default because the default is a work the run *asked for*, which
        # no browse query produced. A test wanting an offer sets both, as the
        # server does — leaving them null on an `offered` work is a state the
        # service will not write.
        "offered_for_artist": None,
        "offered_artist_matched": None,
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
    # The two settable defaults go through `|` rather than being passed as
    # keywords beside `**overrides`, which raises "multiple values for keyword
    # argument" the moment a caller names one — and `image_resolution_available`
    # is the one branch of `runSentence` that cannot be reached any other way.
    fields = {
        "searches": SearchUsageOut(used=1, allowance=10, exhausted=False),
        "image_resolution_available": True,
    }
    view = RunViewOut(run=run, tally=tally, works=works, **(fields | overrides))
    return view.model_dump(mode="json")


def an_instance(**overrides) -> InstanceOut:
    """One scan, defaulting to the one on offer with a picture that travels."""
    fields = {
        "image_id": "image-1",
        "work_id": "work-1",
        "url": "https://artic.edu/persistence",
        "provider": "artic",
        "confidence": 0.92,
        "is_selected": True,
        "rejected": False,
        "rights_status": "public_domain",
        "selection_rationale": None,
        "fit": FitOut(
            verdict=DisplayFit.NATIVE.value,
            rendered_width=3316,
            rendered_height=1597,
            rendered_long_edge_inches=27.4,
        ),
        "fit_note": None,
        "preview_available": True,
        "preview_note": None,
    }
    return InstanceOut(**(fields | overrides))


def a_card(work: CandidateWorkOut | None = None, shown: InstanceOut | None = ..., **overrides) -> CandidateCardOut:
    """One review card, defaulting to a work standing on the scan it was offered.

    `shown` defaults through a sentinel rather than through `None`, because
    "no scan at all" is a state this surface has to be able to express and a
    plain `None` default would make it unreachable.
    """
    work = work or a_candidate()
    shown = an_instance(work_id=work.work_id) if shown is ... else shown
    fields = {
        "work": work,
        "shown": shown,
        "shown_is_on_offer": shown is not None and shown.is_selected,
        "instances_held": 0 if shown is None else 1,
        "instances_surviving": 0 if shown is None else 1,
    }
    return CandidateCardOut(**(fields | overrides))


def a_candidate_page(cards, *, run: RunOut | None = None, total=None, truncated=False, offset=0) -> dict:
    """One page of a run's works, as `/api/runs/{id}/candidates` answers it."""
    cards = list(cards)
    return CandidatePageOut(
        run=run or a_run(status=RunStatus.COMPLETED.value, is_terminal=True),
        works=cards,
        total=len(cards) if total is None else total,
        limit=30,
        offset=offset,
        truncated=truncated,
    ).model_dump(mode="json")


def an_instance_listing(instances=None, *, work: CandidateWorkOut | None = None, held=None, **overrides) -> dict:
    """A work's alternates, as `/api/candidates/{id}/images` answers it.

    `held` and the truncation flag are computed from the instances unless a test
    names them, so a fixture cannot claim a complete card while showing a
    truncated one — which is the exact confusion the two counts exist to prevent.
    """
    work = work or a_candidate()
    instances = [an_instance(work_id=work.work_id)] if instances is None else list(instances)
    held = len(instances) if held is None else held
    fields = {
        "work": work,
        "instances": instances,
        "held": held,
        "surviving_held": len([i for i in instances if not i.rejected]),
        "truncated": len(instances) < held,
        "shows_every_choosable_instance": True,
    }
    return InstanceListingOut(**(fields | overrides)).model_dump(mode="json")


def a_verdict(work: CandidateWorkOut | None = None, **overrides) -> dict:
    """The answer to recording a verdict, defaulting to a plain acceptance."""
    work = work or a_candidate(verdict=Verdict.ACCEPTED.value)
    fields = {
        "work": work,
        "artwork_id": "artwork-minted",
        "decided_at": "2026-08-05T10:06:00+00:00",
        "minted_artist": None,
        "possible_duplicate_artists": [],
        "notice": None,
    }
    return VerdictOut(**(fields | overrides)).model_dump(mode="json")


def an_artist(**overrides) -> ArtistOut:
    fields = {
        "artist_id": "artist-1",
        "name": "Salvador Dalí",
        "nationality": None,
        "born": None,
        "died": None,
        "lifespan_text": None,
        "biography": None,
        "family_name": None,
        "given_name": None,
        # Required-but-nullable, like the two name parts above it: `ArtistOut`
        # gives none of these a default, so the model refuses a payload that
        # omits one rather than inventing a null. That is what caught this
        # fixture when the field landed.
        "display_nationality": None,
    }
    return ArtistOut(**(fields | overrides))


def a_theme(**overrides) -> ThemeOut:
    fields = {
        "theme_id": "theme-1",
        "name": "Winter",
        "description": None,
        "rotation_interval_seconds": None,
        "shuffle": None,
        "created_at": "2026-08-12T09:00:00+00:00",
    }
    return ThemeOut(**(fields | overrides))


def a_theme_detail(works, *, theme: ThemeOut | None = None) -> dict:
    """A theme and its works in curated order, as every membership write answers.

    The order in this body is the whole point of the shape: `POST`/`DELETE` on a
    theme's works and the position route all answer with it, so the screen
    repaints from what the write returned rather than reading the order back.
    Which means a test can hand the client an order no catalogue would produce
    and see whether the table shows it.
    """
    return ThemeDetailOut(theme=theme or a_theme(), works=list(works)).model_dump(mode="json")


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
        "year": None,
        "month": None,
    }
    return SpendOut(**(fields | overrides)).model_dump(mode="json")


def a_sample(title="Untitled No. 5", **overrides) -> SampleOut:
    """One picture beside a name, defaulting to one the collection can show."""
    fields = {
        "title": title,
        "artist": "Agnes Martin",
        "image_url": f"https://www.artic.edu/iiif/2/{abs(hash(title)) % 100000}/full/843,/0/default.jpg",
    }
    return SampleOut(**(fields | overrides))


def a_suggestion(value="Agnes Martin", *, kind="artist", samples=None) -> SuggestionOut:
    return SuggestionOut(kind=kind, value=value, samples=list(samples or []))


def a_turn(text="Something calm for the living room.", **overrides) -> ConversationTurnOut:
    """One turn, defaulting to the curator's own and offering nothing."""
    fields = {
        "turn_id": "turn-1",
        "ordinal": 0,
        "role": TurnRole.CURATOR.value,
        "text": text,
        "suggested": [],
        "committed_run_id": None,
        "created_at": "2026-08-12T10:00:00+00:00",
    }
    return ConversationTurnOut(**(fields | overrides))


def a_conversation(**overrides) -> ConversationOut:
    fields = {
        "conversation_id": "conversation-under-test",
        "started_at": "2026-08-12T10:00:00+00:00",
        "last_turn_at": "2026-08-12T10:01:00+00:00",
        "summary": None,
    }
    return ConversationOut(**(fields | overrides))


def a_thread(turns=None, **overrides) -> dict:
    """A whole conversation as `/api/conversations/{id}` answers it.

    `committed_run_id` and `unanswered_turn_id` are derived from the turns rather
    than passed in, exactly as the server derives them. A fixture free to
    disagree with itself could assert a screen no server could ever have
    produced — a commit card polling a run no turn committed, or a retry button
    over a question that was answered.
    """
    turns = [a_turn()] if turns is None else list(turns)
    committed = next((turn.committed_run_id for turn in reversed(turns) if turn.committed_run_id), None)
    last = turns[-1] if turns else None
    unanswered = last.turn_id if last is not None and last.role == TurnRole.CURATOR.value and not last.committed_run_id else None
    fields = {
        "conversation": a_conversation(),
        "turns": turns,
        "committed_run_id": committed,
        "failure": None,
        "unanswered_turn_id": unanswered,
    }
    return ConversationViewOut(**(fields | overrides)).model_dump(mode="json")


def a_conversation_list(conversations=None) -> dict:
    conversations = [a_conversation()] if conversations is None else list(conversations)
    return ConversationListOut(conversations=conversations, count=len(conversations)).model_dump(mode="json")


def an_affinity(value="Agnes Martin", **overrides) -> AffinityOut:
    """One judgment, defaulting to one the curator stated themselves.

    `stated` is the default because it is what every reaction and every
    correction writes, and because it is the one derivation that legitimately
    carries neither a rationale nor a turn — a builder defaulting to `inferred`
    would make every test that did not care about provenance assert against a
    row the write path would refuse.
    """
    fields = {
        "affinity_id": f"affinity-{abs(hash(value)) % 100000}",
        "kind": VocabularyKind.ARTIST.value,
        "value": value,
        "sentiment": AffinitySentiment.LOVES.value,
        "open_to_more": True,
        "derivation": AffinityDerivation.STATED.value,
        "rationale": None,
        "source_turn_id": None,
        "conversation_id": None,
        "artist_id": None,
        "created_at": "2026-08-12T10:00:00+00:00",
        "updated_at": "2026-08-12T10:00:00+00:00",
    }
    return AffinityOut(**(fields | overrides))


def a_taste(affinities=None) -> dict:
    """The whole taste as `/api/affinities` answers it.

    `count` is derived rather than passed, exactly as the server derives it: a
    fixture free to disagree with itself could assert an empty state over a list
    that holds rows, or a populated screen over none.
    """
    affinities = [] if affinities is None else list(affinities)
    return AffinityListOut(affinities=affinities, count=len(affinities)).model_dump(mode="json")
