"""The thread, the money it costs, and the seam onto a run.

Service level, over the real store and the real spend path, with the model
behind a fake — the arrangement every run-lifecycle test uses, and for the same
reason: the interesting cases are a turn that fails after being billed, a turn
that fails before being billed, and a deployment with no key, none of which can
be provoked cheaply or reliably against a live API.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fakes import a_billed_failure, a_collection_holding

from curation.discovery.conversation import ConversationFailure, Suggestion
from curation.persistence.discovery_records import SpendCategory, TurnRole
from curation.services.conversation import ConversationService
from curation.services.errors import ServiceError


@pytest.fixture
def talking(services, conversation_engine, discovery_store, runner):
    """A conversation with something to say, over a runner that does not spawn.

    The synchronous `runner` fixture rather than `services.runner`, for the
    reason that fixture exists: the shipped runner hands phase 1 to a worker so
    `start` can return at once, which is right in a deployment and is a thread
    still writing to the catalogue while a unit test tears the file down.
    """
    conversation_engine.suggested = (Suggestion(kind="artist", value="Agnes Martin"),)
    return ConversationService(discovery_store, conversation_engine, services.discovery, runner)


def test_a_turn_writes_a_conversation_tokens_row_in_the_call_that_spends(talking, discovery):
    """The chunk's own rule: the producer ships with the category or not at all.

    Attributed to the turn and to no run — "what did talking cost" and "what did
    asking for Kandinsky cost" are separate questions, and folding one into the
    other would make a run's estimate unfalsifiable against its actuals.
    """
    view = talking.speak(talking.start().conversation.id, "Something calm.")

    (record,) = discovery._store.list_spend_records()
    assert record.category is SpendCategory.CONVERSATION_TOKENS
    assert record.cost_usd == Decimal("0.00001896")
    assert record.discovery_run_id is None
    assert record.conversation_turn_id == view.turns[-1].turn.id


def test_a_turn_appears_in_the_month_total(talking, discovery):
    """The acceptance criterion, read off the figure the month report reads."""
    now = datetime.now(UTC)
    before = discovery.spend_in_month(year=now.year, month=now.month)

    talking.speak(talking.start().conversation.id, "Something calm.")

    assert discovery.spend_in_month(year=now.year, month=now.month) == before + Decimal("0.00001896")


def test_a_thread_carries_every_earlier_turn_into_the_next_question(talking, conversation_engine):
    """A conversation that sent only the newest question is not a conversation."""
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")
    talking.speak(conversation_id, "Anyone else?")

    latest = conversation_engine.threads[-1]
    assert [turn.role for turn in latest] == [TurnRole.CURATOR, TurnRole.SYSTEM, TurnRole.CURATOR]
    assert [turn.text for turn in latest][::2] == ["Something calm.", "Anyone else?"]


def test_a_failed_turn_stays_in_the_thread_and_is_not_an_error(talking, conversation_engine):
    """The requirement, at the level that decides it.

    The curator's question is written *before* the model is asked, so nothing
    about a failure can take it away — and the refusal comes back on the view
    rather than as an exception, because an exception carries no thread and a
    client rendering one would show a sentence with the question nowhere.
    """
    conversation_engine.error = ConversationFailure("the model could not be reached")
    conversation_id = talking.start().conversation.id

    view = talking.speak(conversation_id, "Something calm.")

    assert view.failure == "the model could not be reached"
    assert [turn.turn.text for turn in view.turns] == ["Something calm."]
    assert view.unanswered is not None
    # And it survives a fresh read, with the *reason* gone: what is durable is
    # that the question has no answer, which is the actionable half.
    reread = talking.get(conversation_id)
    assert reread.failure is None
    assert reread.unanswered is not None


def test_a_failure_that_was_billed_still_writes_its_row(talking, conversation_engine, discovery):
    """A 2xx that could not be read was paid for.

    A month total that omitted exactly the failures would under-report by what
    the failures cost, which is the under-reporting this ledger exists to stop.
    """
    conversation_engine.error = a_billed_failure()

    talking.speak(talking.start().conversation.id, "Something calm.")

    (record,) = discovery._store.list_spend_records()
    assert record.category is SpendCategory.CONVERSATION_TOKENS
    assert record.cost_usd == Decimal("0.00011843")


def test_a_failure_that_reached_no_provider_writes_nothing(talking, conversation_engine, discovery):
    """The distinction that makes retrying safe rather than a second charge."""
    conversation_engine.error = ConversationFailure("could not reach OpenRouter")

    talking.speak(talking.start().conversation.id, "Something calm.")

    assert discovery._store.list_spend_records() == []


def test_retrying_answers_the_question_already_asked_rather_than_asking_it_again(talking, conversation_engine):
    """The whole of this chunk's idempotency, and it is the transcript's doing.

    A retry sends no text. So it cannot append a second copy of the question, and
    a thread whose last turn *was* answered has nothing outstanding — which is
    exactly the case where the model was billed and the response was lost coming
    back. The double-spend window is closed by what the thread says rather than
    by a key the client has to remember to send.
    """
    conversation_engine.error = ConversationFailure("the model could not be reached")
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")

    conversation_engine.error = None
    view = talking.speak(conversation_id)

    assert [turn.turn.text for turn in view.turns] == ["Something calm.", conversation_engine.reply]
    assert view.unanswered is None


def test_retrying_an_answered_thread_is_refused_rather_than_spending_again(talking):
    """The lost-response case, refused by the only thing that knows: the thread."""
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")

    with pytest.raises(ServiceError, match="nothing to retry"):
        talking.speak(conversation_id)


def test_a_turn_names_things_and_shows_a_few_pictures_for_each(services, conversation_engine, discovery_store, runner):
    """Samples come from the collection the product already browses, and are free.

    The lookup is the same seam a run supplements from — a museum API that
    charges nothing — so `conversation_tokens` is the whole price of a turn and
    there is no second paid thing to account for.
    """
    collection = a_collection_holding(**{"Agnes Martin": ["Untitled No. 5", "Friendship", "The Islands"]})
    conversation_engine.suggested = (
        Suggestion(kind="artist", value="Agnes Martin"),
        Suggestion(kind="movement", value="Minimalism"),
    )
    talking = ConversationService(discovery_store, conversation_engine, services.discovery, runner, collection=collection)

    view = talking.speak(talking.start().conversation.id, "Something calm.")

    named = view.turns[-1].suggested
    assert [suggestion.value for suggestion, _ in named] == ["Agnes Martin", "Minimalism"]
    artist_samples = named[0][1]
    assert [sample.title for sample in artist_samples] == ["Untitled No. 5", "Friendship", "The Islands"]
    assert all(sample.image_url for sample in artist_samples)
    # A movement is named and carries nothing: the collection is browsed by
    # artist and by nothing else, and answering a movement with an artist's
    # works would be the product inventing a lookup it has not measured.
    assert named[1][1] == ()


def test_the_samples_are_frozen_into_the_turn_rather_than_looked_up_on_read(
    services, conversation_engine, discovery_store, runner
):
    """The transcript is a record of what was said, not a live index.

    A thread re-read after the collection changed must show the pictures it
    showed at the time — otherwise "what this turn offered" is a claim about
    today rather than about the turn.
    """
    collection = a_collection_holding(**{"Agnes Martin": ["Untitled No. 5"]})
    conversation_engine.suggested = (Suggestion(kind="artist", value="Agnes Martin"),)
    talking = ConversationService(discovery_store, conversation_engine, services.discovery, runner, collection=collection)
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")

    collection.holdings = {}

    assert [sample.title for _, samples in talking.get(conversation_id).turns[-1].suggested for sample in samples] == [
        "Untitled No. 5"
    ]


def test_a_deployment_that_browses_no_collection_still_names_things(talking):
    """Names without pictures, rather than a turn that fails over decoration."""
    view = talking.speak(talking.start().conversation.id, "Something calm.")

    assert [suggestion.value for suggestion, _ in view.turns[-1].suggested] == ["Agnes Martin"]
    assert all(samples == () for _, samples in view.turns[-1].suggested)


def test_committing_sets_the_run_on_the_committing_turn(talking, engine):
    """The seam, written on a turn the curator authored.

    Recorded as a turn rather than as a flag on the model's offer, so the
    transcript says what was committed, verbatim — and so a curator who reloads
    the page mid-search still sees the commit, because the thread itself carries
    it.
    """
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")

    view = talking.commit(conversation_id, "Agnes Martin")

    committed = view.turns[-1].turn
    assert committed.role is TurnRole.CURATOR
    assert committed.text == "Agnes Martin"
    assert committed.committed_run_id == view.committed_run_id
    assert engine.requests[-1].intent_text == "Agnes Martin"


def test_a_run_started_from_discover_has_no_committing_turn(talking, runner, discovery):
    """The other half of the seam's claim: it is set only where it happened."""
    from curation.persistence.discovery_records import InitiatedBy

    run = runner.start(intent_text="Something by Dalí", initiated_by=InitiatedBy.WEB_UI)

    assert discovery.get_run(run.id).id == run.id
    assert all(
        turn.committed_run_id != run.id
        for conversation in talking.list_conversations()
        for turn in [view.turn for view in talking.get(conversation.id).turns]
    )


def test_committing_spends_nothing_of_its_own(talking, discovery):
    """A commit starts a run, and the run's own spend is not the conversation's.

    The rows this produces are the *run's* — `discovery_tokens` and
    `web_search`, attributed to the run that incurred them. What must not appear
    is a second `conversation_tokens` row, because committing asks no model: the
    thread's cost is what talking cost, and a commit that billed under this
    category would put a run's phase-1 charge inside the intent-forming total.
    """
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")

    view = talking.commit(conversation_id, "Agnes Martin")

    records = discovery._store.list_spend_records()
    assert [record.category for record in records].count(SpendCategory.CONVERSATION_TOKENS) == 1
    assert {record.category for record in records} > {SpendCategory.CONVERSATION_TOKENS}
    # And the run's own rows attribute to the run, never to the committing turn.
    assert all(
        record.conversation_turn_id is None for record in records if record.category is not SpendCategory.CONVERSATION_TOKENS
    )
    assert all(record.discovery_run_id != view.committed_run_id for record in records if record.conversation_turn_id)


def test_starting_a_conversation_spends_nothing_and_asks_nothing(talking, conversation_engine, discovery):
    """A curator who opens one and thinks better of it has cost a row."""
    talking.start()

    assert conversation_engine.threads == []
    assert discovery._store.list_spend_records() == []


def test_turns_are_ordered_by_position_rather_than_by_the_clock(talking):
    """A question and the answer written in the same request share a second."""
    conversation_id = talking.start().conversation.id
    talking.speak(conversation_id, "Something calm.")
    talking.speak(conversation_id, "Anyone else?")

    assert [turn.turn.ordinal for turn in talking.get(conversation_id).turns] == [0, 1, 2, 3]


def test_the_list_is_ordered_by_the_last_thing_said(talking):
    """The thread a curator is looking for is the one they last spoke in."""
    first = talking.start().conversation.id
    second = talking.start().conversation.id
    talking.speak(first, "Something calm.")

    assert [conversation.id for conversation in talking.list_conversations()][0] == first
    assert second in {conversation.id for conversation in talking.list_conversations()}


def test_an_unknown_conversation_is_refused_by_name(talking):
    with pytest.raises(ServiceError, match="No conversation with id"):
        talking.get("not-a-conversation")
