"""The seam an intent-forming turn is answered through, and the types that cross it.

Beside `phase_one.py` rather than under it, and the distinction is the whole
point of this module existing. Phase 1 turns a settled intent into a list of
works and is the start of a run. A conversation turn sits **upstream** of that:
it answers from model knowledge, names artists or movements, and acquires
nothing. So the two share a provider, a client and a spend type, and share no
lifecycle at all — a conversation has no status to poll, nothing to approve, and
no work to cancel.

**The turns are fast precisely because they do no discovery**, which is what lets
one be served synchronously in a request the curator is watching. Measured
2026-08-12 against the live API: a warm turn answers in under a second, where a
run's phase 1 takes minutes.

**Reasoning is switched off, and the measurement is the argument.** On an
open-ended conversational prompt the routed model consumed its entire output
reservation on reasoning before emitting a character — ten calls in a row, at
reservations of 16, 200 and 900 tokens alike, every one returning empty content
and every one billed in full. `{"enabled": False}` produced a usable answer for a
twenty-seventh of the cost. The mat call fixed the same failure by raising the
reservation to 8,000; that works because a mat prompt is tightly specified and
its reasoning is bounded, and this evidence says an open question's is not.
"""

import json
import logging
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Final, Protocol, runtime_checkable

from curation.discovery.engine import EngineSpend
from curation.discovery.openrouter import Completion, KeyExhausted, Message, OpenRouterClient, OpenRouterError
from curation.persistence.discovery_records import SpendCategory, TurnRole

log = logging.getLogger(__name__)

#: The kinds a suggestion may name. The same closed set `Affinity.kind` uses,
#: because a suggestion is what an affinity would later be recorded *about* — a
#: second vocabulary here would mean the thing said and the thing remembered
#: could not be matched up.
SUGGESTION_KINDS: Final[tuple[str, ...]] = ("artist", "movement", "era", "subject", "medium", "palette")

#: What the provider is told the conversation is for. A standing instruction at
#: the head of the thread, which the API accepts (measured) and which is the one
#: place the product's own vocabulary is explained to a model that has none.
SYSTEM_PROMPT: Final[str] = (
    "You are helping one person decide what art to hang on a wall in their home. "
    "Answer from what you know: name real artists, movements, eras, subjects, media or palettes, "
    "and say briefly why each fits what they have described. Never claim to have searched anything, "
    "and never claim a particular museum holds a particular work — you have not looked. "
    "Keep every reply to at most three sentences, in plain language, addressed to them. "
    "List in `suggested` only the things you actually named in the reply."
)

#: The shape the answer must take. Enforced by the provider through
#: `response_format`, and parsed defensively regardless: a model may advertise
#: schema support, honour it, and stop honouring it.
REPLY_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reply", "suggested"],
    "properties": {
        "reply": {"type": "string", "description": "What to say to the curator. At most three sentences."},
        "suggested": {
            "type": "array",
            "description": "The artists, movements or subjects this reply named. Empty when it named none.",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["kind", "value"],
                "properties": {
                    "kind": {"type": "string", "enum": list(SUGGESTION_KINDS)},
                    "value": {"type": "string"},
                },
            },
        },
    },
}

#: What a deployment with no key is told when it tries to talk. Written for the
#: curator who reads it off a failed turn, and it names the one thing that fixes
#: it rather than the internals that noticed. Declared here rather than at the
#: entry point because the container needs the same sentence for its own default,
#: and two spellings of one refusal is one that drifts.
NO_CONVERSATION_KEY: Final[str] = (
    "This turn cannot be answered: the deployment has no OPENROUTER_API_KEY set, and forming an intent by "
    "conversation needs a model to answer with. Set it in .env — the spend ceiling is that key's own credit "
    "limit. Everything already said in this conversation is kept, and the question can be asked again once "
    "a key is configured."
)

#: Sent on every conversational call. See the module docstring for the ten empty,
#: fully-billed turns that made this a correctness value rather than a preference.
REASONING_OFF: Final[Mapping[str, Any]] = {"enabled": False}


@dataclass(frozen=True, slots=True)
class ThreadTurn:
    """One turn of the thread as the engine is given it, in the product's words.

    `role` is the product's `curator`/`system` pair; translating it into the
    provider's `user`/`assistant` happens below this seam, once. A role the
    provider does not know is a 400 — measured — so the translation being in one
    place is what stops a surface from inventing a third word.
    """

    role: TurnRole
    text: str


@dataclass(frozen=True, slots=True)
class Suggestion:
    """One thing a reply named.

    Deliberately not an `Affinity`: an engine says what it named, and whether the
    curator liked it is a separate fact recorded elsewhere by someone who asked
    them. `kind` is validated against the closed set above and an unknown one is
    dropped rather than stored, because a value no surface has words for is a
    diagnostic label waiting to appear on a screen.
    """

    kind: str
    value: str


@dataclass(frozen=True, slots=True)
class ConversationReply:
    """What one turn produced, and what producing it cost.

    `text` is never `None`. A truncated turn comes back from the provider as
    `content: null`, and a reply object that could carry that null would put it
    into the transcript — where the *next* turn resends it and is refused for a
    missing content field, a failure with nothing to do with why the first turn
    was cut off.

    `spend` is a sequence for the same reason phase 1's is, even though a
    conversational turn incurs exactly one charge today: the category split is a
    property of how the provider bills, not of this caller, and a turn that
    searched would carry two.
    """

    text: str
    spend: Sequence[EngineSpend] = ()
    suggested: Sequence[Suggestion] = ()
    model_id: str | None = None


class ConversationFailure(Exception):
    """A turn could not be answered.

    Carries whatever spend the failure travelled with, because a 2xx that could
    not be read was still billed — the same rule phase 1's `EngineFailure` states.
    A turn that failed **before** any 2xx carries nothing, and that distinction is
    what makes retrying safe: a request the provider never accepted cost nothing,
    so asking again does not double-spend.
    """

    def __init__(self, message: str, *, spend: Sequence[EngineSpend] = ()) -> None:
        super().__init__(message)
        self.spend = tuple(spend)


@runtime_checkable
class ConversationEngine(Protocol):
    """Answering one turn of an intent-forming thread, as the service sees it."""

    @property
    def unavailable_reason(self) -> str | None:
        """Why this engine cannot answer, or `None` when it can.

        The same shape phase 1's seam uses, and for the same reason: a deployment
        with no API key must still boot and serve everything else, and the
        refusal a curator reads has to name the thing that fixes it rather than
        describing whatever noticed.
        """

    def answer(self, thread: Sequence[ThreadTurn]) -> ConversationReply:
        """Answer the last turn of `thread`, with the rest of it as context.

        Raises `ConversationFailure` when no usable answer came back.
        """


@dataclass(frozen=True, slots=True)
class UnavailableConversation:
    """The engine a deployment with no key has: one that says why, honestly.

    Not a stand-in that answers. A convincing double reachable from a real
    deployment is one somebody eventually leaves wired, and an invented reply in a
    transcript is indistinguishable from a real one — the curator's evidence that
    the product works would be the product fabricating it.
    """

    reason: str

    @property
    def unavailable_reason(self) -> str | None:
        return self.reason

    def answer(self, thread: Sequence[ThreadTurn]) -> ConversationReply:
        raise ConversationFailure(self.reason)


@dataclass(frozen=True, slots=True)
class OpenRouterConversation:
    """An intent-forming turn, over a real provider, for real money."""

    client: OpenRouterClient
    #: How many turns of history travel with each question. **A cost dial, and
    #: the measurement says so**: the provider keeps no thread state, so every
    #: turn resends and is re-billed for everything before it — a thread's cost
    #: is superlinear in its length. Twelve is generous for a conversation whose
    #: job is to firm up one direction, and it bounds a tab left open all day.
    history_turns: int = 12

    @property
    def unavailable_reason(self) -> str | None:
        """Always available: a client cannot be constructed without a key."""
        return None

    def answer(self, thread: Sequence[ThreadTurn]) -> ConversationReply:
        """Ask once, pay once, and return the reply with its cost attached."""
        if not thread:
            raise ConversationFailure("A conversation turn needs something to answer.")
        # Nothing is recorded here about what was sent. That the whole history
        # travels is asserted at the transport, where a recording
        # `httpx.MockTransport` sees the real request body — a list on the engine
        # would be the same claim, weaker, and it would grow without bound in a
        # process that runs for months.
        messages = _wire(thread, history_turns=self.history_turns)
        try:
            completion = self.client.complete_thread(
                messages=messages,
                schema=REPLY_SCHEMA,
                schema_name="conversation_reply",
                reasoning=REASONING_OFF,
            )
        except KeyExhausted as exc:
            # No spend travels with this: the provider refuses before generating.
            # Named apart from every other failure because the answer is
            # different — retrying will refuse identically until the credit limit
            # resets or is raised.
            raise ConversationFailure(str(exc)) from exc
        except OpenRouterError as exc:
            raise ConversationFailure(str(exc)) from exc

        # From here the call has been billed, so every path out carries its
        # spend, including the parse failures. A turn that paid for an answer it
        # could not read still paid.
        spend = _spend_of(completion)
        reply, suggested = _read_reply(completion.content)
        if reply is None:
            raise ConversationFailure(
                f"The model returned no usable answer ({_why_it_stopped(completion)}). "
                "If it stopped on 'length', the reply was cut off and CONVERSATION_MAX_OUTPUT_TOKENS is too small.",
                spend=spend,
            )
        log.info(
            "a conversation turn was answered",
            extra={
                "event": "conversation.answered",
                "model_id": completion.model_id,
                "history_turns": len(messages),
                "suggested": len(suggested),
                "cost_usd": str(completion.cost_usd),
                "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens,
            },
        )
        return ConversationReply(text=reply, spend=spend, suggested=suggested, model_id=completion.model_id)


def _wire(thread: Sequence[ThreadTurn], *, history_turns: int) -> list[Message]:
    """The thread as the provider takes it: a standing instruction, then the turns.

    The tail is what travels, never the head — the last question is the one being
    answered, and dropping it to keep an old one would answer the wrong thing.
    """
    carried = list(thread)[-history_turns:] if history_turns > 0 else list(thread)[-1:]
    return [
        Message(role="system", text=SYSTEM_PROMPT),
        # A turn with nothing in it travels as the empty string, which is the
        # measured requirement: the provider refuses `content: null` — *"The
        # content field is a required field"* — and accepts `""`. Nothing on this
        # path can produce a null, because `ConversationTurn.text` is a `str` over
        # a `NOT NULL` column and the provider's own null is normalised where it
        # arrives, in `_read_completion`. So this is a statement of the invariant
        # rather than a second enforcement of it.
        *(Message(role=_PROVIDER_ROLE[turn.role], text=turn.text) for turn in carried),
    ]


#: The product's two words, in the provider's. The provider refuses anything else
#: — measured: *"curator is not one of ['system', 'assistant', 'user', 'tool',
#: 'function']"* — so this mapping is the entire translation and there is no other.
_PROVIDER_ROLE: Final[Mapping[TurnRole, str]] = {TurnRole.CURATOR: "user", TurnRole.SYSTEM: "assistant"}


def _spend_of(completion: Completion) -> tuple[EngineSpend, ...]:
    """The charge for one turn, as the row it becomes.

    One row, because no search plugin is sent: `usage.cost` and
    `cost_details.upstream_inference_cost` were equal on every measured
    conversational call, so `search_cost_usd` computes to zero and a `web_search`
    row would price a search nobody made. The whole charge is used rather than
    the inference share, so what the ledger holds is the figure the account was
    actually debited.
    """
    return (
        EngineSpend(
            category=SpendCategory.CONVERSATION_TOKENS,
            cost_usd=completion.cost_usd,
            model_id=completion.model_id,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        ),
    )


def _read_reply(content: str) -> tuple[str | None, tuple[Suggestion, ...]]:
    """The reply and what it named, or `None` when nothing usable came back.

    Parsed defensively even though the schema is enforced, for the reason phase 1
    parses defensively: a model may advertise structured output, honour it, and
    stop honouring it. A reply with unreadable suggestions is still a reply — the
    sentence is what the curator reads, and dropping it because a list beside it
    was malformed would lose the answer to keep the index.
    """
    if not content.strip():
        return None, ()
    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        # A truncated answer is well-formed right up to where it was cut, so it
        # arrives as a decode error rather than as prose. Reported as no usable
        # answer, which is what it is, with the finish reason naming the remedy.
        return None, ()
    if not isinstance(parsed, dict):
        return None, ()
    reply = parsed.get("reply")
    if not isinstance(reply, str) or not reply.strip():
        return None, ()
    return reply.strip(), _read_suggestions(parsed.get("suggested"))


def _read_suggestions(raw: object) -> tuple[Suggestion, ...]:
    """The things a reply named, dropping anything the product has no words for."""
    if not isinstance(raw, list):
        return ()
    found = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        kind = entry.get("kind")
        value = entry.get("value")
        if kind not in SUGGESTION_KINDS or not isinstance(value, str) or not value.strip():
            continue
        found.append(Suggestion(kind=str(kind), value=value.strip()))
    return tuple(found)


def _why_it_stopped(completion: Completion) -> str:
    """The finish reason in words, because it names which setting is wrong."""
    return f"the model stopped on {completion.finish_reason!r}" if completion.finish_reason else "no reason was given"


def build_conversation_engine(
    api_key: str,
    *,
    model: str,
    max_output_tokens: int,
) -> OpenRouterConversation:
    """The engine a real deployment uses, assembled from configuration.

    Its own client rather than discovery's, and its own model setting behind it:
    `DISCOVERY_MODEL` defaults to a text-only model — measured `input_modalities:
    ["text"]` — while a conversation may one day carry a picture the curator
    points at. The same argument `mat_model` already records.
    """
    return OpenRouterConversation(
        OpenRouterClient(api_key, model=model, max_output_tokens=max_output_tokens),
    )
