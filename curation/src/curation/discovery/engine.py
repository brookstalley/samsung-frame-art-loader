"""The seam discovery's paid work sits behind, and the types that cross it.

Phase 1 turns a curator's intent into a list of works. Doing that means calling a
model, and possibly searching the web, against a foreign API that bills per token
and per search. **None of that is in this module.** What is here is the narrow
interface that work is reached through, so the run lifecycle above it — starting,
gating, approving, cancelling, pricing — is buildable and testable without a
network, an API key, or a cent of spend.

The seam is what makes the provider replaceable. The engine depends on nothing
about the transport, so swapping a direct HTTP client for a framework's chat
model later is one file's work rather than a rewrite of everything that calls it.

**An engine reports what it spent; it never decides whether it may.** The ceiling
is a provider-side credit limit, and `BudgetExhausted` is how its refusal
arrives here — never a local sum crossing a number, because a local tally that
fails open is indistinguishable from one that works.

**Not every refusal is exhaustion.** The provider also declines a request whose
*reserved* output would cost more than the credit remaining, which is a different
condition with money still in the account and a different correct response: ask
for less rather than stop. Only true exhaustion raises `BudgetExhausted`; the
mapping from a provider's status codes to that distinction belongs to the client
behind this seam, and the measured shapes are in `openrouter-api-findings.md`.

**The search allowance travels in and the searches used come back**, so the run
that authorised a bounded number of searches can check it got one. An engine that
overruns its allowance is a defect rather than an expensive success, and the
caller can only see that if the number comes back.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable

from curation.persistence.discovery_records import SpendCategory


@dataclass(frozen=True, slots=True)
class WorkListRequest:
    """What phase 1 is asked for: the intent, and how much searching it may do.

    `search_allowance` is a count of web searches, not a sum of money. A monthly
    credit limit cannot bound a single run that has decided to search forever,
    and an estimate a run may freely exceed is not an estimate — so the bound
    that makes the pre-run figure meaningful is expressed in the unit the run
    actually consumes.
    """

    intent_text: str
    search_allowance: int


@dataclass(frozen=True, slots=True)
class ProposedWork:
    """One work phase 1 says matches the intent.

    Deliberately not a `CandidateWork`: an engine proposes a title, an artist and
    a reason, and has no business minting ids, dedup keys or run references. The
    work of turning this into a stored row belongs to the caller, which is what
    keeps the dedup key derived in exactly one place.

    `rationale` is required for the same reason the stored record requires it — a
    review card that cannot say *why* this work matched asks the curator to judge
    a bare title.
    """

    title: str
    rationale: str
    artist: str | None = None


@dataclass(frozen=True, slots=True)
class EngineSpend:
    """One charge the engine incurred, in the provider's own terms.

    `units` carries the count for anything billed per call rather than per token
    — web searches, today. It is the authoritative search count: deriving the
    number used from the same record that prices it means the cap and the bill
    cannot disagree about how much searching happened.
    """

    category: SpendCategory
    cost_usd: Decimal
    model_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    units: int | None = None


@dataclass(frozen=True, slots=True)
class WorkList:
    """What phase 1 produced, and what producing it cost.

    `strategy` is how the intent was read — which works were taken to be in
    scope, and what was searched for. It comes from the engine rather than being
    composed above it because interpreting the intent is the engine's act, and a
    sentence assembled from settings would describe the configuration rather
    than the reading. It is what lets a curator see *why* a list looks the way it
    does before judging the works in it.
    """

    works: Sequence[ProposedWork]
    spend: Sequence[EngineSpend] = ()
    strategy: str | None = None

    @property
    def searches_used(self) -> int:
        """How many web searches this run made, from the records that price them.

        Derived rather than reported separately so there is one number: a
        `searches_used` field beside a priced spend record is two tallies of the
        same event, free to disagree, and the disagreement would surface as a cap
        that held while the bill said otherwise.
        """
        return sum(entry.units or 0 for entry in self.spend if entry.category is SpendCategory.WEB_SEARCH)


class EngineFailure(Exception):
    """Phase 1 could not finish, and this is what it had spent when it stopped.

    Spend is carried on the exception because a run that broke halfway still
    incurred whatever it incurred, and a failure path that dropped it would
    under-report the month by exactly the amount the failures cost.
    """

    def __init__(self, message: str, *, spend: Sequence[EngineSpend] = ()) -> None:
        super().__init__(message)
        self.spend = tuple(spend)


class BudgetExhausted(EngineFailure):
    """The provider refused to spend more.

    Distinct from every other failure because the correct response differs: this
    means stop, and an ordinary failure means retry. An agent that cannot tell
    them apart will keep paying to be told it has no money — which is why the run
    state it produces is its own, and not a generic error.
    """


@runtime_checkable
class DiscoveryEngine(Protocol):
    """Phase 1, as everything above it sees it.

    `unavailable_reason` is how an engine that cannot run says so *before* a run
    exists, rather than by failing one. The distinction matters: a run that was
    created and immediately failed is a record of something that went wrong,
    while a refused start is a record of nothing at all — and the catalogue
    should not accumulate rows for a capability that is simply not wired up yet.
    """

    @property
    def unavailable_reason(self) -> str | None:
        """Why this engine cannot run, or `None` when it can."""

    def enumerate_works(self, request: WorkListRequest) -> WorkList:
        """Turn an intent into a list of works, spending what that takes.

        Raises `BudgetExhausted` when the provider refuses further spend, and
        `EngineFailure` for anything else that stops it finishing.
        """


@dataclass(frozen=True, slots=True)
class UnavailableEngine:
    """A stand-in for a phase-1 engine that has not been wired up.

    A deployment needs *an* engine to be handed to the service layer, and the
    honest one to hand it before the real client exists is one that says so.
    Refusing is deliberately not the same as substituting a convincing test
    double: a double wired into a real deployment would write invented works into
    a real catalogue, and the curator's evidence that discovery worked would be
    the product fabricating it.
    """

    reason: str

    @property
    def unavailable_reason(self) -> str | None:
        return self.reason

    def enumerate_works(self, request: WorkListRequest) -> WorkList:
        """Never reached: a start is refused before a run exists. Guarded anyway."""
        raise EngineFailure(self.reason)


#: Why a deployment of this version cannot discover. The surface quotes it back,
#: so it is written for a curator or an agent reading a refusal rather than for a
#: developer reading a stack trace.
PHASE_ONE_NOT_WIRED: str = (
    "Discovery phase 1 is not wired up in this deployment: no model client is configured, "
    "so there is nothing that can turn an intent into a list of works. Every other "
    "art_discovery action works on runs that already exist."
)


def unavailable_engine(reason: str = PHASE_ONE_NOT_WIRED) -> DiscoveryEngine:
    """The engine a deployment gets until a real one is configured."""
    return UnavailableEngine(reason)
