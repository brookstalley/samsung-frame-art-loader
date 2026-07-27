"""Discovery operations — everything a work goes through before it is accepted.

The counterpart to `catalogue.py`, and the split is the pipeline's own: the
catalogue holds works that are already in the collection, discovery holds runs,
proposed works, the image instances found for them, what each run spent, and the
curator's verdicts. Both are reached the same way — a surface unpacks arguments,
calls one method here, and formats the result — so the rules live in exactly one
place regardless of which concern they belong to.

**Discovery depends on the catalogue and never the other way round.** Acceptance
is a promotion: a candidate work becomes an Artwork and its image instances
become that work's Sources. The dependency runs in the direction the pipeline
does, so nothing in the catalogue has to know that candidates exist.

Methods are synchronous, for the same reason the catalogue's are: the store is a
local file answering point lookups in well under a millisecond, and a synchronous
core keeps this logic testable without an event loop.
"""

import logging

from curation.services.catalogue import CatalogueService

log = logging.getLogger(__name__)


class DiscoveryService:
    """Read and write the pre-acceptance pipeline."""

    def __init__(self, catalogue: CatalogueService) -> None:
        self._catalogue = catalogue
