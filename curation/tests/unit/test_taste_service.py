"""The rules a judgment about the curator has to satisfy before it can be stored.

Service level, over the real store, because every rule here is about what the
*file* is allowed to end up holding and a fake store would let this suite agree
with itself about a shape SQLite would refuse.

**Every check in this file is a check on the write path, and that is the point
rather than an implementation detail.** Deleting a conversation nulls
`Affinity.source_turn_id`, so a stored `NOT NULL` or a cascading foreign key
would make the delete impossible or destructive. The invariants therefore live
where a *write* can be refused without saying anything about a row already on
disk, and the tests that prove they exist have to be here rather than against the
schema.
"""

from datetime import UTC, datetime

import pytest

from curation.persistence.discovery_records import (
    Affinity,
    AffinityDerivation,
    AffinitySentiment,
    Conversation,
    ConversationTurn,
    TurnRole,
)
from curation.persistence.records import VocabularyKind
from curation.services.errors import ServiceError
from curation.services.taste import NEEDS_RATIONALE, TasteService, validated_write


@pytest.fixture
def taste(services):
    return services.taste


@pytest.fixture
def a_turn(discovery_store):
    """A real conversation turn, so an `inferred` judgment has something to cite."""
    now = datetime.now(UTC)
    conversation = Conversation(id="conversation-1", started_at=now, last_turn_at=now)
    discovery_store.add_conversation(conversation)
    turn = ConversationTurn(
        id="turn-1",
        conversation_id=conversation.id,
        ordinal=0,
        role=TurnRole.CURATOR,
        text="Something calm for the living room.",
        created_at=now,
    )
    discovery_store.add_conversation_turn(turn)
    return turn


# -- what `set` refuses -------------------------------------------------------


def test_set_refuses_observed_and_names_the_path_that_can_write_it(taste):
    """`observed` is a claim only the review path can make truthfully.

    A row written by a caller claiming the product read the judgment out of
    accept-and-reject behaviour is a fabricated observation — indistinguishable
    afterwards from one the product earned, and with nothing behind it for a
    later rebuild to work from. The refusal has to *name the alternative*,
    because "not allowed" leaves a caller retrying blind.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation="observed",
            rationale="accepted four of their works",
        )

    assert "observed" in str(refused.value)
    assert "review" in str(refused.value)
    assert "stated" in str(refused.value)


@pytest.mark.parametrize("derivation", sorted(str(member) for member in NEEDS_RATIONALE))
def test_the_two_derivations_that_are_claims_about_the_curator_need_a_rationale(derivation, a_turn):
    """Required for `inferred` and `observed`, because it is what survives a delete.

    Driven through `validated_write` rather than through `set_affinity`, and
    deliberately: `set` refuses `observed` outright, so the rationale rule for
    that derivation is unreachable from it. The rule belongs to the write path —
    which is a function precisely so the review path that will one day assert
    `observed` goes through the same checks — and this is the test that says so.
    """
    with pytest.raises(ServiceError) as refused:
        validated_write(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation=derivation,
            source_turn_id=a_turn.id,
        )

    assert "rationale" in str(refused.value)
    # The reason, not just the requirement: this is the only evidence such a row
    # can be left with once the conversation behind it is gone.
    assert "Deleting a conversation" in str(refused.value)


def test_a_stated_judgment_needs_no_rationale_and_no_turn(taste):
    """The curator saying a thing is the whole provenance.

    The mirror of the test above, and it is not decoration: a rule applied to all
    three derivations would make the ordinary reaction — a curator pressing "not
    this" beside a picture — impossible to record without inventing an account of
    a judgment they made themselves.
    """
    view = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    assert view.affinity.derivation is AffinityDerivation.STATED
    assert view.affinity.rationale is None
    assert view.affinity.source_turn_id is None
    assert view.conversation_id is None


def test_an_inferred_judgment_must_cite_the_turn_it_was_read_out_of(taste):
    """The invariant the acceptance criterion is about, on the write and nowhere else.

    Both derivations are writable by a caller, so guarding only `observed` would
    leave the neighbouring door open: any client could otherwise write "the model
    read this out of what they said" citing nothing, which is the same
    unrebuildable, unauditable row.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation="inferred",
            rationale="they asked for calm grids",
        )

    assert "turn" in str(refused.value)
    assert "stated" in str(refused.value)


def test_an_inferred_judgment_citing_a_turn_that_does_not_exist_is_refused(taste):
    """A citation nobody can follow is the same as none, and worse for looking real."""
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(
            kind="artist",
            value="Kandinsky",
            sentiment="likes",
            open_to_more=True,
            derivation="inferred",
            rationale="they asked for calm grids",
            source_turn_id="no-such-turn",
        )

    assert "no-such-turn" in str(refused.value)


def test_openness_is_required_beside_sentiment_rather_than_defaulted(taste):
    """The two-fields rule, defended at the one place a default would creep in.

    The default that reads as safe — do not offer more — is the one that silently
    blacklists an artist the curator asked to keep hearing about, so there is no
    default at all.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(kind="artist", value="Kandinsky", sentiment="cool", open_to_more=None)

    assert "open_to_more" in str(refused.value)


def test_an_unknown_kind_is_refused_against_the_shared_vocabulary(taste):
    """`Affinity.kind` is `VocabularyKind` itself, not a matching copy of it.

    A free-text kind would turn a typo into a new dimension of taste, and nothing
    downstream could tell `subject` from `subjcet`.
    """
    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(kind="mood", value="calm", sentiment="likes", open_to_more=True)

    assert "mood" in str(refused.value)
    for kind in VocabularyKind:
        assert str(kind) in str(refused.value)


# -- what `set` does to an existing row ---------------------------------------


def test_set_is_an_upsert_on_the_thing_rather_than_on_an_id(taste):
    """One live judgment per thing, corrected in place.

    `create` would be a lie on the second call and `update` on the first, which
    is why the verb is `set` and why a correction needs no id — the handle is the
    name a model has in a sentence.
    """
    first = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)

    second = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    assert second.affinity.id == first.affinity.id
    assert second.affinity.sentiment is AffinitySentiment.DECLINES
    assert second.affinity.open_to_more is False
    assert second.affinity.created_at == first.affinity.created_at
    assert len(taste.list_affinities()) == 1


def test_the_same_name_under_two_kinds_is_two_judgments(taste):
    """Uniqueness is on the pair, and it has to be: 'Baroque' is a movement and
    could equally be a subject, and one row for both would make correcting one
    silently rewrite the other."""
    taste.set_affinity(kind="movement", value="Baroque", sentiment="loves", open_to_more=True)
    taste.set_affinity(kind="subject", value="Baroque", sentiment="declines", open_to_more=False)

    assert len(taste.list_affinities()) == 2


def test_a_correction_replaces_the_provenance_and_never_keeps_the_old_turn(taste, a_turn):
    """The R-17 rule: a row must never carry a turn that did not produce its judgment.

    Writing the fields given and leaving the rest is the cheap default, and it
    produces provenance that is a lie — indistinguishable afterwards from the
    real thing, from which a later rebuild either resurrects a superseded
    judgment or overwrites the curator's own correction.
    """
    inferred = taste.set_affinity(
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for calm grids",
        source_turn_id=a_turn.id,
    )
    assert inferred.affinity.source_turn_id == a_turn.id

    corrected = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    assert corrected.affinity.derivation is AffinityDerivation.STATED
    assert corrected.affinity.source_turn_id is None
    assert corrected.affinity.rationale is None


def test_a_weaker_provenance_cannot_overwrite_a_stronger_one(taste, a_turn):
    """A model's reading may not overwrite what the curator said.

    The ranks are the builder's ruling, stated at `_PROVENANCE_RANK`: `stated` is
    the curator's own words, `observed` is their own behaviour, `inferred` is a
    reading of what they said. Without this an agent's inference silently
    replaces a correction the curator made by hand, and the row that results
    looks exactly like one they never touched.
    """
    taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    with pytest.raises(ServiceError) as refused:
        taste.set_affinity(
            kind="artist",
            value="Kandinsky",
            sentiment="loves",
            open_to_more=True,
            derivation="inferred",
            rationale="they kept asking for grids",
            source_turn_id=a_turn.id,
        )

    assert "stated" in str(refused.value)
    standing = taste.list_affinities()[0].affinity
    assert standing.sentiment is AffinitySentiment.DECLINES
    assert standing.derivation is AffinityDerivation.STATED


def test_an_inference_may_correct_an_earlier_inference(taste, a_turn):
    """Equal rank passes, and it has to: re-deriving a judgment when the eliciting
    prompt improves is exactly the correction the retained turns exist for."""
    taste.set_affinity(
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="inferred",
        rationale="an early reading",
        source_turn_id=a_turn.id,
    )

    again = taste.set_affinity(
        kind="artist",
        value="Kandinsky",
        sentiment="loves",
        open_to_more=True,
        derivation="inferred",
        rationale="a better reading",
        source_turn_id=a_turn.id,
    )

    assert again.affinity.sentiment is AffinitySentiment.LOVES
    assert again.affinity.rationale == "a better reading"


def test_a_judgment_carries_the_thread_its_citation_belongs_to(taste, a_turn):
    """The way back from a judgment to the conversation that produced it.

    Resolved by the service rather than stored, so it cannot come apart from the
    citation — and so a browser link and a tool result cannot disagree about
    which thread a judgment came from.
    """
    view = taste.set_affinity(
        kind="artist",
        value="Kandinsky",
        sentiment="likes",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for calm grids",
        source_turn_id=a_turn.id,
    )

    assert view.conversation_id == a_turn.conversation_id


# -- reading and forgetting ---------------------------------------------------


def test_the_listing_narrows_by_each_of_the_three_things_worth_narrowing_by(taste, a_turn):
    taste.set_affinity(kind="artist", value="Kandinsky", sentiment="loves", open_to_more=True)
    taste.set_affinity(kind="movement", value="Bauhaus", sentiment="declines", open_to_more=False)
    taste.set_affinity(
        kind="artist",
        value="Agnes Martin",
        sentiment="loves",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for stillness",
        source_turn_id=a_turn.id,
    )

    assert [view.affinity.value for view in taste.list_affinities(kind="artist")] == ["Agnes Martin", "Kandinsky"]
    assert [view.affinity.value for view in taste.list_affinities(sentiment="declines")] == ["Bauhaus"]
    assert [view.affinity.value for view in taste.list_affinities(derivation="inferred")] == ["Agnes Martin"]


def test_forgetting_answers_with_what_was_forgotten(taste):
    """Not recoverable, so the acknowledgement names the thing rather than the id.

    A confirmation reporting a handle the curator never saw cannot be checked
    against what they meant to do.
    """
    written = taste.set_affinity(kind="artist", value="Kandinsky", sentiment="declines", open_to_more=False)

    gone = taste.delete_affinity(written.affinity.id)

    assert gone.affinity.value == "Kandinsky"
    assert taste.list_affinities() == []


def test_forgetting_something_that_is_not_there_is_refused_by_name(taste):
    with pytest.raises(ServiceError) as refused:
        taste.delete_affinity("no-such-affinity")

    assert "no-such-affinity" in str(refused.value)


# -- the shape the file is allowed to hold ------------------------------------


def test_an_inferred_judgment_with_no_turn_stores_and_reads_back(discovery_store):
    """**The acceptance criterion, from the storage side.**

    The write path refuses this combination, and the *file* must not — because
    deleting a conversation produces exactly it, and a stored constraint would
    make that delete impossible or would take the judgment with it. Written
    through the store directly, which is the only way to express "a row that
    exists but could not have been written", and read back through the service so
    the refusal cannot be hiding in the read either.
    """
    now = datetime.now(UTC)
    orphaned = Affinity(
        id="affinity-1",
        kind=VocabularyKind.ARTIST,
        value="Kandinsky",
        sentiment=AffinitySentiment.LIKES,
        open_to_more=True,
        derivation=AffinityDerivation.INFERRED,
        created_at=now,
        updated_at=now,
        rationale="they asked for calm grids",
        source_turn_id=None,
    )

    discovery_store.add_affinity(orphaned)

    (view,) = TasteService(discovery_store).list_affinities()
    assert view.affinity.derivation is AffinityDerivation.INFERRED
    assert view.affinity.source_turn_id is None
    assert view.affinity.rationale == "they asked for calm grids"
    assert view.conversation_id is None
