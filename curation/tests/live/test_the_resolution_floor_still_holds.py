"""How much of a real phase-1 list the pipeline can actually find images for.

**A green suite is not evidence that this pipeline works.** Both suites were green
on 2026-08-04 while two production runs proposed works and resolved none of them,
because no rule anywhere said a run must resolve anything: partial success is
normal by design, and nothing distinguished "34 of 40" from "0 of 8". This is the
rule. It states the rate as a measurement against a fixed corpus and fails when it
falls, which is the whole of what the success criterion in `product-brief.md`
promises and the mechanism it records as owed.

**The corpus is real phase-1 output, not a wish list.** `phase_one_proposals.json`
holds proposals a model actually produced over realistic intents, with their
ground-truth work identities assigned by reading them. So the works here carry
every hazard the real pipeline meets — invented titles, citation markup, the same
painting under two names, and works no museum in the wiring holds.

**Deselected by default**, under `live_museum` with its sibling: it needs the
network and costs nothing.

    uv run pytest -m live_museum

**What a failure means depends on the direction.** Below the floor is a
regression and the diff that caused it is the suspect. *Above* it is not a pass to
be enjoyed quietly — it means the floor is stale, and the number below is raised
in the same change that earned it, so the next regression is measured against what
the pipeline can really do rather than against a figure it outgrew.
"""

import json
from pathlib import Path

import pytest

from curation.discovery.artic import build_image_search
from curation.discovery.dedup import clean_name
from curation.discovery.images import ImageQuery, ImageSearchFailure
from curation.discovery.phase_two import PhaseTwoEngine
from curation.services.display_fit import ArtworkBox

pytestmark = pytest.mark.live_museum

USER_AGENT = "samsung-frame-art-loader test suite (brooks@noun.band)"

#: How many of the corpus's distinct works the pipeline resolves to a usable
#: image. **Measured, and to be re-measured rather than reasoned about.**
#:
#: The value stated here is the floor, not the observation: a run that does
#: better is welcome and a run that does worse is a regression. Raising it
#: requires a measurement; *lowering* it requires the ratification that the
#: success criterion in `product-brief.md` describes, because a floor that any
#: change may quietly lower is not a floor.
#:
#: History, kept because the trend is the point and one number cannot show it:
#: **4** when the corpus was first measured against the live provider, **5** after
#: the museum query stopped carrying the artist (both 2026-08-04). One work, and
#: that is the honest result — the fold was a real defect and fixing it was never
#: going to be the thing that moves this. What moves it is supply, and the five
#: that resolve say so plainly: four Japanese prints and one O'Keeffe, all of them
#: safely inside the public-domain boundary, out of fifty-one works a model
#: proposed across six realistic intents.
RESOLUTION_FLOOR = 5

#: A fixed 42" geometry, matching the sibling live suite: the floor verdict has to
#: mean something against a known panel, and it must not move when a deployment's
#: television changes.
BOX = ArtworkBox(width=3316, height=1597, pixels_per_inch=104.9, floor_inches=12.0)

CORPUS = Path(__file__).resolve().parents[1] / "fixtures" / "phase_one_proposals.json"


def distinct_works() -> list[tuple[str, str]]:
    """One (title, artist) per ground-truth work, cleaned as the engine cleans them.

    Distinct by the corpus's own `work` label rather than by title: the same
    painting appears under several names across runs, and counting each spelling
    separately would measure the model's inconsistency instead of the pipeline's
    reach. The first spelling of each work is the one asked about, which is
    arbitrary and honest — a later one is no more the "real" title than the first.

    `clean_name` is applied because phase 1 applies it before a title ever
    becomes a proposal; asking the museum about raw citation markup would measure
    a query the pipeline never sends.
    """
    rows = json.loads(CORPUS.read_text())["rows"]
    first: dict[str, tuple[str, str]] = {}
    for row in rows:
        first.setdefault(row["work"], (clean_name(row["title"]), clean_name(row.get("artist") or "")))
    return list(first.values())


def test_the_pipeline_still_resolves_at_least_the_floor():
    """The measurement the success criterion names, over the corpus it names.

    Counted the way the pipeline counts: a work resolves when an instance
    survives the identity comparison *and* clears the display floor, which is
    exactly the condition under which a selection is made and the work becomes
    reviewable. Instances that are found and refused, or found and too small, are
    not resolutions — treating them as such would report a rate a curator cannot
    see any of.

    A provider that cannot be reached is not counted either way and is reported:
    a network fault must not read as the pipeline getting worse, which is the
    same distinction phase 2 draws between `unresolved` and unreachable.
    """
    engine = PhaseTwoEngine(build_image_search(user_agent=USER_AGENT), box=BOX)
    works = distinct_works()
    resolved, unreachable = [], []
    for title, artist in works:
        try:
            instances = engine.resolve(ImageQuery(title=title, artist=artist or None)).instances
        except ImageSearchFailure:
            unreachable.append(title)
            continue
        if any(not entry.below_floor for entry in instances):
            resolved.append(title)

    assert not unreachable, f"the museum could not be asked about {len(unreachable)}: {unreachable}"
    assert len(resolved) >= RESOLUTION_FLOOR, (
        f"resolved {len(resolved)} of {len(works)}, below the floor of {RESOLUTION_FLOOR}. " f"Resolved: {sorted(resolved)}"
    )
