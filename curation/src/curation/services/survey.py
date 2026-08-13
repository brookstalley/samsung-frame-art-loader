"""What a curator sees when they look at a work — composed once, for both surfaces.

A review surface does not want a work; it wants a work together with everything
needed to judge it: how large the held image would render on this deployment's
wall, and whether there is an image to look at at all. `api-contract.md` requires
exactly that pairing of `art_review`'s listings, and the browser grid needs the
same thing — so composing it here is what stops an agent and a click disagreeing
about whether a work is big enough for the wall.

**Nothing is decided here that is decided elsewhere.** The readiness verdict is
`display_fit`'s, the choice of which held image to show is the thumbnail
service's, and paging is the catalogue's. This gathers them, and its only
judgement of its own is that a missing answer is reported as a stated reason
rather than as an absent field — a card that shows no size because a work has no
master must not look like a card whose work is small.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from curation.persistence.records import MatColor, Original, Source, WorkFacet
from curation.services.catalogue import ArtworkDetail, CatalogueService, FacetGroup, RenditionView
from curation.services.display import DisplayService
from curation.services.display_fit import ArtworkBox, FitAssessment
from curation.services.thumbnails import ThumbnailService, ThumbnailUnavailable


@dataclass(frozen=True, slots=True)
class ImageAvailability:
    """Whether this work can be shown, and which held image would be shown."""

    available: bool
    #: `tv_display` when the wall's own render is current, `original` when the
    #: master is standing in for it, None when there is nothing to show.
    source_kind: str | None
    #: Present exactly when `available` is false, saying what is missing.
    note: str | None


@dataclass(frozen=True, slots=True)
class WorkSurvey:
    """One work as a review surface needs it."""

    detail: ArtworkDetail
    #: None when the work holds no master, in which case `fit_note` says so.
    fit: FitAssessment | None
    fit_note: str | None
    image: ImageAvailability


@dataclass(frozen=True, slots=True)
class WorkSurveyPage:
    """One page of works, carrying enough to describe its own place in the set."""

    entries: Sequence[WorkSurvey]
    total: int
    limit: int
    offset: int
    truncated: bool
    #: What the facet controls beside this grid should offer, with each option's
    #: count over the *rest* of the filter. Travels with the page rather than
    #: from a second route, so the numbers and the works cannot describe
    #: different sets.
    facets: Sequence[FacetGroup] = ()


@dataclass(frozen=True, slots=True)
class WorkDossier:
    """One work in full — what a detail view shows."""

    survey: WorkSurvey
    original: Original | None
    sources: Sequence[Source]
    renditions: Sequence[RenditionView]
    mat_colors: Sequence[MatColor]
    #: What this work is said to be. On the dossier rather than on every grid
    #: card: the Work screen states a work's facets, and a grid states the
    #: collection's counts — one card carrying its own six kinds would be a read
    #: per work per page for something no card shows.
    facets: Sequence[WorkFacet] = ()


class SurveyService:
    """Read works the way a surface that shows them to a human needs them."""

    def __init__(
        self,
        catalogue: CatalogueService,
        display: DisplayService,
        thumbnails: ThumbnailService,
        box: ArtworkBox,
    ) -> None:
        self._catalogue = catalogue
        self._display = display
        self._thumbnails = thumbnails
        self._box = box

    @property
    def artwork_box(self) -> ArtworkBox:
        """The space this deployment renders a work into, as resolved at startup."""
        return self._box

    def list_works(
        self,
        *,
        status: str | None = None,
        q: str | None = None,
        facets: Mapping[str, Sequence[str]] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> WorkSurveyPage:
        """A page of works, each with its fit verdict and its image state.

        The narrowing arguments are passed straight through: what `q` and
        `facets` mean, and how the facet counts beside the page are computed, is
        `CatalogueService.list_artworks`'s to decide. Restating any of it here
        would be the second implementation of "list the catalogue" that the shared
        service layer exists to prevent.
        """
        listing = self._catalogue.list_artworks(status=status, q=q, facets=facets, limit=limit, offset=offset)
        return WorkSurveyPage(
            entries=[self._survey(entry) for entry in listing.entries],
            total=listing.total,
            limit=listing.limit,
            offset=listing.offset,
            truncated=listing.truncated,
            facets=listing.facets,
        )

    def theme_works(self, theme_id: str) -> Sequence[WorkSurvey]:
        """A theme's works in curated order, each judged the way a grid card needs.

        The order is the theme's, so this reads through the display service
        rather than re-deriving it: a second implementation of "which works, in
        what order" is exactly the divergence a surface must not introduce.
        """
        return [self._survey(detail) for detail in self._display.theme_works(theme_id)]

    def get_work(self, artwork_id: str) -> WorkDossier:
        """One work with everything a detail view shows."""
        detail = self._catalogue.get_artwork(artwork_id)
        return WorkDossier(
            survey=self._survey(detail),
            original=self._catalogue.get_original(artwork_id),
            sources=self._catalogue.list_sources(artwork_id),
            renditions=self._catalogue.list_renditions(artwork_id),
            mat_colors=self._catalogue.mat_color_history(artwork_id),
            facets=self._catalogue.facets_for(artwork_id),
        )

    def _survey(self, detail: ArtworkDetail) -> WorkSurvey:
        artwork_id = detail.artwork.id
        original = self._catalogue.get_original(artwork_id)
        fit = None if original is None else self._catalogue.display_fit(artwork_id, box=self._box)
        fit_note = None if original is not None else "No master image has been acquired, so its size on the wall is unknown."
        try:
            source = self._thumbnails.source_for(artwork_id)
        except ThumbnailUnavailable as absent:
            # The type exists for this: "there is no image yet" is an ordinary
            # state of a catalogue mid-acquisition, and its message is written to
            # be shown beside the work rather than raised at the curator.
            image = ImageAvailability(available=False, source_kind=None, note=str(absent))
        else:
            image = ImageAvailability(available=True, source_kind=source.kind, note=None)
        return WorkSurvey(detail=detail, fit=fit, fit_note=fit_note, image=image)
