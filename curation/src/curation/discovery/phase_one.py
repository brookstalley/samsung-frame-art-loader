"""Phase 1: a curator's intent, one paid call, an enumerable list of works.

This is what sits behind the seam. It asks the model for *works* — titles and
artists — and never for images, which is phase 2's job and a different search
entirely.

**Every run searches the web.** A text-only call can only enumerate works the
model already knows, and asking for "recent award-winning art" without searching
returns a confident list of works from before the cutoff with nothing to mark it
as stale — measured, not supposed. Deciding per-intent whether to search was
considered and rejected: a trigger that guesses wrong fails silently, in the one
direction the product cannot detect, while searching always costs a flat fee per
run that is a rounding error against the monthly ceiling. Grounding a
non-recency intent is not waste either — it is what stops the model inventing a
plausible title.

**Breadth is free, so it is taken.** The fee is charged per search *request*, not
per result: one, three, five and ten results all bill identically. A deployment
that lowers the result count therefore saves nothing and sees less.

**One call is one search.** The search allowance is a bound on a run's fan-out,
and this engine spends one of it. The allowance travels in rather than being read
from configuration here, so the bound the run was authorised against is the bound
it runs under — and a deployment that sets it to zero gets a genuine text-only
run rather than a setting nothing honours.
"""

import json
import logging
from collections.abc import Mapping
from typing import Any, Final

from curation.discovery.engine import (
    BudgetExhausted,
    EngineFailure,
    EngineSpend,
    ProposedWork,
    WorkList,
    WorkListRequest,
)
from curation.discovery.openrouter import Completion, KeyExhausted, OpenRouterClient, OpenRouterError
from curation.persistence.discovery_records import SpendCategory

log = logging.getLogger(__name__)

#: The shape the provider is made to enforce. `strict` mode requires every
#: property to be listed as required, so `artist` is asked for as a string and an
#: empty one is read as "unattributed" — a schema that made it nullable would be
#: rejected before the call rather than after it.
WORK_LIST_SCHEMA: Final[Mapping[str, Any]] = {
    "type": "object",
    "properties": {
        "strategy": {
            "type": "string",
            "description": "One or two sentences on how the request was interpreted and what was searched for.",
        },
        "works": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "The work's title."},
                    "artist": {"type": "string", "description": "The artist's name, or an empty string if unknown."},
                    "rationale": {"type": "string", "description": "One sentence on why this work matches the request."},
                },
                "required": ["title", "artist", "rationale"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["strategy", "works"],
    "additionalProperties": False,
}

#: Deliberately not capped at a number of works. The approval gate exists to
#: catch a run that read an intent far more broadly than intended — "you asked
#: for Dalí and I found 200 works, really?" — and a prompt that quietly limited
#: the list to twenty would mean the gate could never fire and the judgement it
#: invites would never be asked for. The output reservation bounds the length
#: physically; the curator bounds it editorially.
PROMPT: Final[str] = """\
A curator is choosing art to show on a wall in their home. They have asked for:

{intent}

List the specific artworks that genuinely match this request. Name each work and
its artist — individual works, never collections, exhibitions or artists on their
own. Give one sentence for each on why it matches what was asked for.

If the request concerns anything recent, time-bound, or tied to a prize or event,
rely on the search results rather than on recollection, and prefer works you can
point to a source for.

Include only works you are confident actually exist. Do not pad the list to a
length: a short list of real works is worth more than a long one containing
plausible titles, because every work here will be shown to the curator to judge.
"""


class OpenRouterEngine:
    """Phase 1, over a real provider, for real money."""

    def __init__(self, client: OpenRouterClient, *, search_results: int) -> None:
        self._client = client
        self._search_results = search_results

    @property
    def unavailable_reason(self) -> str | None:
        """Always available: a client cannot be constructed without a key."""
        return None

    @property
    def model(self) -> str:
        """Which model this engine spends on, for saying so without calling it."""
        return self._client.model

    def enumerate_works(self, request: WorkListRequest) -> WorkList:
        """Ask once, pay once, and return what came back with its cost attached."""
        searching = request.search_allowance > 0
        try:
            completion = self._client.complete(
                prompt=PROMPT.format(intent=request.intent_text.strip()),
                schema=WORK_LIST_SCHEMA,
                search_results=self._search_results if searching else 0,
            )
        except KeyExhausted as exc:
            # No spend travels with this: the provider refuses before generating,
            # so there is nothing to record. Reported as exhaustion specifically,
            # which is the one failure whose answer is to stop rather than retry.
            raise BudgetExhausted(str(exc)) from exc
        except OpenRouterError as exc:
            raise EngineFailure(str(exc)) from exc

        # From here the call has been billed, so every path out carries its
        # spend — including the parsing failures below. A run that paid for an
        # answer it could not read still paid.
        spend = _spend_of(completion)
        if not completion.content.strip():
            # Usually the output reservation being reached before anything was
            # emitted. Named rather than reported as a bare parse failure,
            # because `DISCOVERY_MAX_OUTPUT_TOKENS` is the setting that fixes it.
            because = (
                f"the model stopped on {completion.finish_reason!r}"
                if completion.finish_reason
                else "the provider gave no reason"
            )
            raise EngineFailure(
                f"Phase 1 returned an empty answer ({because}). If it stopped on 'length', the output "
                "reservation is too small for a work list of this size.",
                spend=spend,
            )
        try:
            parsed = json.loads(completion.content)
        except json.JSONDecodeError as exc:
            raise EngineFailure(f"Phase 1's answer was not the JSON its schema required: {exc}", spend=spend) from exc
        if not isinstance(parsed, dict):
            raise EngineFailure(f"Phase 1 answered with {type(parsed).__name__}, not an object.", spend=spend)

        works = _read_works(parsed.get("works"))
        log.info(
            "phase 1 called the model",
            extra={
                "event": "engine.completed",
                "model_id": completion.model_id,
                "searched": completion.searched,
                "citations": len(completion.citations),
                "works_returned": len(works),
                "cost_usd": str(completion.cost_usd),
                "input_tokens": completion.input_tokens,
                "output_tokens": completion.output_tokens,
            },
        )
        return WorkList(works=works, spend=spend, strategy=_read_strategy(parsed.get("strategy")))


def _spend_of(completion: Completion) -> tuple[EngineSpend, ...]:
    """Split one charge into the categories that are billed differently.

    The two rows sum to exactly what the provider said the call cost, because
    the search share is derived by subtraction from that same total rather than
    priced locally. A search fee computed from a configured rate would be a
    second opinion about a number the account has already been debited for.

    The search row is written only when a search actually ran, and its `units` is
    one: the fee is per request, and this engine makes one request. That count is
    what the run's cap is read from, so it comes from the same record that prices
    it rather than from a separate tally free to disagree.
    """
    rows = [
        EngineSpend(
            category=SpendCategory.DISCOVERY_TOKENS,
            cost_usd=completion.inference_cost_usd,
            model_id=completion.model_id,
            input_tokens=completion.input_tokens,
            output_tokens=completion.output_tokens,
        )
    ]
    if completion.searched:
        rows.append(
            EngineSpend(
                category=SpendCategory.WEB_SEARCH,
                cost_usd=completion.search_cost_usd,
                model_id=completion.model_id,
                units=1,
            )
        )
    return tuple(rows)


def _read_works(raw: object) -> tuple[ProposedWork, ...]:
    """Turn the answer's work entries into proposals, dropping what is unusable.

    An entry with no title or no rationale is dropped rather than failing the
    run. The record layer refuses both, so passing one through would throw away
    a whole list of good works over one malformed row — but each drop is logged,
    because a run that proposed twelve works from an answer naming thirteen is a
    discrepancy somebody should be able to account for.
    """
    if not isinstance(raw, list):
        return ()
    works = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        rationale = str(entry.get("rationale") or "").strip()
        artist = str(entry.get("artist") or "").strip()
        if not title or not rationale:
            log.warning(
                "dropping a proposed work that cannot be recorded",
                extra={"event": "engine.work_dropped", "work_title": title, "has_rationale": bool(rationale)},
            )
            continue
        works.append(ProposedWork(title=title, rationale=rationale, artist=artist or None))
    return tuple(works)


def _read_strategy(raw: object) -> str | None:
    """The interpretation, or nothing — never an empty string standing in for one."""
    if not isinstance(raw, str):
        return None
    return raw.strip() or None


def build_engine(api_key: str, *, model: str, max_output_tokens: int, search_results: int) -> OpenRouterEngine:
    """The engine a deployment holding an API key gets.

    A function rather than construction at the call site so the wiring reads as
    one decision — a key buys a working engine — and so the client stays an
    implementation detail of this module rather than something every entry point
    has to know how to assemble.
    """
    return OpenRouterEngine(
        OpenRouterClient(api_key, model=model, max_output_tokens=max_output_tokens),
        search_results=search_results,
    )
