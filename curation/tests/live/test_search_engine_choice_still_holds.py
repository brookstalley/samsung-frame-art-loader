"""The engine comparison, as a test rather than as a recorded conclusion.

`parallel` was chosen because three back-ends scored identically on this
product's two stated hard cases and it costs a fifth as much per request. Both
halves of that can stop being true: an engine's index can decay, and a per-request
price can move. A decision resting on a measurement nobody re-runs quietly stops
describing the world.

**Deselected by default.** These calls cost real money on the configured key and
need the network. Run deliberately:

    uv run pytest -m live_api

The corpus is deliberately mid-tier rather than famous. "Resolve The Night Watch
to the Rijksmuseum" is generic relevance and every engine passes it; the spike's
own constraint is that the comparison must be made on this product's actual hard
case, which is a work a search has to look up rather than one it has seen ten
thousand times. Holdings here are known independently rather than taken from an
engine's own citations, which would have scored the others against one engine's
answer.
"""

import os
from urllib.parse import urlsplit

import pytest

from curation.config import DEFAULT_DISCOVERY_MODEL, DEFAULT_DISCOVERY_SEARCH_ENGINE
from curation.discovery.openrouter import OpenRouterClient

pytestmark = pytest.mark.live_api

KEY = os.environ.get("OPENROUTER_API_KEY")
needs_key = pytest.mark.skipif(not KEY, reason="OPENROUTER_API_KEY is not set")

#: (work, artist, the domain of the institution that holds it).
HOLDINGS = [
    ("Early Sunday Morning", "Edward Hopper", "whitney.org"),
    ("One: Number 31, 1950", "Jackson Pollock", "moma.org"),
    ("The Windmill at Wijk bij Duurstede", "Jacob van Ruisdael", "rijksmuseum.nl"),
    ("Mr and Mrs Andrews", "Thomas Gainsborough", "nationalgallery.org.uk"),
    ("The Nobleman with his Hand on his Chest", "El Greco", "museodelprado.es"),
]

#: What every engine scored when the choice was made. A floor: an engine that
#: still resolves most of the corpus has not regressed in a way that reopens the
#: decision, and demanding a clean sweep would make this fail on one reorganised
#: museum website.
ADOPTED_FLOOR = 4


def host_of(url: str) -> str:
    try:
        return (urlsplit(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


def resolved(engine: str) -> tuple[int, float]:
    """How many holdings this engine surfaced, and what asking cost."""
    client = OpenRouterClient(KEY or "", model=DEFAULT_DISCOVERY_MODEL, max_output_tokens=1500, search_engine=engine)
    found, spend = 0, 0.0
    for title, artist, domain in HOLDINGS:
        completion = client.complete(
            prompt=(
                f"Find the page for the painting '{title}' by {artist} on the website of the museum "
                "that holds it. Give the URL and nothing else."
            ),
            search_results=10,
        )
        spend += float(completion.cost_usd)
        hosts = [host_of(citation.url) for citation in completion.citations]
        found += any(host == domain or host.endswith("." + domain) for host in hosts)
    return found, spend


@needs_key
def test_the_chosen_engine_still_resolves_works_to_their_museums():
    """The quality half of the decision, on the engine actually configured."""
    found, _ = resolved(DEFAULT_DISCOVERY_SEARCH_ENGINE)

    assert found >= ADOPTED_FLOOR, (
        f"{DEFAULT_DISCOVERY_SEARCH_ENGINE} resolved {found} of {len(HOLDINGS)} holdings, below the "
        f"{ADOPTED_FLOOR} it was chosen at — the quality half of that choice no longer holds"
    )


@needs_key
def test_the_chosen_engine_is_still_the_cheap_one():
    """The half the decision actually turned on.

    Quality did not separate these, so price did. If Parallel stopped being
    markedly cheaper the comparison would have nothing left to decide on and
    would need re-running against something other than cost.
    """
    _, chosen_spend = resolved(DEFAULT_DISCOVERY_SEARCH_ENGINE)
    _, exa_spend = resolved("exa")

    assert chosen_spend < exa_spend, (
        f"{DEFAULT_DISCOVERY_SEARCH_ENGINE} cost ${chosen_spend:.4f} against exa's ${exa_spend:.4f}; "
        "the price gap the engine was chosen for has closed"
    )
