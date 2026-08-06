"""Where the MCP and HTTP surfaces describe the same record, they must agree.

`http/models.py`'s own docstring states the rule and then leaves it to memory:

    Field names match the MCP surface wherever both carry the same fact … they
    are not allowed to differ in what a thing is *called*, because that is how an
    agent and a click come to disagree about the same catalogue in a way no test
    would catch.

Nothing caught it. A grep over this suite found no reference to `ThemeOut` or
`_theme_fields` and no parity assertion of any kind, so a builder adding a Theme
field while working on the browser surface updated `_theme` and not
`_theme_fields`, `art_theme(action='get')` silently omitted it, and the suite
stayed green — precisely the disagreement the docstring forbids.

**A test rather than a shared projection, and that is a choice with a reason.**
`architecture.md`'s Decision Log (2026-07-27) says the two bindings each format
their own results, because tool results are shaped for a model and HTTP responses
for a UI. Extracting a common formatter would partially reverse that: the MCP
side returns plain dicts and the HTTP side returns pydantic models whose field
docstrings are themselves documentation. This keeps both, and makes divergence a
failure at the moment of the edit instead of a memory exercise.

**What is deliberately NOT pinned here: the artwork projections.** `WorkOut` adds
`fit` and `image` and drops `accepted_at`/`created_at`, where `_artwork_fields`
keeps the timestamps and has neither — they are two shapes for two readers, which
is the case the recorded decision actually describes. Theme, Artist and the
candidate-work summary are not that: they are one shape written twice.
"""

from datetime import UTC, datetime

import pytest

from curation.http import models as http_models
from curation.mcp import bindings
from curation.persistence.discovery_records import CandidateWork, DiscoveryRun, InitiatedBy, RunKind, RunStatus
from curation.persistence.records import Artist, Artwork, Theme

WHEN = datetime(2026, 8, 6, 12, 0, tzinfo=UTC)


def _fields(model: type) -> set[str]:
    """The field names a pydantic response model declares."""
    return set(model.model_fields)


def check_parity(record: str, mcp: set[str], http: set[str], http_only: frozenset[str] = frozenset()) -> None:
    """Raise unless two projections of `record` name the same facts the same way.

    A checked function rather than an assertion per pair, because the pairs in
    this tree all currently agree — so an assertion written directly against them
    can only ever be seen to pass. A mutation sweep loosened `==` to `<=` in two
    of them and nothing went red: with the comparison one-directional, a field
    dropped from a projection would have sailed through the very test written to
    catch it. The fabricated cases below are what make the strictness provable.

    Three ways to disagree, and the third is the one nobody thinks of:

    - a field the HTTP model has and the tool result does not — an agent cannot
      read a fact a click can;
    - the reverse;
    - an **exemption that no longer applies**. If a field named here as
      intentionally HTTP-only later appears on both, the entry stops describing
      anything and starts hiding the next real divergence behind a name that
      looks considered.
    """
    missing_from_mcp = http - mcp - http_only
    missing_from_http = mcp - http
    stale_exemptions = http_only - (http - mcp)

    assert not missing_from_mcp, (
        f"the HTTP {record} model carries {sorted(missing_from_mcp)} that the MCP projection does "
        "not. One record, two readers that must call its facts by the same names — the surface "
        "missing a field will silently omit it while its suite stays green. Add it to both, or "
        "record it as intentionally HTTP-only with its reason."
    )
    assert not missing_from_http, (
        f"the MCP {record} projection carries {sorted(missing_from_http)} that the HTTP model does "
        "not — a fact an agent can read and a click cannot."
    )
    assert not stale_exemptions, (
        f"{sorted(stale_exemptions)} is recorded as intentionally HTTP-only on {record}, but the "
        "two projections now agree about it. Remove the exemption: one that no longer applies "
        "hides the next real divergence behind a name that reads as considered."
    )


def test_the_theme_projections_carry_the_same_field_names():
    """One shape, two writers. Adding a field to one must fail until both follow."""
    theme = Theme(id="thm_1", name="Quiet", created_at=WHEN)

    check_parity("Theme", set(bindings._theme_fields(theme)), _fields(http_models.ThemeOut))


def test_the_artist_projections_carry_the_same_field_names():
    artist = Artist(id="art_1", name="Hokusai")

    check_parity("Artist", set(bindings._artist_fields(artist)), _fields(http_models.ArtistOut))


#: The one field `CandidateWorkOut` carries that `_work_summary` does not, and
#: why the difference is intended on both sides rather than an omission.
#:
#: The HTTP model shows the run view and the review grid, where a curator judging
#: a work list is judging the engine's reasoning as much as the titles. The MCP
#: summary is deliberately "enough to choose and to act, and no more" — and the
#: same prose repeated across forty listing rows is what pushed that shape past
#: the token budget its own docstring records measuring.
#:
#: Named rather than tolerated by a subset check: an exemption list of one is a
#: decision, and a bare `<=` would silently absorb the next four.
HTTP_ONLY_ON_CANDIDATE_WORK = frozenset({"rationale"})


def test_the_candidate_work_projections_agree_but_for_one_named_field():
    """The seven keys the MCP surface writes once, against the HTTP model's eight.

    Until 2026-08-06 those seven were written out at four sites with identical
    expressions — three in `bindings.py` and one in `api.py`. Adding `provenance`
    took four coordinated edits, and the next field added to `CandidateWork` would
    have reached some of them and not others.

    Three of the four are now one function. This holds the fourth, which cannot
    be merged into it: the HTTP surface returns a typed model, not a dict.
    """
    work = _work()

    check_parity(
        "CandidateWork",
        set(bindings._work_summary(work)),
        _fields(http_models.CandidateWorkOut),
        HTTP_ONLY_ON_CANDIDATE_WORK,
    )


#: The one field `RunOut` carries that the tool result does not.
#:
#: `is_terminal` is carried for the browser rather than left for it to derive
#: from a list of status names, because that list is the thing that goes stale: a
#: tenth status added to the enum would leave a browser polling a finished run
#: for ever with nothing failing to say so. A model reads `status` itself and has
#: the enum's meaning in the tool description, so it needs no such crutch.
HTTP_ONLY_ON_RUN = frozenset({"is_terminal"})


def test_the_run_projections_agree_but_for_one_named_field():
    """Pinned while both surfaces were being changed at once, which is when it matters.

    `http/api.py`'s run listing carried a note saying the cap had to reach both
    surfaces together, "because fixing one alone is how the two come to
    disagree". The same is true of the row's field names, and nothing was
    checking them.
    """
    run = DiscoveryRun(
        id="r1",
        kind=RunKind.DISCOVERY,
        initiated_by=InitiatedBy.MCP_CLIENT,
        status=RunStatus.COMPLETED,
        approval_required=False,
        started_at=WHEN,
    )

    check_parity("DiscoveryRun", set(bindings._run_fields(run)), _fields(http_models.RunOut), HTTP_ONLY_ON_RUN)


def test_a_field_only_the_http_model_has_is_rejected():
    """The direction a builder hits while working on the browser surface."""
    with pytest.raises(AssertionError, match="MCP projection does not"):
        check_parity("Theme", mcp={"theme_id", "name"}, http={"theme_id", "name", "shuffle"})


def test_a_field_only_the_tool_result_has_is_rejected():
    """The other direction, which a UI-focused reviewer is least likely to notice."""
    with pytest.raises(AssertionError, match="a click cannot"):
        check_parity("Theme", mcp={"theme_id", "name", "shuffle"}, http={"theme_id", "name"})


def test_an_exemption_that_no_longer_applies_is_rejected():
    """A named difference must keep being a difference, or it stops meaning anything."""
    with pytest.raises(AssertionError, match="now agree about it"):
        check_parity(
            "CandidateWork",
            mcp={"work_id", "rationale"},
            http={"work_id", "rationale"},
            http_only=frozenset({"rationale"}),
        )


def test_the_mcp_listing_and_detail_shapes_both_compose_the_summary():
    """The intra-surface half of the same defect, and the reason it is safe here.

    `_candidate_detail` does not compose `_candidate_summary`, and its docstring
    is right about why: `_shown_fields` appends an image block as a side effect
    of assigning an index, so composing the two would picture one instance twice
    and charge the caller for both. That argument is about the image half and
    never reached the seven text keys, which is how they came to be repeated.

    Asserted through the real projections rather than by reading them: a later
    edit that re-inlines one of these shapes would restore the drift this whole
    module exists to prevent, and nothing else would notice.
    """
    work = _work()
    view = _view(work)
    pictures = bindings._Pictures()
    summary_keys = set(bindings._work_summary(work))

    assert summary_keys <= set(bindings._candidate_summary(view, pictures))
    assert summary_keys <= set(bindings._candidate_detail(view, pictures))


def check_divergence(mcp: set[str], http: set[str], mcp_only: set[str], http_only: set[str]) -> None:
    """Raise unless each surface still carries the fields that make it its own shape.

    The mirror of `check_parity`, and it needs the same treatment for the same
    reason: written as a bare assertion against the real tree it can only be seen
    to pass, and a sweep proved that. Weakening `>= {"accepted_at", "created_at"}`
    to `>= set()` left it vacuously true and every test green — an alert that had
    stopped alerting, in a test whose entire purpose is to alert.
    """
    lost_from_http = http_only - (http - mcp)
    lost_from_mcp = mcp_only - (mcp - http)

    assert not lost_from_http, (
        f"WorkOut no longer carries {sorted(lost_from_http)} uniquely — the fields that make it a "
        "UI's shape rather than a tool result's: how the held master meets the wall, and where to "
        "fetch the picture. These projections converging is a reason to re-read the Decision Log's "
        "per-surface-formatting rationale, not to widen this test."
    )
    assert not lost_from_mcp, (
        f"the tool result no longer carries {sorted(lost_from_mcp)} uniquely — the timestamps "
        "WorkOut drops. Same conclusion as above."
    )


def test_the_artwork_projections_are_free_to_differ_and_actually_do():
    """The scoped-out case, asserted so the scope-out is a fact rather than a claim.

    `architecture.md`'s per-surface-formatting rationale describes exactly this
    pair — two shapes for two readers — and the tests above would be wrong to
    cover it. Written as a test because "these may differ" is otherwise
    indistinguishable from "nobody checked", and because the divergence is the
    *evidence* for the rationale: if the two ever converged, the recorded reason
    for keeping every projection independent would have lost its only example,
    and the tests above would deserve to grow a fourth pair.
    """
    artwork = Artwork(id="awk_1", title="The Great Wave", created_at=WHEN)

    check_divergence(
        mcp=set(bindings._artwork_fields(artwork)),
        http=_fields(http_models.WorkOut),
        mcp_only={"accepted_at", "created_at"},
        http_only={"fit", "image"},
    )


def test_the_ui_shape_losing_its_own_fields_is_reported():
    """The alert firing, which the real tree cannot show while the pair still differs.

    **One direction per case, and that is the correction rather than the design.**
    A single fabricated case that broke both directions at once passed whichever
    assertion fired first, so a sweep could blank either one and the test stayed
    green — the same vacuity it was written to prevent, one level up. Each case
    now leaves the other direction intact, so only the assertion under test can
    raise.
    """
    with pytest.raises(AssertionError, match="WorkOut no longer carries"):
        check_divergence(
            mcp={"artwork_id", "created_at"},
            http={"artwork_id"},
            mcp_only={"created_at"},
            http_only={"fit"},
        )


def test_the_tool_result_losing_its_own_fields_is_reported():
    with pytest.raises(AssertionError, match="the tool result no longer carries"):
        check_divergence(
            mcp={"artwork_id"},
            http={"artwork_id", "fit"},
            mcp_only={"created_at"},
            http_only={"fit"},
        )


def _work() -> CandidateWork:
    """The minimum a candidate work needs to exist. Only its key names matter here."""
    return CandidateWork(
        id="cw_1",
        discovery_run_id="run_1",
        proposed_title="The Great Wave",
        rationale="named by the model",
        work_dedup_key="great-wave",
    )


def _view(work: CandidateWork):
    """A CandidateView with no instances, which is all these shapes need.

    Built here rather than in a fixture because only this module wants it: the
    parity claim is about key *names*, so an empty view exercises every key
    without needing a store, a run, or an image on disk.
    """
    from curation.services.review import CandidateView  # noqa: PLC0415

    return CandidateView(work=work, instances_held=0, instances_surviving=0, shown=None)
