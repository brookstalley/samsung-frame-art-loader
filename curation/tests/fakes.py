"""A discovery engine the suite drives, standing where a paid one will stand.

**Not scaffolding.** This is the provider every test of the run lifecycle runs
against, and it stays that way once a real engine exists: the lifecycle's
interesting cases are a run that breaks, a run the provider refuses to fund, and
a run that overruns its search allowance, and none of those can be provoked
reliably — or cheaply — against a live API.

It lives under `tests/` rather than in the package on purpose. A convincing
stand-in reachable from a deployment is one somebody eventually wires up, and the
result would be invented works written into a real catalogue with nothing to
distinguish them from found ones. What the package ships instead is an engine
that refuses.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from dataclasses import dataclass, field
from decimal import Decimal

from curation.discovery.engine import (
    EngineFailure,
    EngineSpend,
    ProposedWork,
    WorkList,
    WorkListRequest,
)
from curation.persistence.discovery_records import SpendCategory

#: Titles that are actually distinct works by one artist, so a run built from
#: them exercises the dedup key doing nothing rather than the key collapsing a
#: list into one row and the test passing for the wrong reason.
_TITLES = (
    "The Persistence of Memory",
    "The Elephants",
    "Swans Reflecting Elephants",
    "The Temptation of St. Anthony",
    "Galatea of the Spheres",
)


def a_work(title: str, *, artist: str | None = "Salvador Dalí") -> ProposedWork:
    return ProposedWork(title=title, artist=artist, rationale=f"{title} is a central example of what was asked for.")


def works(count: int, *, artist: str | None = "Salvador Dalí") -> tuple[ProposedWork, ...]:
    """`count` distinct works, generated past the end of the named list.

    Numbered beyond the handful of real titles rather than repeating them: a
    twenty-six-work run testing the approval gate needs twenty-six *distinct*
    works, and recycling titles would have the dedup key silently reduce it to
    five.
    """
    named = [a_work(title, artist=artist) for title in _TITLES[:count]]
    extra = [a_work(f"Untitled Study No. {index}", artist=artist) for index in range(len(named), count)]
    return tuple(named + extra)


def spent(*, tokens_usd: str = "0.08", searches: int = 1, search_usd: str = "0.005") -> tuple[EngineSpend, ...]:
    """What a run of this size costs, in the two categories phase 1 can incur.

    Web search is its own category because it bills per call rather than per
    token, and its `units` is where the search count lives — the same record that
    prices the searches is the one the cap is read from, so the two cannot
    disagree.
    """
    return (
        EngineSpend(
            category=SpendCategory.DISCOVERY_TOKENS,
            cost_usd=Decimal(tokens_usd),
            model_id="fake/deterministic-v1",
            input_tokens=490_000,
            output_tokens=30_000,
        ),
        EngineSpend(category=SpendCategory.WEB_SEARCH, cost_usd=Decimal(search_usd) * searches, units=searches),
    )


def a_work_list(count: int = 3, *, searches: int = 1, artist: str | None = "Salvador Dalí") -> WorkList:
    return WorkList(works=works(count, artist=artist), spend=spent(searches=searches))


@dataclass
class FakeEngine:
    """Answers with whatever it was built to answer, and records what it was asked.

    `gate` is what makes a run observably in-flight: a test that needs to see a
    run *while* it is working — to cancel it, to watch a status call hold, to
    leave it for startup reconciliation to find — has to be able to stop phase 1
    in the middle, and an engine that always returns instantly cannot be caught
    there.
    """

    result: WorkList = field(default_factory=a_work_list)
    error: EngineFailure | None = None
    reason: str | None = None
    gate: threading.Event | None = None
    requests: list[WorkListRequest] = field(default_factory=list)

    @property
    def unavailable_reason(self) -> str | None:
        return self.reason

    def enumerate_works(self, request: WorkListRequest) -> WorkList:
        self.requests.append(request)
        if self.gate is not None:
            # Bounded so a test that forgets to release the gate fails as a test
            # rather than hanging the suite.
            assert self.gate.wait(timeout=20), "the fake engine was never released"
        if self.error is not None:
            raise self.error
        return self.result

    @property
    def searched(self) -> Sequence[int]:
        """The allowance every call was given, for asserting the cap travelled."""
        return [request.search_allowance for request in self.requests]
