"""Intent-forming: the thread, the turns, and the seam onto a run.

**A conversation is upstream of a run and is never one.** It answers from model
knowledge, shows a few sample pictures, acquires nothing, writes no `Artwork` and
reaches no museum API to resolve anything. That is what keeps the fast turns
fast, and it is why a run started from here is still a batch with a knowable
scope — the conversation did none of the discovery.

**Every model turn writes its own spend row, in the same call that spends it.**
`conversation_tokens` exists because intent-forming costs real money and the
month total has to include it; a route that spent without writing the row would
put a whole paid path outside the only figure anyone reconciles. The row carries
`conversation_turn_id` and never a run id, even after the conversation seeds one.

**Two foreign services are reached through narrow protocols, not by holding
them.** Recording spend lives on `DiscoveryService` and starting a run lives on
`DiscoveryRunner`, and this service needs one method from each. Taking the whole
of either would deepen a coupling already filed for removal — the accounting
split the mat path is the second caller for — so what is depended on here is
`records spend` and `starts a run`, which is all this is about and all the split
would have to preserve.

**Sample pictures cost nothing, and that is a design constraint rather than a
happy accident.** They come from the collection the product already browses, by
artist, over an open museum API — the same free seam a run supplements from. So
the whole price of a turn is its model call, and `conversation_tokens` is the
only category intent-forming can produce.
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Protocol

from curation.discovery.browse import BrowseQuery, CollectionBrowse, CollectionBrowseFailure
from curation.discovery.conversation import ConversationEngine, ConversationFailure, Suggestion, ThreadTurn
from curation.discovery.engine import EngineSpend
from curation.persistence.discovery import DiscoveryStore
from curation.persistence.discovery_records import (
    Conversation,
    ConversationTurn,
    DiscoveryRun,
    InitiatedBy,
    SpendCategory,
    SpendRecord,
    TurnRole,
)
from curation.services.errors import ServiceError
from curation.services.fields import require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)

#: How many sample pictures one suggested artist contributes to a turn.
#:
#: Three, and the number is about the thread rather than about the collection: a
#: turn naming four artists already puts a dozen pictures in front of a curator
#: who asked a question, and the samples are there to make a name concrete rather
#: than to be browsed. The collection's own total is not reported beside them for
#: the same reason — this is not an offer of works, and a count would read as one.
SAMPLES_PER_SUGGESTION: int = 3

#: How many suggested artists a single turn looks up.
#:
#: The lookup is free, so the bound is a bound on the *reading*: a reply that
#: named nine artists would otherwise become a page of pictures with a sentence
#: on top of it. The first few are the ones the reply led with.
SUGGESTIONS_SAMPLED: int = 3

#: The kind a sample lookup can serve. The collection is browsed by artist and by
#: nothing else — widening past artist adjacency is gated on a measurement that
#: has not been made, so a `movement` suggestion is named in the transcript and
#: simply carries no pictures, rather than being answered with an artist's.
SAMPLED_KIND: str = "artist"


class SpendWriter(Protocol):
    """Whatever records what something cost. One method, deliberately."""

    def record_spend(
        self,
        *,
        category: SpendCategory,
        cost_usd: Decimal,
        conversation_turn_id: str | None = None,
        model_id: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> SpendRecord:
        """Write one spend row and return it."""


class RunStarter(Protocol):
    """Whatever begins a discovery run behind a handle. One method, deliberately."""

    def start(self, *, intent_text: str, initiated_by: InitiatedBy) -> DiscoveryRun:
        """Begin a run and return its handle at once."""


@dataclass(frozen=True, slots=True)
class Sample:
    """One picture shown beside a name, to make the name concrete.

    **Not a `CandidateWork` and not on its way to becoming one.** Nothing here is
    proposed, judged or acquired: it is the collection's own record of a work it
    holds by an artist the reply named, shown so a curator can see what the name
    means. `image_url` is the collection's preview address, rendered by the
    browser directly — a conversation caches no files, because a sample nobody
    chose is not a preview of anything and reclaiming it would need a sweep for
    pictures that were never candidates.
    """

    title: str
    artist: str | None
    image_url: str | None


@dataclass(frozen=True, slots=True)
class TurnView:
    """One turn as a surface renders it: what was said, and what it offered."""

    turn: ConversationTurn
    #: `(suggestion, samples)` pairs, in the order the reply named them. Read
    #: back off the stored turn rather than looked up again, because the record
    #: is of *what was said* — a thread re-read next month must show the pictures
    #: it showed at the time, not whatever the collection would answer today.
    suggested: Sequence[tuple[Suggestion, Sequence[Sample]]] = ()


@dataclass(frozen=True, slots=True)
class ConversationView:
    """A whole thread, and whatever is outstanding on it.

    `unanswered` is derived rather than stored, and that is the design of the
    retryable failed turn: a thread whose last turn is the curator's is one whose
    question has not been answered, whether the model refused, was cut off, or
    could not be reached at all. Nothing has to be written to record a failure,
    so nothing can be written *wrongly* — and after a reload the state is still
    exactly what the transcript says it is.

    `failure` is the account of why the most recent attempt did not answer, and
    it lives only on the response to that attempt. It is a fact about a call
    rather than about the thread, and a transcript that kept it would be
    reporting a provider's transient complaint as part of the conversation.
    """

    conversation: Conversation
    turns: Sequence[TurnView]
    failure: str | None = None

    @property
    def unanswered(self) -> ConversationTurn | None:
        """The curator's turn that is still waiting, or `None`."""
        last = self.turns[-1].turn if self.turns else None
        return last if last is not None and last.role is TurnRole.CURATOR and last.committed_run_id is None else None

    @property
    def committed_run_id(self) -> str | None:
        """The run this conversation seeded, if it has seeded one.

        The most recent, because a curator may commit a second direction from the
        same thread and the card at the bottom is about the last thing they did.
        """
        for view in reversed(self.turns):
            if view.turn.committed_run_id is not None:
                return view.turn.committed_run_id
        return None


class ConversationService:
    """Threads, turns, and the one edge from intent-forming onto a run."""

    def __init__(
        self,
        store: DiscoveryStore,
        engine: ConversationEngine,
        spend: SpendWriter,
        runs: RunStarter,
        *,
        collection: CollectionBrowse | None = None,
    ) -> None:
        self._store = store
        self._engine = engine
        self._spend = spend
        self._runs = runs
        #: `None` is a deployment that has not named itself to the museum, and it
        #: is a supported one: the conversation still answers, and the names it
        #: gives simply carry no pictures. The same gate phase 2 and the run's
        #: supplement are behind, for the same reason — a collection that asks
        #: callers to identify themselves is not browsed anonymously.
        self._collection = collection

    # -- reads ----------------------------------------------------------------

    def list_conversations(self) -> Sequence[Conversation]:
        """Every conversation, the most recently spoken in first."""
        return self._store.list_conversations()

    def get(self, conversation_id: str) -> ConversationView:
        """One whole thread, in reading order."""
        conversation = self._store.get_conversation(conversation_id)
        if conversation is None:
            raise ServiceError(f"No conversation with id {conversation_id!r}.")
        turns = self._store.list_conversation_turns(conversation_id)
        return ConversationView(conversation=conversation, turns=tuple(_view(turn) for turn in turns))

    # -- writes ---------------------------------------------------------------

    def start(self) -> ConversationView:
        """Open an empty thread.

        Empty rather than opened with a first question, so that starting one
        spends nothing: a curator who opens a conversation and thinks better of
        it has cost the household a row. The first turn is `speak`, like every
        other.
        """
        now = datetime.now(UTC)
        conversation = Conversation(id=str(uuid.uuid4()), started_at=now, last_turn_at=now)
        store_write(self._store.add_conversation, conversation)
        log.info("a conversation was started", extra={"event": "conversation.started", "conversation_id": conversation.id})
        return ConversationView(conversation=conversation, turns=())

    def speak(self, conversation_id: str, text: str | None = None) -> ConversationView:
        """Ask something, or ask again for the answer to the last thing asked.

        **Retrying is asking for the answer, never re-sending the question**, and
        that is what keeps a spend-triggering POST safe to press twice. With no
        `text` this answers the turn already standing unanswered at the end of the
        thread; a thread whose last turn was answered has nothing to retry and is
        told so, which is precisely the case where the model was billed and the
        response was lost on the way back to the browser. So the double-spend
        window is closed by the transcript itself rather than by an idempotency
        key the client would have to remember to send.

        The failure is returned rather than raised. A refusal that travelled as an
        error would take the curator's question with it — the client would show a
        sentence and no thread — and the requirement is that a failed turn *stays*
        in the thread and is retryable.
        """
        view = self.get(conversation_id)
        if text is None or not text.strip():
            asking = view.unanswered
            if asking is None:
                raise ServiceError(
                    "There is nothing to retry: the last turn in this conversation was answered. "
                    "Send some text to ask something new."
                )
        else:
            asking = self._append(view, role=TurnRole.CURATOR, text=require_text(text, field="text"))
            view = self.get(conversation_id)

        unavailable = self._engine.unavailable_reason
        if unavailable is not None:
            return _with_failure(view, unavailable)
        try:
            reply = self._engine.answer([ThreadTurn(role=turn.turn.role, text=turn.turn.text) for turn in view.turns])
        except ConversationFailure as exc:
            # The spend still lands. A 2xx that could not be read was billed, and
            # a month total that omitted exactly the failures would under-report
            # by what they cost — the failure this ledger exists to prevent. The
            # curator's turn is what it attributes to, because that is the turn
            # that was paid for.
            self._record(exc.spend, turn_id=asking.id)
            log.info(
                "a conversation turn could not be answered",
                extra={"event": "conversation.failed", "conversation_id": conversation_id, "detail": str(exc)},
            )
            return _with_failure(view, str(exc))

        answered = self._append(view, role=TurnRole.SYSTEM, text=reply.text, suggested=self._offer(reply.suggested))
        self._record(reply.spend, turn_id=answered.id)
        return self.get(conversation_id)

    def commit(self, conversation_id: str, intent: str) -> ConversationView:
        """Seed a discovery run from this thread, without ending it.

        The commit is written as the curator's own turn carrying
        `committed_run_id` — the seam — rather than as a flag on the model's
        offer. Two things follow, and both are wanted: the transcript records
        what was actually committed, verbatim, and a curator who reloads the page
        mid-run still sees the commit and its progress, because the thread itself
        says a run was started from here.

        Nothing is spent by committing. The run prices itself, and its spend is
        the run's — conversation spend and run spend answer different questions.
        """
        view = self.get(conversation_id)
        wanted = require_text(intent, field="intent")
        # Started before the turn is written rather than after, so that a run the
        # runner refuses — no key, an engine that cannot run — leaves no turn
        # claiming a commit that never happened.
        run = self._runs.start(intent_text=wanted, initiated_by=InitiatedBy.WEB_UI)
        self._append(view, role=TurnRole.CURATOR, text=wanted, committed_run_id=run.id)
        log.info(
            "a conversation seeded a run",
            extra={"event": "conversation.committed", "conversation_id": conversation_id, "run_id": run.id},
        )
        return self.get(conversation_id)

    # -- internals ------------------------------------------------------------

    def _append(
        self,
        view: ConversationView,
        *,
        role: TurnRole,
        text: str,
        suggested: Sequence[Mapping[str, Any]] | None = None,
        committed_run_id: str | None = None,
    ) -> ConversationTurn:
        """Write one turn at the end of the thread and move the conversation's clock."""
        now = datetime.now(UTC)
        turn = ConversationTurn(
            id=str(uuid.uuid4()),
            conversation_id=view.conversation.id,
            # Derived from the thread rather than counted separately: the
            # position and the rows have to agree, and a counter stored beside
            # them is a second answer free to drift from the first.
            ordinal=len(view.turns),
            role=role,
            # A `str` on every path, and the column is `NOT NULL`. The null this
            # product has to normalise is the provider's — a truncated turn comes
            # back as `content: null` — and it is normalised where it arrives, in
            # `_read_completion`. A second guard here would be untestable by
            # construction, which is exactly what a mutation sweep flags.
            text=text,
            created_at=now,
            suggested=suggested,
            committed_run_id=committed_run_id,
        )
        with self._store.transaction():
            store_write(self._store.add_conversation_turn, turn)
            store_write(self._store.update_conversation, _touched(view.conversation, now))
        return turn

    def _record(self, spend: Sequence[EngineSpend], *, turn_id: str) -> None:
        """Write what a turn cost, attributed to the turn rather than to any run."""
        for entry in spend:
            self._spend.record_spend(
                category=entry.category,
                cost_usd=entry.cost_usd,
                conversation_turn_id=turn_id,
                model_id=entry.model_id,
                input_tokens=entry.input_tokens,
                output_tokens=entry.output_tokens,
            )

    def _offer(self, suggested: Sequence[Suggestion]) -> list[dict[str, Any]] | None:
        """What a reply named, with a few pictures each where the collection has them.

        Frozen into the turn rather than looked up on every read. The record is of
        what was said, and a thread re-read next month showing different pictures
        would be a live index wearing a transcript's clothes.
        """
        if not suggested:
            return None
        samples = self._samples([entry.value for entry in suggested if entry.kind == SAMPLED_KIND][:SUGGESTIONS_SAMPLED])
        return [
            {
                "kind": entry.kind,
                "value": entry.value,
                "samples": [
                    {"title": sample.title, "artist": sample.artist, "image_url": sample.image_url}
                    for sample in samples.get(entry.value, ())
                ],
            }
            for entry in suggested
        ]

    def _samples(self, artists: Sequence[str]) -> Mapping[str, Sequence[Sample]]:
        """A few works per artist, out of the collection, or nothing at all.

        A collection that cannot be asked yields no samples and no failure. The
        pictures illustrate a name the curator already has; losing them costs a
        turn its decoration, and failing the turn over it would cost them the
        answer they paid for.
        """
        if self._collection is None or not artists:
            return {}
        try:
            groups = self._collection.browse([BrowseQuery(artist=artist) for artist in artists], per_query=SAMPLES_PER_SUGGESTION)
        except CollectionBrowseFailure as exc:
            log.info("no sample pictures for this turn: the collection could not be browsed: %s", exc)
            return {}
        return {
            group.query.artist: [Sample(title=work.title, artist=work.artist, image_url=work.preview_url) for work in group.works]
            for group in groups
        }


def _touched(conversation: Conversation, now: datetime) -> Conversation:
    """The conversation with its ordering clock moved to the turn just written."""
    return Conversation(
        id=conversation.id,
        started_at=conversation.started_at,
        last_turn_at=now,
        summary=conversation.summary,
    )


def _with_failure(view: ConversationView, failure: str) -> ConversationView:
    return ConversationView(conversation=view.conversation, turns=view.turns, failure=failure)


def _view(turn: ConversationTurn) -> TurnView:
    """A stored turn as a surface reads it, with its suggestions unpacked.

    Anything unreadable in `suggested` is dropped rather than raised on. The
    column holds JSON written by an earlier version of this code, and a
    transcript that refused to render because one turn's index has an unexpected
    shape would lose the conversation to keep the decoration.
    """
    if not turn.suggested:
        return TurnView(turn=turn)
    offered = []
    for entry in turn.suggested:
        if not isinstance(entry, Mapping):
            continue
        kind, value = entry.get("kind"), entry.get("value")
        if not isinstance(kind, str) or not isinstance(value, str):
            continue
        samples = entry.get("samples")
        offered.append(
            (
                Suggestion(kind=kind, value=value),
                tuple(_sample(sample) for sample in samples if isinstance(sample, Mapping)) if isinstance(samples, list) else (),
            )
        )
    return TurnView(turn=turn, suggested=tuple(offered))


def _sample(entry: Mapping[str, Any]) -> Sample:
    return Sample(
        title=str(entry.get("title") or ""),
        artist=entry.get("artist"),
        image_url=entry.get("image_url"),
    )
