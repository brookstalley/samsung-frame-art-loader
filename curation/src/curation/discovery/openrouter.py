"""The OpenRouter client discovery's paid work actually goes through.

One provider, one account, one narrow surface: a chat completion that may carry
a web search, and a reading of the key's own credit limit. Nothing here knows
what a discovery run is — it turns a request into a response and reports what
that cost, which is what keeps the engine above it testable without a network.

**The client is first-party rather than a framework's chat model.** Everything
this product pays for routes through this one provider, so a multi-provider
abstraction would carry no traffic while pulling a large dependency tree onto a
memory-capped Pi. The seam above makes that reversible: adopting a framework
later is one module's work, not a rewrite of everything that calls it.

**Money is `Decimal` from the moment it is parsed, never `float`.** The response
body is JSON, and a cost like `0.00523535` read as a binary float is already
wrong by the time anyone adds it up. `json.loads(..., parse_float=Decimal)`
converts at the tokeniser, before a float ever exists.

**Two refusals mean opposite things, and collapsing them would be a bug with a
bill attached.** Measured against the live API rather than assumed:

- **403** is exhaustion — the key's credit limit is spent. Stop.
- **402** is a *pre-flight affordability check*, and it arrives with credit still
  in the account: the provider reserves the maximum output the request could
  produce and declines when that reservation exceeds what remains. Ask for less
  and continue.

That is why `max_output_tokens` is a deliberate value and not a tuning knob. Left
unset, the reservation becomes the model's own maximum, so a nearly empty key
refuses everything and a well-funded one refuses expensive models — at full
credit, with nothing generated and nothing spent.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Final

import httpx

#: Where the provider lives. Not a deployment value: this client is written to
#: one provider's measured response shapes, so a different base URL would be a
#: different API wearing this one's parser.
BASE_URL: Final[str] = "https://openrouter.ai/api/v1"

#: How long one completion may take. Generous, because a call carrying a web
#: search does the searching before it starts generating, and this runs on a
#: worker thread behind an already-returned run handle — nothing is waiting on
#: it. Short enough that a hung connection ends as a failed run rather than a
#: thread parked forever.
COMPLETION_TIMEOUT_SECONDS: Final[float] = 180.0

#: How long the key endpoint may take. Short: it backs a display figure, and a
#: budget readout that hangs is worse than one that says it could not be read.
KEY_TIMEOUT_SECONDS: Final[float] = 15.0

#: How long **one connection attempt** may take, as opposed to the whole request.
#:
#: **Not a subdivision of the budgets above, and the distinction is the point.**
#: Those bound *generation*, which legitimately takes minutes; opening a socket to
#: a host that is going to answer takes milliseconds. Handing httpx a single
#: number sets both, which is what makes an unreachable address cost a whole
#: completion budget.
#:
#: **It exists because httpx has no Happy Eyeballs.** Its transport walks the
#: addresses `getaddrinfo` returns in order, and this provider publishes AAAA
#: records — so on a network whose IPv6 path is black-holed, every connection
#: begins with an attempt that will never be answered, and only then falls back to
#: IPv4. Measured 2026-08-12 on such a network: ~150 seconds per connection
#: against 0.02 seconds over IPv4, and httpx's keepalive expires after five
#: seconds, so anything slower than a tight loop pays it on every single call. A
#: browser on the same network falls back in about 250 milliseconds.
#:
#: **The measurement above is no longer reproducible from here, and the constant
#: stays.** The operator disabled IPv6 at the router on 2026-08-12, after the fix
#: landed, so a cold connection on this network now opens over IPv4 in
#: milliseconds. That is a change to one network, not to httpx: the next one that
#: advertises a black-holed prefix — a hotel, a phone hotspot, the ISP again —
#: brings the whole 150 seconds back. Read a fast cold connect as the router doing
#: its job, not as evidence this bound is dead weight.
#:
#: Five seconds is generous for a reachable host on a slow link and short enough
#: that walking a dead address family is an inconvenience rather than an outage.
#: The right long-term answer is a transport that races the two families; this is
#: the one-value version of it, and it works without depending on any network
#: being correctly configured.
CONNECT_TIMEOUT_SECONDS: Final[float] = 5.0


class OpenRouterError(Exception):
    """The provider could not be made to answer."""


class KeyExhausted(OpenRouterError):
    """The key's credit limit is spent — HTTP 403.

    Its own type because the correct response is unique: stop until the limit
    resets or is raised. Every other failure is worth retrying; this one will
    fail identically until somebody changes something outside this product.
    """


class RequestUnaffordable(OpenRouterError):
    """The reserved output costs more than the credit remaining — HTTP 402.

    **Not exhaustion.** It arrives with money in the account, nothing generated
    and nothing spent, because the provider prices the reservation rather than
    the result. Treating it as exhaustion would halt runs that can still pay;
    the answer is a smaller `max_output_tokens`.
    """


@dataclass(frozen=True, slots=True)
class Citation:
    """One page a search returned, and the excerpt the model was given.

    `content` is what makes a discovered work traceable to a page rather than to
    the model's assertion, which is the difference between a citation and a
    claim that one exists.
    """

    url: str
    title: str
    content: str


@dataclass(frozen=True, slots=True)
class ImageAttachment:
    """An image to ask the model about, already encoded and sized.

    Carries bytes rather than a path or a URL for two reasons. A path would put
    file reading and downscaling behind a transport, where a caller could not see
    what it was about to pay for — the encoded size *is* the input token count.
    A URL would have the provider fetch it, which for a museum's server means an
    unannounced third party pulling a gigapixel master.
    """

    #: Base64 of the encoded image, without any data-URI preamble.
    base64_data: str
    #: The media type of what `base64_data` decodes to, e.g. `image/jpeg`.
    media_type: str

    @property
    def data_uri(self) -> str:
        """The `data:` URI form the provider's `image_url` part expects."""
        return f"data:{self.media_type};base64,{self.base64_data}"


@dataclass(frozen=True, slots=True)
class Message:
    """One turn of a thread, in the provider's vocabulary rather than the product's.

    `role` is `"system"`, `"user"` or `"assistant"` — the names the API accepts,
    and deliberately not the product's `curator`/`system` pair. Measured: a role
    of `"curator"` is a 400 reading *"curator is not one of ['system',
    'assistant', 'user', 'tool', 'function']"*, so the translation happens above
    this seam or it happens at the provider's expense.

    **`text` is a string and never `None`, and that is the load-bearing part.**
    A truncated turn comes back with `content: null`, and feeding that object
    straight back into the next request is refused — *"The content field is a
    required field"* — while `content: ""` is accepted and answered normally.
    Both measured, twice, on 2026-08-12. A caller that stored the provider's
    message object untouched would therefore poison the thread one turn later,
    which is why nothing here can express a null.

    **An image may only ride a `user` turn.** An `image_url` part on an assistant
    turn is a 400: *"An incorrect modal `image` was entered … or was placed in
    the wrong position (e.g., in system/assistant)"*. Refused below, where the
    mistake is made, rather than by the provider a network round trip later.
    """

    role: str
    text: str
    image: ImageAttachment | None = None

    def __post_init__(self) -> None:
        if self.role not in _ROLES:
            raise ValueError(f"A message role is one of {sorted(_ROLES)}, got {self.role!r}.")
        if self.image is not None and self.role != "user":
            raise ValueError(
                f"An image may only travel on a user turn, not on a {self.role!r} one. Measured against the live "
                "API: the provider refuses an image part in a system or assistant message. A sample the model "
                "should look at again rides the curator's next turn."
            )

    def wire(self) -> dict[str, Any]:
        """This turn as the request body carries it."""
        if self.image is None:
            # A bare string rather than a one-element part list. Both are
            # accepted; this is the shape every capture of a text-only turn
            # holds, and matching what was measured is what makes the fakes
            # built from those captures mean anything.
            return {"role": self.role, "content": self.text}
        return {
            "role": self.role,
            "content": [
                {"type": "text", "text": self.text},
                {"type": "image_url", "image_url": {"url": self.image.data_uri}},
            ],
        }


#: The roles the provider accepts, quoted from its own refusal of one it does not.
_ROLES: Final[frozenset[str]] = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True, slots=True)
class Completion:
    """What one call produced, and what it cost in the provider's own terms.

    `cost_usd` is the provider's own figure for the whole call and is
    authoritative — it already includes any search fee, which a total computed
    from tokens and a price table would silently omit. `inference_cost_usd` is
    the token-priced portion, so the remainder is what searching cost; splitting
    it that way means the two attributed categories always sum back to the one
    number the account was actually debited.
    """

    content: str
    model_id: str
    cost_usd: Decimal
    inference_cost_usd: Decimal
    input_tokens: int
    output_tokens: int
    citations: tuple[Citation, ...] = ()
    #: Why the model stopped — `"stop"`, `"length"`, whatever the provider says.
    #: Carried so a caller judging an unusable answer can explain it, rather than
    #: reporting an empty result with no account of how it got that way.
    finish_reason: str | None = None

    @property
    def searched(self) -> bool:
        """Whether a search actually ran, from the citations rather than the cost.

        The provider returns annotations when it searched and omits them when it
        did not, which is a direct signal. Inferring it from a non-zero fee would
        be reading the bill to find out what was bought.
        """
        return bool(self.citations)

    @property
    def search_cost_usd(self) -> Decimal:
        """What the searching cost: the whole charge less its token-priced part.

        Never negative. A provider or route that reports the two in a way this
        subtraction does not fit would otherwise produce a negative spend row,
        and an ungrounded credit is a worse answer than attributing the lot to
        tokens.
        """
        return max(self.cost_usd - self.inference_cost_usd, Decimal(0))


@dataclass(frozen=True, slots=True)
class KeyStatus:
    """The account's own view of the ceiling.

    **Display only, and the reason is measured.** `/key` lags by minutes: while
    live calls were already being refused as limit-exceeded, it still reported
    credit remaining. A run that gated on this would be deciding from a number
    that does not yet include the calls it just made — which is precisely the
    silent failure the provider-side ceiling exists to rule out.
    """

    limit_usd: Decimal | None
    usage_usd: Decimal
    remaining_usd: Decimal | None
    resets: str | None


class OpenRouterClient:
    """Chat completions and the key's credit standing, over one HTTP session."""

    def __init__(
        self,
        api_key: str,
        *,
        model: str,
        max_output_tokens: int,
        search_engine: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("An OpenRouter client needs an API key.")
        if max_output_tokens <= 0:
            raise ValueError(
                f"max_output_tokens must be positive, got {max_output_tokens}. It is the output reservation the "
                "provider prices before it will accept a request, so there is no meaningful zero."
            )
        self._model = model
        self._max_output_tokens = max_output_tokens
        # Not validated against a list of known engines, deliberately. The
        # provider is the authority on which engines exist, and a local allowlist
        # is a second answer that drifts the moment one is added — the same
        # reasoning that keeps the spend ceiling on the provider's side. An
        # unknown value is refused by the provider with its own message, which is
        # a better error than one written here from a stale list.
        self._search_engine = search_engine
        # Injectable so the suite can drive a recorded transport instead of the
        # network. The default is a real session; nothing else in the package
        # constructs one. No `base_url` on it: every request below builds its
        # full URL, and a base that half the code ignored would be a second
        # answer to where the provider lives.
        self._http = client or httpx.Client()
        self._headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    @property
    def model(self) -> str:
        """Which model this client calls, for attributing spend to what spent it."""
        return self._model

    @property
    def search_engine(self) -> str | None:
        """Which search back-end this client pins, or `None` to take the default.

        Exposed for the same reason as `model`: a measurement of search quality
        has to be able to say what it measured. `None` is not "no search" — it is
        the provider's own default, which resolves to the *model provider's*
        native search where one exists and falls back to Exa where it does not.
        That makes the engine an emergent consequence of the model rather than a
        decision, so anything comparing engines has to pin one.
        """
        return self._search_engine

    def complete(
        self,
        *,
        prompt: str,
        schema: Mapping[str, Any] | None = None,
        search_results: int = 0,
        image: ImageAttachment | None = None,
    ) -> Completion:
        """Ask the model once, optionally about an image, optionally searching first.

        `search_results` is how many pages a search may return, and zero means
        do not search at all. It is *not* a count of searches: one call carries
        one search, and the number of results it brings back is free — the fee
        is per request, measured flat across one, three, five and ten results.
        So breadth costs nothing and is worth asking for.

        A `schema` makes the provider enforce the response shape, which is what
        lets the engine above parse without defending against prose. **Enforce is
        the intent, not the guarantee** — a model may advertise `response_format`
        without `structured_outputs`, honour the schema anyway, and remain free to
        stop honouring it. Callers parse defensively regardless.

        `image` turns the message into a list of content parts. Measured against
        the live API: nothing else about the request or the response changes —
        same choices, same `usage.cost`, same `finish_reason` — and the image
        bills inside `prompt_tokens` rather than as a separate charge.
        """
        return self.complete_thread(
            messages=[Message(role="user", text=prompt, image=image)],
            schema=schema,
            search_results=search_results,
        )

    def complete_thread(
        self,
        *,
        messages: Sequence[Message],
        schema: Mapping[str, Any] | None = None,
        schema_name: str = "work_list",
        search_results: int = 0,
        reasoning: Mapping[str, Any] | None = None,
    ) -> Completion:
        """Ask the model with a history behind the question.

        **The provider keeps no thread state.** Measured 2026-08-12 over twelve
        multi-turn calls: there is no thread id and no `previous_response_id`, so
        every turn resends the whole conversation and is billed for it. An image
        left in the history is re-sent, re-billed and genuinely re-read — 434
        prompt tokens on *every* subsequent turn for one 768-pixel preview, with
        `cached_tokens` zero throughout — so a thread's cost is linear in
        (images × remaining turns) and a caller deciding how much history to
        carry is deciding what it spends.

        `reasoning` is the parameter `complete` has no need of and a
        conversational turn cannot do without. On an open-ended prompt the routed
        model consumed its **entire** output reservation on reasoning before
        emitting a character — measured at 16, 200 and 900 tokens alike, ten
        calls in a row, each returning empty content and each billed in full.
        `{"enabled": False}` produced an answer for a twenty-seventh of the cost.
        Passed through rather than decided here: this client reports what a call
        cost and does not hold opinions about how the model should think.
        """
        if not messages:
            # Refused here rather than by the provider, which answers 400 with
            # *"Input required: specify \"prompt\" or \"messages\""* — a true
            # sentence about a request this method should never have sent.
            raise ValueError("A thread needs at least one message; the provider refuses an empty one.")
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [message.wire() for message in messages],
            # Deliberate, never omitted: this is the reservation the provider
            # prices, and leaving it out invites a 402 at full credit.
            "max_tokens": self._max_output_tokens,
            # Without this the response carries no cost at all, and the run's
            # actual spend would have to be computed from a price table — which
            # is the one arithmetic that omits the search fee.
            "usage": {"include": True},
        }
        if schema is not None:
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": dict(schema)},
            }
        if search_results > 0:
            plugin: dict[str, Any] = {"id": "web", "max_results": search_results}
            if self._search_engine is not None:
                plugin["engine"] = self._search_engine
            body["plugins"] = [plugin]
        if reasoning is not None:
            body["reasoning"] = dict(reasoning)

        payload = self._post("/chat/completions", body)
        return _read_completion(payload, fallback_model=self._model)

    def key_status(self) -> KeyStatus:
        """What the account says about the ceiling. For display, never for gating.

        **No surface consumes this yet, and that is deliberate rather than an
        oversight.** `api-contract.md` specifies no action that reports remaining
        budget; the cost display that will is part of the discovery UI, and until
        it exists adding a field to the tool surface would be inventing a
        requirement. What already depends on this is the live suite's check that
        the key carries a limit at all — the only mechanical test that the
        product's entire spend ceiling has been provisioned, since nothing in this
        repository enforces one.
        """
        payload = self._get("/key")
        data = payload.get("data") or {}
        return KeyStatus(
            limit_usd=_money(data.get("limit")),
            usage_usd=_money(data.get("usage")) or Decimal(0),
            remaining_usd=_money(data.get("limit_remaining")),
            resets=data.get("limit_reset"),
        )

    # -- transport ------------------------------------------------------------

    def _post(self, path: str, body: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            response = self._http.post(
                f"{BASE_URL}{path}", headers=self._headers, json=dict(body), timeout=_timeout(COMPLETION_TIMEOUT_SECONDS)
            )
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"Could not reach OpenRouter: {exc}") from exc
        return _read_body(response)

    def _get(self, path: str) -> Mapping[str, Any]:
        try:
            response = self._http.get(f"{BASE_URL}{path}", headers=self._headers, timeout=_timeout(KEY_TIMEOUT_SECONDS))
        except httpx.HTTPError as exc:
            raise OpenRouterError(f"Could not reach OpenRouter: {exc}") from exc
        return _read_body(response)


def _timeout(overall: float) -> httpx.Timeout:
    """A budget that bounds connecting far more tightly than waiting for an answer.

    Built here rather than at each call site so the two requests cannot drift into
    disagreeing about how long a socket may take to open — which is the kind of
    difference that shows up only on the one network that provokes it.
    """
    return httpx.Timeout(overall, connect=CONNECT_TIMEOUT_SECONDS)


def _read_body(response: httpx.Response) -> Mapping[str, Any]:
    """Turn a response into a payload, or into the right kind of refusal.

    The status is what discriminates, and the two money-related codes are read
    apart here rather than anywhere above: 403 means the key is spent, 402 means
    this particular request reserved more than the balance covers.
    """
    if response.status_code == 403:
        raise KeyExhausted(
            f"OpenRouter refused the call: the key's credit limit is spent. {_provider_message(response)} "
            "The ceiling is a per-key credit limit with a monthly reset, so this clears when the month turns "
            "or when the limit is raised in the OpenRouter console."
        )
    if response.status_code == 402:
        raise RequestUnaffordable(
            f"OpenRouter declined the request as unaffordable, with credit still in the account: "
            f"{_provider_message(response)} The provider reserves the maximum output the request could produce; "
            "lower DISCOVERY_MAX_OUTPUT_TOKENS or raise the key's limit."
        )
    if response.status_code >= 400:
        raise OpenRouterError(f"OpenRouter returned HTTP {response.status_code}: {_provider_message(response)}")
    try:
        # Parsed with `parse_float=Decimal` so a cost never exists as a binary
        # float, not even momentarily. Rounding introduced at parse time cannot
        # be recovered later by converting.
        payload = json.loads(response.text, parse_float=Decimal)
    except json.JSONDecodeError as exc:
        raise OpenRouterError(f"OpenRouter returned a body that is not JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise OpenRouterError(f"OpenRouter returned {type(payload).__name__}, not an object.")
    return payload


def _provider_message(response: httpx.Response) -> str:
    """The provider's own words, which say more than the status code does.

    Quoted through rather than replaced: the 402's text carries the arithmetic
    that explains it — what was requested against what is affordable — and no
    message written here could reconstruct that.

    **A refusal has two possible authors, and reading only the outer one throws
    away the half worth acting on.** OpenRouter's own refusals — the money codes,
    a malformed request it rejects itself — put the reason in `error.message`.
    A refusal from the *model provider* behind it puts the constant string
    "Provider returned error" there instead, and the actual objection inside
    `error.metadata.raw`. Measured 2026-08-12: a null content field, an image on
    an assistant turn and an unknown role all arrived wearing that one string,
    three different mistakes with three different fixes, indistinguishable to
    whoever had to act on them.
    """
    try:
        body = response.json()
    except ValueError:
        return response.text[:300]
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return response.text[:300]
    message = str(error.get("message") or "").strip()
    upstream = _upstream_message(error.get("metadata"))
    if message and upstream:
        return f"{message} ({upstream})"
    return message or upstream or response.text[:300]


def _upstream_message(metadata: object) -> str:
    """What the provider behind OpenRouter said, attributed to which one said it.

    The provider is named because the route decides it: the same request can be
    refused by one provider and served by another, so "Alibaba objected" is a
    materially different report from "the model objected".
    """
    if not isinstance(metadata, Mapping):
        return ""
    name = str(metadata.get("provider_name") or "").strip()
    raw = metadata.get("raw")
    if not isinstance(raw, str) or not raw.strip():
        return f"{name} gave no reason" if name else ""
    detail = _upstream_detail(raw) or raw.strip()[:300]
    return f"{name}: {detail}" if name else detail


def _upstream_detail(raw: str) -> str:
    """The `message` out of an upstream error body, or nothing if it is not there.

    `raw` is the provider's own response forwarded verbatim, still wearing the
    SSE `data:` frame it was streamed in. That framing belongs to a third party
    and is free to change, so a body this cannot parse falls back to being passed
    through whole by the caller: harder to read, and strictly better than the
    alternative of telling someone only that an error occurred.
    """
    text = raw.strip()
    if text.startswith("data:"):
        text = text[len("data:") :].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ""
    error = payload.get("error") if isinstance(payload, dict) else None
    if isinstance(error, dict) and error.get("message"):
        return str(error["message"])
    return ""


def _read_completion(payload: Mapping[str, Any], *, fallback_model: str) -> Completion:
    """Read the one choice, its citations, and what the call cost."""
    # **Nothing here raises, and that is the rule rather than a series of
    # judgements.** By this point the provider has answered 2xx and the call has
    # been billed, so any exception raised from this function would travel
    # without the charge attached — and the run that paid for an unusable answer
    # would record having spent nothing. That is the under-reporting the whole
    # spend path is arranged to prevent, so an answer with no choices and an
    # answer with empty content are treated alike: reported, with their cost.
    # Judging whether the content is usable belongs to the caller.
    choices = payload.get("choices") or [{}]
    message = choices[0].get("message") or {}
    content = message.get("content") or ""

    usage = payload.get("usage") or {}
    details = usage.get("cost_details") or {}
    cost = _money(usage.get("cost")) or Decimal(0)
    # Falls back to the whole charge when the route reports no breakdown, which
    # attributes everything to tokens. That over-reports tokens on a call that
    # searched, and the alternative — inventing a split — would put a number in
    # the ledger the provider never said.
    inference = _money(details.get("upstream_inference_cost"))
    return Completion(
        content=str(content),
        model_id=str(payload.get("model") or fallback_model),
        cost_usd=cost,
        inference_cost_usd=cost if inference is None else inference,
        input_tokens=int(usage.get("prompt_tokens") or 0),
        output_tokens=int(usage.get("completion_tokens") or 0),
        citations=_read_citations(message.get("annotations")),
        finish_reason=choices[0].get("finish_reason"),
    )


def _read_citations(annotations: Sequence[Mapping[str, Any]] | None) -> tuple[Citation, ...]:
    """The pages a search returned, ignoring annotations of any other kind."""
    if not annotations:
        return ()
    found = []
    for annotation in annotations:
        if annotation.get("type") != "url_citation":
            continue
        citation = annotation.get("url_citation") or {}
        found.append(
            Citation(
                url=str(citation.get("url") or ""),
                title=str(citation.get("title") or ""),
                content=str(citation.get("content") or ""),
            )
        )
    return tuple(found)


def _money(value: object) -> Decimal | None:
    """A JSON number as exact money, or `None` where the provider sent nothing.

    `str()` before `Decimal` for the case where a body was parsed by something
    other than this module's parser and a float got through: converting the
    repr keeps the digits the provider wrote, while `Decimal(float)` would
    faithfully preserve the binary approximation instead.
    """
    if value is None:
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        try:
            return Decimal(str(value))
        except ArithmeticError:
            return None
    return None
