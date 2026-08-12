"""The one operation in this product that genuinely destroys a record.

Beside `test_conversation_service.py` rather than inside it, because this file
asks a different question of the same service: not what a thread does while it is
alive, but what survives it. Every test here is about something the delete must
*not* do — cascade to a judgment, move a month total, refuse itself because a
column would not allow the shape it produces.

**Nulling and cascading are one line apart and both read as correct in a diff.**
That is the reason the plan names the mutation sweep for this chunk, and it is
the reason these tests assert the surviving rows rather than the deleted ones: a
delete that took the affinities with it would satisfy every "the conversation is
gone" assertion anyone would think to write.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from curation.discovery.conversation import Suggestion
from curation.persistence.discovery_records import AffinityDerivation, SpendCategory
from curation.services.conversation import ConversationService
from curation.services.errors import ServiceError


@pytest.fixture
def talking(services, conversation_engine, discovery_store, runner):
    """A conversation with something to say, over a runner that does not spawn."""
    conversation_engine.suggested = (Suggestion(kind="artist", value="Agnes Martin"),)
    return ConversationService(discovery_store, conversation_engine, services.discovery, runner)


@pytest.fixture
def a_thread(talking, services):
    """A thread that has spent money and produced an inferred judgment.

    Both are needed and neither is decoration: the affinity is what must survive
    with a null citation, and the spend row is what must keep the month total
    where it was.
    """
    conversation_id = talking.start().conversation.id
    view = talking.speak(conversation_id, "Something calm for the living room.")
    answered = view.turns[-1].turn
    services.taste.set_affinity(
        kind="artist",
        value="Agnes Martin",
        sentiment="loves",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for stillness, and said the room is pale",
        source_turn_id=answered.id,
    )
    return conversation_id


def test_deleting_a_thread_takes_the_conversation_and_its_turns(talking, a_thread, discovery_store):
    """The destroying half. Everything else here is about what it must leave."""
    talking.delete(a_thread)

    assert discovery_store.get_conversation(a_thread) is None
    assert discovery_store.list_conversation_turns(a_thread) == []
    with pytest.raises(ServiceError):
        talking.get(a_thread)


def test_the_judgment_it_produced_stands_with_a_null_citation(talking, a_thread, services):
    """**Detached, not cascaded.** The count is asserted first, deliberately.

    An assertion over a list that might be empty passes vacuously, and this is
    exactly the shape that would: `all(a.source_turn_id is None for a in [])` is
    true of a delete that destroyed every judgment, which is the failure the test
    exists to catch. So the count comes first and the fields after it.
    """
    talking.delete(a_thread)

    standing = services.taste.list_affinities()
    assert len(standing) == 1
    (view,) = standing
    assert view.affinity.value == "Agnes Martin"
    assert view.affinity.source_turn_id is None
    assert view.conversation_id is None
    # The judgment itself is untouched, and the derivation is not softened to
    # `stated` — that would be the product claiming the curator said something
    # they never said.
    assert view.affinity.derivation is AffinityDerivation.INFERRED
    assert view.affinity.rationale == "they asked for stillness, and said the room is pale"


def test_the_month_total_is_the_same_number_across_the_delete(talking, a_thread, discovery):
    """**The acceptance criterion, asserted rather than reasoned about.**

    The figure is read from the same method the month report reads, before and
    after, and compared to itself. A ledger whose totals fall because somebody
    tidied a transcript is a number that lies about the past — worse than a
    number with a gap in its provenance.
    """
    now = datetime.now(UTC)
    before = discovery.spend_in_month(year=now.year, month=now.month)
    assert before > Decimal(0), "the thread spent nothing, so this test would pass against a cascade"

    talking.delete(a_thread)

    assert discovery.spend_in_month(year=now.year, month=now.month) == before


def test_the_ledger_entry_keeps_its_amount_and_loses_only_its_citation(talking, a_thread, discovery_store):
    """The row behind the total, so a passing total cannot be hiding a rewrite.

    A delete that halved one row and doubled another would leave the month total
    where it was; this is what says the amounts were not touched at all.
    """
    before = [(record.id, record.cost_usd, record.category) for record in discovery_store.list_spend_records()]
    assert before, "no spend was recorded, so this test would pass against a cascade"

    talking.delete(a_thread)

    after = discovery_store.list_spend_records()
    assert [(record.id, record.cost_usd, record.category) for record in after] == before
    assert [record.conversation_turn_id for record in after] == [None] * len(after)
    assert after[0].category is SpendCategory.CONVERSATION_TOKENS


def test_the_deletion_reports_what_it_detached(talking, a_thread):
    talking_result = talking.delete(a_thread)

    assert talking_result.conversation_id == a_thread
    assert talking_result.turns_deleted == 2
    assert talking_result.affinities_detached == 1
    assert talking_result.spend_records_detached == 1


def test_the_confirmation_names_what_is_lost_rather_than_a_row_count(talking, a_thread):
    """The requirement the IA states for every consequential act on this surface.

    "3 rows deleted" tells a curator nothing about what they can no longer do.
    What they can no longer do is rebuild those judgments when the way this
    product reads a conversation improves, and that is not recoverable.
    """
    said = talking.delete(a_thread).describe()

    assert "rebuilt" in said
    assert "cannot be undone" in said
    # The judgments are named as *kept*, because a sentence about destruction
    # that did not say what survived would read as a cascade.
    assert "kept" in said
    assert "no month total changes" in said


def test_a_thread_that_produced_nothing_says_only_what_it_destroyed(talking):
    """The confirmation is composed, not a fixed paragraph.

    A conversation nobody reacted to and nothing was billed for has no detached
    judgments and no detached spend, and a sentence claiming otherwise would be
    telling the curator they are losing provenance they never had.
    """
    said = talking.delete(talking.start().conversation.id).describe()

    assert "cannot be undone" in said
    assert "rebuilt" not in said
    assert "month total" not in said


def test_a_run_the_thread_committed_survives_and_the_seam_does_not(talking, a_thread, discovery, runner):
    """The third consequence: provenance is gone rather than degraded.

    Nothing is orphaned — a run with no committing turn is ordinary, because that
    is every run started from Discover — but the record that *this* conversation
    is where it came from goes with the turn, and the confirmation says so.
    """
    view = talking.commit(a_thread, "Agnes Martin")
    run_id = view.committed_run_id
    assert run_id is not None

    deletion = talking.delete(a_thread)

    assert deletion.runs_unattributed == 1
    assert "nothing will record that this conversation is where they came from" in deletion.describe().lower()
    assert discovery.get_run(run_id) is not None


def test_deleting_an_unknown_conversation_is_refused_by_name(talking):
    with pytest.raises(ServiceError) as refused:
        talking.delete("no-such-conversation")

    assert "no-such-conversation" in str(refused.value)


def test_a_judgment_from_another_thread_is_not_touched(talking, a_thread, services):
    """The detach is scoped to the turns being destroyed.

    A delete that nulled every citation in the file would pass every test above,
    because every one of them looks at the thread being deleted.
    """
    other = talking.start().conversation.id
    view = talking.speak(other, "Something loud for the hall.")
    services.taste.set_affinity(
        kind="movement",
        value="Bauhaus",
        sentiment="likes",
        open_to_more=True,
        derivation="inferred",
        rationale="they asked for hard edges",
        source_turn_id=view.turns[-1].turn.id,
    )

    talking.delete(a_thread)

    surviving = {entry.affinity.value: entry for entry in services.taste.list_affinities()}
    assert len(surviving) == 2
    assert surviving["Bauhaus"].affinity.source_turn_id is not None
    assert surviving["Bauhaus"].conversation_id == other
    assert surviving["Agnes Martin"].affinity.source_turn_id is None
