"""Catalogue operations — the only place their logic lives.

Everything above this module is a binding: the MCP tools unpack arguments,
call one method here, and format what comes back; the HTTP handlers will do
the same. Two implementations of "list the catalogue" would diverge within
weeks, and the divergence would show up as an agent and a click disagreeing
about the same catalogue, which reads as the product being untrustworthy
rather than as a bug.

**This is also where the catalogue's rules are enforced, at write time.** A rule
applied on the way out instead of on the way in is a rule the data can already
violate, and the violation is then permanent. Rules that span rows — exactly one
mat colour current, at most one primary source — are applied inside a store
transaction as a clear-then-set pair, because a pair that can be interrupted
between its halves leaves the catalogue in the state the rule forbids.

Works, artists, sources, originals, renditions and mat colours live here. Themes,
the standing directive and the manifest built from them live in `display.py`,
which holds this service; nothing here holds that one.

Methods are synchronous. The store is a local file answering point lookups in
well under a millisecond, and a synchronous core keeps this logic testable
without an event loop.
"""

import logging
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Final

from curation.persistence.catalogue import CatalogueStore, WorkQuery
from curation.persistence.records import (
    AcquisitionMethod,
    Artist,
    Artwork,
    ArtworkStatus,
    FacetDerivation,
    FetchStatus,
    MatColor,
    MatMethod,
    Original,
    Rendition,
    RenditionKind,
    RightsStatus,
    Source,
    SourceClass,
    VocabularyKind,
    WorkFacet,
    is_current,
)
from curation.services.display_fit import ArtworkBox, FitAssessment, assess_display_fit
from curation.services.errors import ServiceError
from curation.services.fields import description_markup, relative_path, require_member, require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)

#: How many works a listing returns when the caller does not say.
DEFAULT_LIST_LIMIT: Final[int] = 25

#: The most a single listing will return. A cap exists because the MCP client
#: truncates oversized tool output, and a silently truncated list is worse than
#: a short one that says how much it left behind.
MAX_LIST_LIMIT: Final[int] = 100

#: How many options one facet offers before the list is cut. **A rail is read, so
#: it has to be readable**: `artist` alone holds hundreds of values on a
#: thousands-work catalogue, and a control listing every one of them is a scroll
#: rather than a choice. The cut is by count, so what survives is what most of the
#: collection actually is — and the group reports how many values it holds, so a
#: control can say "50 of 512" rather than implying the vocabulary is fifty long.
#: **A value the curator has selected is never cut**, whatever its count: an
#: option that vanished from the rail could not be switched off again.
MAX_FACET_VALUES: Final[int] = 50

#: How many words one search may carry. Terms narrow rather than widen, so
#: dropping the surplus would silently *broaden* the result — the refusal names
#: the cap instead. The bound exists because each term adds a `LIKE` against every
#: searched column, and a pasted paragraph would compose a statement in the
#: hundreds of clauses against a request nobody meant to make.
MAX_SEARCH_TERMS: Final[int] = 8


@dataclass(frozen=True, slots=True)
class ArtworkDetail:
    """A work together with the artist record it points at, if any."""

    artwork: Artwork
    artist: Artist | None


@dataclass(frozen=True, slots=True)
class FacetOption:
    """One value a facet control offers, and what choosing it would select."""

    value: str
    #: How many works the *rest* of the filter selects that also carry this value.
    #: Computed with this facet's own selection dropped — see `WorkQuery.without`.
    count: int
    selected: bool

    @property
    def disabled(self) -> bool:
        """True for an option that would select nothing, and it is still returned.

        **Disabled, never omitted.** Hiding a zero makes the vocabulary appear to
        shrink as filters are applied, which reads as data loss rather than as an
        empty intersection — and it takes away the only on-screen evidence that
        the combination the curator is imagining does not exist.

        A *selected* value is never disabled even at zero, because the control
        that turns it off is the same control that would be greyed out. That is
        the state a shared link can arrive in, and it is the one state from which
        an empty grid has to be escapable.
        """
        return self.count == 0 and not self.selected


@dataclass(frozen=True, slots=True)
class FacetGroup:
    """One facet kind as a control renders it."""

    kind: VocabularyKind
    #: Ordered by count, commonest first, then by value. Capped at
    #: `MAX_FACET_VALUES` with every selected value kept regardless.
    options: Sequence[FacetOption]
    #: How many distinct values this kind holds across the catalogue, before the
    #: cap. Present so a control can say how much it is not showing.
    total_values: int

    @property
    def truncated(self) -> bool:
        """True when this kind holds values the options do not carry."""
        return len(self.options) < self.total_values


@dataclass(frozen=True, slots=True)
class ArtworkListing:
    """One page of works, and enough context to describe it honestly."""

    entries: Sequence[ArtworkDetail]
    total: int
    limit: int
    offset: int
    #: One group per facet kind, always all of them and always in vocabulary
    #: order, so a control does not appear and disappear as the catalogue is
    #: filtered. A kind the catalogue holds no facets of comes back with no
    #: options rather than being left out.
    facets: Sequence[FacetGroup] = ()

    @property
    def truncated(self) -> bool:
        """True when works matched the filter that this page does not carry."""
        return self.offset + len(self.entries) < self.total


@dataclass(frozen=True, slots=True)
class RenditionView:
    """A rendition and whether it still matches the image it was made from.

    Staleness is derived on every read rather than stored, so it cannot disagree
    with the original it is a statement about. The 2024 code expressed the same
    intent imperatively — clearing the television's state whenever it regenerated
    an image — which worked only at the one site that remembered to.
    """

    rendition: Rendition
    stale: bool


def _offered(options: Sequence[FacetOption]) -> Sequence[FacetOption]:
    """Order a kind's options and cut the tail, keeping every selected one.

    Commonest first, then alphabetically, because what a rail is *for* is showing
    where most of the collection is; a value the curator has already chosen
    survives the cut whatever its count, since the control that removes it is the
    option itself.
    """
    ordered = sorted(options, key=lambda option: (-option.count, option.value.casefold()))
    if len(ordered) <= MAX_FACET_VALUES:
        return ordered
    kept = list(ordered[:MAX_FACET_VALUES])
    # The tail is already in order, so appending from it keeps the whole list in
    # order — nothing is re-sorted and the kept prefix does not move.
    kept.extend(option for option in ordered[MAX_FACET_VALUES:] if option.selected)
    return kept


class CatalogueService:
    """Read and write the catalogue."""

    def __init__(self, store: CatalogueStore) -> None:
        self._store = store

    # -- reads: works ---------------------------------------------------------

    def list_artworks(
        self,
        *,
        status: str | None = None,
        q: str | None = None,
        facets: Mapping[str, Sequence[str]] | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> ArtworkListing:
        """Page through the catalogue, narrowed by text and by facet.

        `status` is optional: omitting it lists accepted and archived works
        together, which is what "the whole catalogue" means.

        `q` is free text, split on whitespace; every word must appear somewhere in
        the work's own text or its artist's name. `facets` maps a facet kind to
        the values chosen for it — several values within a kind mean *either*,
        several kinds mean *both*.

        **The facet counts come back with the page rather than from a second
        route**, because they answer the same question the grid answers — what
        does this filter select? — and two routes would give a curator two answers
        to it, which could differ by a write landing between the calls. The cost
        is that they are recomputed on page 2 of a grid that did not change them;
        that is accepted on a loopback service serving one household, and
        `api-contract.md` records the measurement and the trigger for revisiting.
        """
        resolved_status = self._parse_status(status)
        resolved_limit = DEFAULT_LIST_LIMIT if limit is None else limit
        if not 1 <= resolved_limit <= MAX_LIST_LIMIT:
            raise ServiceError(f"limit must be between 1 and {MAX_LIST_LIMIT}, got {resolved_limit}.")
        if offset < 0:
            raise ServiceError(f"offset cannot be negative, got {offset}.")

        query = WorkQuery(status=resolved_status, terms=self._parse_terms(q), facets=self._parse_facets(facets))
        # **One read scope over the page, the total and every facet count.**
        # These are four statements or more, and the response asserts they agree:
        # the counts are offered as what the grid *would* hold, so a write
        # landing between the page and its counts publishes a page whose parts
        # were never simultaneously true. This is the guarantee `select_page`
        # already gave the rows and their total by taking one lock, extended to
        # a read the service composes rather than the store — and it is the
        # reason the counts can be in this response at all rather than behind a
        # second route, so it has to be true and not merely intended.
        with self._store.reading():
            page = self._store.list_artworks(query, limit=resolved_limit, offset=offset)
            groups = self._facet_groups(query)
            # Attribution is the first thing anyone judges a work by, so a
            # listing that returned a bare artist id would send every caller
            # straight back for a second read. Resolved here, memoised within the
            # page: a page is capped at MAX_LIST_LIMIT local point lookups, and
            # works by the same artist collapse to one. Inside the scope with
            # the rest: a work whose artist was renamed mid-listing would
            # otherwise be attributed to a name the same response's counts were
            # not computed against.
            artists: dict[str, Artist | None] = {}
            entries = [
                ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, artists))
                for artwork in page.artworks
            ]
        return ArtworkListing(
            entries=entries,
            total=page.total,
            limit=resolved_limit,
            offset=offset,
            facets=groups,
        )

    def _facet_groups(self, query: WorkQuery) -> Sequence[FacetGroup]:
        """Every facet kind, with each value's count and whether it is chosen.

        **The rule this method exists for: a facet's counts are computed over the
        results filtered by every *other* facet, never by its own.** Including its
        own would collapse each control to the single value already chosen — the
        curator could not change their mind about Baroque without first clearing
        Baroque, which at a rail of six controls is a filter that can only be
        escaped and never adjusted.

        What it buys is the acceptance criterion: an option offered as enabled has
        a count computed against exactly the filter that would be in force once it
        is clicked, so **clicking an enabled option cannot produce an empty grid**.
        Free text is the one narrowing that can, and it explains itself.

        **The kinds nobody has filtered on are counted together, in one
        statement.** That is not an exception to the rule above — it *is* the
        rule: `without(kind)` returns the same query for every kind that is not
        narrowing anything, so those kinds all need one and the same count. Only a
        kind with a selection of its own needs a query of its own. Measured on the
        4,000-work corpus with `tools/search_latency.py`, this and the unnarrowed
        skip in `_Restriction.narrows` together took the whole listing's median
        from **57 ms to 6 ms** unfiltered and from **101 ms to 31 ms** with a
        search term.
        """
        vocabulary = self._store.facet_vocabulary(status=query.status)
        # A kind with nothing chosen has nothing to drop, so `without` leaves the
        # query as it stands and one statement answers for all of them together.
        unfiltered = [kind for kind in VocabularyKind if not query.facets.get(kind)]
        counts = dict(self._store.count_facet_values(unfiltered, query))
        for kind in VocabularyKind:
            if query.facets.get(kind):
                counts.update(self._store.count_facet_values([kind], query.without(kind)))

        groups: list[FacetGroup] = []
        for kind in VocabularyKind:
            held = list(vocabulary.get(kind, ()))
            chosen = set(query.facets.get(kind, ()))
            # A chosen value the catalogue does not hold — a shared link naming
            # a value since renamed away, or one that exists only among works the
            # status filter excludes — is still offered, at zero and selected.
            # Otherwise the filter in force would have no control to turn it off.
            values = held + [value for value in chosen if value not in set(held)]
            tallies = counts[kind]
            options = [FacetOption(value=value, count=tallies.get(value, 0), selected=value in chosen) for value in values]
            groups.append(FacetGroup(kind=kind, options=_offered(options), total_values=len(values)))
        return groups

    def get_artwork(self, artwork_id: str) -> ArtworkDetail:
        """Return one work in full, with its artist resolved."""
        artwork = self._require_artwork(artwork_id)
        return ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, {}))

    # -- reads: how a work can be re-acquired ---------------------------------

    def list_sources(self, artwork_id: str) -> Sequence[Source]:
        """Every place this work can be obtained from, the primary one first.

        More than one is the point: a work held by several institutions survives
        any one of them reorganising its site, which is what makes re-acquiring
        it from scratch a promise rather than a hope.
        """
        self._require_artwork(artwork_id)
        return self._store.list_sources(artwork_id)

    def get_original(self, artwork_id: str) -> Original | None:
        """The master image this work holds, or None if none has been acquired."""
        self._require_artwork(artwork_id)
        return self._store.get_original(artwork_id)

    def display_fit(self, artwork_id: str, *, box: ArtworkBox) -> FitAssessment:
        """Judge the work's held original against the space it would be rendered into."""
        original = self.get_original(artwork_id)
        if original is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to judge.")
        return assess_display_fit(width=original.width, height=original.height, box=box)

    # -- reads: what has been rendered ----------------------------------------

    def list_renditions(self, artwork_id: str) -> Sequence[RenditionView]:
        """Every derived output for this work, each with whether it is current.

        A stale rendition is one whose source image is no longer the image the
        work holds. It is regenerated rather than served, so saying which are
        stale is the whole reason the parent's hash is carried on the row.

        The verdict comes from `is_current`, which every surface that needs it
        shares — see its docstring for why one home rather than three.
        """
        self._require_artwork(artwork_id)
        original = self._store.get_original(artwork_id)
        return [
            RenditionView(rendition=rendition, stale=not is_current(rendition, original))
            for rendition in self._store.list_renditions(artwork_id)
        ]

    # -- reads: the mat -------------------------------------------------------

    def mat_color_history(self, artwork_id: str) -> Sequence[MatColor]:
        """Every mat colour ever chosen for this work, newest first.

        Superseded choices are kept because mat quality is this product's
        subjective quality bar: "the new model picked a worse colour" has to be
        both answerable and reversible.
        """
        self._require_artwork(artwork_id)
        return self._store.list_mat_colors(artwork_id)

    def current_mat_color(self, artwork_id: str) -> MatColor | None:
        """The mat colour in force, or None if none has been chosen."""
        for mat_color in self.mat_color_history(artwork_id):
            if mat_color.is_current:
                return mat_color
        return None

    def resolve_details(self, artwork_ids: Sequence[str]) -> Sequence[ArtworkDetail]:
        """Return these works in the order given, each with its artist resolved.

        One artist lookup per distinct artist rather than per work: a theme is
        typically many works by few artists, and the caller is building a list to
        put on a wall rather than reading one record.
        """
        artists: dict[str, Artist | None] = {}
        entries: list[ArtworkDetail] = []
        for artwork_id in artwork_ids:
            artwork = self._require_artwork(artwork_id)
            entries.append(ArtworkDetail(artwork=artwork, artist=self._resolve_artist(artwork.artist_id, artists)))
        return entries

    # -- writes: artists and works --------------------------------------------

    def list_artists(self) -> Sequence[Artist]:
        """Every artist held, in a stable order by name."""
        return self._store.list_artists()

    def add_artist(
        self,
        *,
        name: str,
        nationality: str | None = None,
        born: int | None = None,
        died: int | None = None,
        lifespan_text: str | None = None,
        biography: str | None = None,
        family_name: str | None = None,
        given_name: str | None = None,
    ) -> Artist:
        """Record an artist and return it with its minted identity."""
        artist = Artist(
            id=str(uuid.uuid4()),
            name=require_text(name, field="name"),
            nationality=nationality,
            born=born,
            died=died,
            lifespan_text=lifespan_text,
            biography=biography,
            family_name=family_name,
            given_name=given_name,
        )
        store_write(self._store.add_artist, artist)
        return artist

    def name_parts_for(self, artist_id: str, *, family_name: str | None, given_name: str | None) -> Artist:
        """Say which part of a stored artist's name is the family name.

        **The only edit an artist row has, and it exists because the parts
        arrived after the rows did.** Every artist in a seeded catalogue was
        written from a source that gave one undivided name string, and the
        e-paper label needs to lead with the family part — a fact no
        rule over that string can recover for "van Gogh" or "Frank Lloyd Wright".
        So the parts are supplied by whoever knows, to rows that already exist.

        **Narrow on purpose.** A general artist edit would let a caller overwrite
        nationality and dates that came from the holding institution with
        whatever it happened to hold, and nothing asks for that; this touches the
        two fields that were never sourced in the first place. Passing `None` for
        a part clears it, which is what a record that turns out not to be a
        person needs.
        """
        artist = self._store.get_artist(artist_id)
        if artist is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        named = replace(artist, family_name=family_name, given_name=given_name)
        store_write(self._store.update_artist, named)
        return named

    def add_artwork(
        self,
        *,
        title: str,
        artist_id: str | None = None,
        date_created: str | None = None,
        medium: str | None = None,
        dimensions: str | None = None,
        description: str | None = None,
        rights: str | None = None,
        commentary: str | None = None,
    ) -> Artwork:
        """Record a work in the catalogue and return it.

        A work enters the catalogue already accepted — there is no other way
        in. Everything before acceptance is a candidate, which is a separate
        entity with its own verdict, so an artwork never carries a pending or
        rejected state of its own to drift out of step with it.
        """
        if artist_id is not None and self._store.get_artist(artist_id) is None:
            raise ServiceError(f"No artist with id {artist_id!r} is in the catalogue.")
        now = datetime.now(UTC)
        artwork = Artwork(
            id=str(uuid.uuid4()),
            title=require_text(title, field="title"),
            created_at=now,
            status=ArtworkStatus.ACCEPTED,
            artist_id=artist_id,
            date_created=date_created,
            medium=medium,
            dimensions=dimensions,
            # Normalised on the way in, once, rather than by every renderer that
            # ever reads it back out.
            description=description_markup(description),
            rights=rights,
            accepted_at=now,
            # Not passed through `description_markup`: that strips a holding
            # institution's HTML paragraph down to text, and commentary is
            # written for a wall label rather than fetched from anywhere, so
            # there is no markup to take out of it.
            commentary=commentary,
        )
        store_write(self._store.add_artwork, artwork)
        return artwork

    def archive_artwork(self, artwork_id: str) -> Artwork:
        """Take a work out of circulation, keeping its record and its mat history."""
        artwork = self._require_artwork(artwork_id)
        if artwork.status is ArtworkStatus.ARCHIVED:
            raise ServiceError(f"Artwork {artwork_id!r} is already archived.")
        archived = replace(artwork, status=ArtworkStatus.ARCHIVED)
        with self._store.transaction():
            store_write(self._store.update_artwork, archived)
            # A pin naming a work that is out of circulation is an instruction
            # the display plane can never carry out, so archiving withdraws it.
            #
            # This is the one directive write outside the service that owns the
            # directive, and the line it respects is integrity versus semantics:
            # clearing an unsatisfiable reference in the same transaction that
            # creates it, exactly as a dangling reference anywhere else would be.
            # It deliberately does NOT advance the sequence — archiving is not an
            # instruction to the display plane, and an advance would step the wall
            # to an unrelated work. Every rule about what an advance *means* lives
            # in the display service; none of them is duplicated here.
            # Every wall, not the one: a work can be pinned in two rooms at once,
            # and a withdrawal that cleared only the first would leave the second
            # holding an instruction that can never be carried out.
            for directive in self._store.list_directives():
                if directive.pinned_work_id != artwork_id:
                    continue
                # Said out loud: a standing instruction disappearing is exactly the
                # kind of silent state change that turns into "the wall stopped
                # doing what I told it" with nothing to read back.
                log.info("archiving %s withdrew the standing pin naming it on wall %s", artwork_id, directive.wall_id)
                store_write(self._store.set_directive, replace(directive, pinned_work_id=None))
        return archived

    def restore_artwork(self, artwork_id: str) -> Artwork:
        """Return an archived work to circulation.

        Its renditions may have gone stale while it was away; they are checked
        against the held original's hash on every read, so nothing has to
        remember to invalidate them here.
        """
        artwork = self._require_artwork(artwork_id)
        if artwork.status is ArtworkStatus.ACCEPTED:
            raise ServiceError(f"Artwork {artwork_id!r} is not archived.")
        restored = replace(artwork, status=ArtworkStatus.ACCEPTED)
        store_write(self._store.update_artwork, restored)
        return restored

    # -- what a work is -------------------------------------------------------

    def facets_for(self, artwork_id: str) -> Sequence[WorkFacet]:
        """Everything this work is said to be, grouped by kind."""
        self._require_artwork(artwork_id)
        return self._store.list_facets(artwork_id)

    def record_facet(
        self,
        *,
        artwork_id: str,
        kind: VocabularyKind | str,
        value: str,
        derivation: FacetDerivation | str,
        source_note: str | None = None,
    ) -> WorkFacet:
        """Say that a work is one more thing, and where that claim came from.

        `derivation` has no default, deliberately. `sourced` and `inferred` carry
        different authority — one is what a holding institution published, the
        other is what a model decided — and a default would let the caller that
        forgot claim the stronger of the two on every row it wrote. That is the
        same reason `Source.rights_status` has none.

        **Recording a facet a work already has is a no-op, not a refusal.** The
        row is a statement that the work *is* Baroque, and asserting it twice is
        the same statement; a caller re-running an inference pass would otherwise
        have to check first, and the check would be this method. What it does not
        do is overwrite the stored derivation — the first recording of a claim is
        the one whose provenance survives, and a later pass that could silently
        relabel a museum's own value as inferred is the failure the column exists
        to prevent.
        """
        self._require_artwork(artwork_id)
        resolved_kind = require_member(kind, enum=VocabularyKind, field="kind")
        resolved_derivation = require_member(derivation, enum=FacetDerivation, field="derivation")
        resolved_value = require_text(value, field="value")
        # Compared case-insensitively, because `work_facets.value` is COLLATE
        # NOCASE and this check has to agree with the index behind it. An exact
        # comparison here would send "baroque" to a store that already holds
        # "Baroque", turning the documented no-op into a refusal for the same
        # call in different capitals — and inference, the path that will write
        # these, is the documented source of inconsistent casing.
        held = next(
            (
                facet
                for facet in self._store.list_facets(artwork_id)
                if facet.kind is resolved_kind and facet.value.casefold() == resolved_value.casefold()
            ),
            None,
        )
        if held is not None:
            return held
        facet = WorkFacet(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            kind=resolved_kind,
            value=resolved_value,
            derivation=resolved_derivation,
            created_at=datetime.now(UTC),
            source_note=source_note,
        )
        store_write(self._store.add_facet, facet)
        return facet

    def remove_facet(self, artwork_id: str, *, facet_id: str) -> None:
        """Withdraw a claim about a work.

        Takes the work as well as the facet so a caller cannot delete a row off
        another work by holding an id — the same reason `record_original` checks
        that a source belongs to the work it is being recorded against.
        """
        self._require_artwork(artwork_id)
        held = next((facet for facet in self._store.list_facets(artwork_id) if facet.id == facet_id), None)
        if held is None:
            raise ServiceError(f"Artwork {artwork_id!r} has no facet with id {facet_id!r}.")
        store_write(self._store.remove_facet, facet_id)

    # -- writes: sources ------------------------------------------------------

    def add_source(
        self,
        *,
        artwork_id: str,
        url: str,
        provider: str,
        source_class: SourceClass,
        acquisition_method: AcquisitionMethod,
        rights_status: RightsStatus,
        is_primary: bool = False,
        confidence: float | None = None,
        selection_rationale: str | None = None,
    ) -> Source:
        """Record a place this work can be obtained from.

        `rights_status` has no default on purpose. "We did not check" and "we
        checked and could not tell" are different facts, and only the second is
        honest as `unknown` — so the value is always recorded and the caller is
        always the one who decided it.
        """
        self._require_artwork(artwork_id)
        source = Source(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            url=require_text(url, field="url"),
            provider=require_text(provider, field="provider"),
            source_class=require_member(source_class, enum=SourceClass, field="source_class"),
            acquisition_method=require_member(acquisition_method, enum=AcquisitionMethod, field="acquisition_method"),
            rights_status=require_member(rights_status, enum=RightsStatus, field="rights_status"),
            is_primary=is_primary,
            confidence=confidence,
            selection_rationale=selection_rationale,
        )
        with self._store.transaction():
            if is_primary:
                self._demote_primary_sources(artwork_id)
            store_write(self._store.add_source, source)
        return source

    def set_primary_source(self, source_id: str) -> Source:
        """Name the source that produced the held original.

        Which source that is is a single fact about the work, so promoting one
        demotes the rest in the same breath.
        """
        source = self._store.get_source(source_id)
        if source is None:
            raise ServiceError(f"No source with id {source_id!r} is in the catalogue.")
        promoted = replace(source, is_primary=True)
        with self._store.transaction():
            self._demote_primary_sources(source.artwork_id)
            store_write(self._store.update_source, promoted)
        return promoted

    def record_fetch(self, source_id: str, *, status: FetchStatus, at: datetime | None = None) -> Source:
        """Record how the last fetch from this source went.

        `partial_tiles` is a normal dezoomify outcome rather than an error: a
        tile server dropping a few tiles still yields a usable master image.
        """
        source = self._store.get_source(source_id)
        if source is None:
            raise ServiceError(f"No source with id {source_id!r} is in the catalogue.")
        updated = replace(
            source,
            last_fetch_status=require_member(status, enum=FetchStatus, field="status"),
            last_fetched_at=at if at is not None else datetime.now(UTC),
        )
        store_write(self._store.update_source, updated)
        return updated

    # -- writes: originals and renditions -------------------------------------

    def record_original(
        self,
        *,
        artwork_id: str,
        source_id: str,
        path: str,
        width: int,
        height: int,
        byte_size: int,
        content_hash: str,
        fetch_status: FetchStatus | None,
    ) -> Original:
        """Record the master image acquired for this work, replacing any held before.

        Re-acquiring is an edit rather than a mistake — a source is re-fetched
        when it is reorganised or when the first attempt came back partial — so
        this replaces rather than refusing. Renditions made from the previous
        image read as stale immediately afterwards, because they carry the hash
        they were made from.

        **Whether the replacement is an improvement is not decided here.** This
        records what the caller proved; refusing a partial result that would
        overwrite a complete master is the acquisition service's judgement, made
        before any bytes are promoted, because the file on disk and the row have
        to be refused together or the two disagree.

        `fetch_status` has no default, and `None` is a real value rather than an
        omission. It says how the bytes being recorded came back; a default would
        claim `ok` on behalf of every caller that forgot, which is the reading that
        loses images. `None` is what the seed passes, honestly — it ingests files
        the 2024 pipeline left on disk, which this product never fetched and whose
        completeness nothing recorded. Readers treat unrecorded as complete, so the
        seeded corpus is protected without anything having to assert a fact about
        it that nobody checked.
        """
        self._require_artwork(artwork_id)
        source = self._store.get_source(source_id)
        if source is None:
            raise ServiceError(f"No source with id {source_id!r} is in the catalogue.")
        if source.artwork_id != artwork_id:
            raise ServiceError(f"Source {source_id!r} belongs to a different artwork than {artwork_id!r}.")
        if byte_size <= 0:
            # The 2024 pipeline's known download failure: a file that exists,
            # holds nothing, and is indistinguishable from a good one by name.
            raise ServiceError(f"An original cannot be {byte_size} bytes; a zero-length file is a failed download.")
        if width <= 0 or height <= 0:
            raise ServiceError(f"An original must have a positive width and height, got {width}x{height}.")
        if fetch_status is FetchStatus.FAILED:
            # There are no bytes to record for a failed fetch, so a row claiming
            # one is a contradiction rather than an unusual case. Refused here
            # because the value would otherwise be read later as "held quality:
            # failed", against which every subsequent result looks like an
            # improvement — the reading constraint 16 exists to prevent.
            raise ServiceError("An original cannot record a failed fetch; a failed fetch produces no image to hold.")

        with self._store.transaction():
            held = self._store.get_original(artwork_id)
            original = Original(
                id=held.id if held is not None else str(uuid.uuid4()),
                artwork_id=artwork_id,
                source_id=source_id,
                relative_path=relative_path(path, field="path"),
                width=width,
                height=height,
                byte_size=byte_size,
                content_hash=require_text(content_hash, field="content_hash"),
                fetch_status=(
                    None if fetch_status is None else require_member(fetch_status, enum=FetchStatus, field="fetch_status")
                ),
            )
            if held is None:
                store_write(self._store.add_original, original)
            else:
                store_write(self._store.update_original, original)
        return original

    def record_rendition(
        self,
        *,
        artwork_id: str,
        kind: RenditionKind,
        target_width: int,
        target_height: int,
        path: str,
    ) -> Rendition:
        """Record a derived output, stamped with the image it was made from.

        The parent's hash is read here rather than accepted from the caller, so a
        rendition is born current and can only ever become stale by the original
        changing under it. A caller-supplied hash would let a rendition claim a
        parent it was not made from, which is the one thing this column exists to
        make impossible.
        """
        self._require_artwork(artwork_id)
        if target_width <= 0 or target_height <= 0:
            raise ServiceError(f"A rendition must have a positive target size, got {target_width}x{target_height}.")
        with self._store.transaction():
            original = self._store.get_original(artwork_id)
            if original is None:
                raise ServiceError(f"Artwork {artwork_id!r} has no acquired original to render from.")
            resolved_kind = require_member(kind, enum=RenditionKind, field="kind")
            existing = next(
                (
                    candidate
                    for candidate in self._store.list_renditions(artwork_id)
                    if candidate.kind is resolved_kind
                    and candidate.target_width == target_width
                    and candidate.target_height == target_height
                ),
                None,
            )
            rendition = Rendition(
                id=existing.id if existing is not None else str(uuid.uuid4()),
                artwork_id=artwork_id,
                kind=resolved_kind,
                target_width=target_width,
                target_height=target_height,
                relative_path=relative_path(path, field="path"),
                source_content_hash=original.content_hash,
                generated_at=datetime.now(UTC),
            )
            if existing is None:
                store_write(self._store.add_rendition, rendition)
            else:
                store_write(self._store.update_rendition, rendition)
        return rendition

    # -- writes: the mat ------------------------------------------------------

    def record_mat_color(
        self,
        *,
        artwork_id: str,
        hex_rgb: str,
        method: MatMethod,
        lab_l: float | None = None,
        lab_a: float | None = None,
        lab_b: float | None = None,
        reason: str | None = None,
        model_id: str | None = None,
    ) -> MatColor:
        """Choose a mat colour, superseding rather than overwriting the last one.

        `method` is recorded because the fallback is otherwise invisible: the
        2024 pipeline silently substituted a darkened dominant colour whenever
        the vision model failed, so a hand-quality choice and a mechanical one
        looked identical in the data.

        **Re-choosing what is already in force is a no-op, not a new row.** The
        history exists so that "the new model picked a worse colour" is
        answerable and reversible, and a row recording that nothing changed
        answers nothing while making every real change harder to find. Anything
        that runs repeatedly — a re-seed, a re-render — would otherwise grow the
        history by a row per work per run. `method` is part of what "the same
        choice" means: the same hex arrived at by a vision model rather than by
        hand is a different fact about the colour, and worth keeping.
        """
        self._require_artwork(artwork_id)
        resolved_hex = self._require_hex(hex_rgb)
        resolved_method = require_member(method, enum=MatMethod, field="method")
        current = self.current_mat_color(artwork_id)
        if current is not None and current.hex_rgb == resolved_hex and current.method is resolved_method:
            return current
        mat_color = MatColor(
            id=str(uuid.uuid4()),
            artwork_id=artwork_id,
            hex_rgb=resolved_hex,
            method=resolved_method,
            chosen_at=datetime.now(UTC),
            is_current=True,
            lab_l=lab_l,
            lab_a=lab_a,
            lab_b=lab_b,
            reason=reason,
            model_id=model_id,
        )
        with self._store.transaction():
            for previous in self._store.list_mat_colors(artwork_id):
                if previous.is_current:
                    superseded = replace(previous, is_current=False)
                    store_write(self._store.update_mat_color, superseded)
            store_write(self._store.add_mat_color, mat_color)
        return mat_color

    # -- internals ------------------------------------------------------------

    def _demote_primary_sources(self, artwork_id: str) -> None:
        """Clear whichever source currently claims to have produced the original."""
        for other in self._store.list_sources(artwork_id):
            if other.is_primary:
                demoted = replace(other, is_primary=False)
                store_write(self._store.update_source, demoted)

    def _require_artwork(self, artwork_id: str) -> Artwork:
        artwork = self._store.get_artwork(artwork_id)
        if artwork is None:
            raise ServiceError(f"No artwork with id {artwork_id!r} is in the catalogue.")
        return artwork

    def _resolve_artist(self, artist_id: str | None, seen: dict[str, Artist | None]) -> Artist | None:
        if artist_id is None:
            return None
        if artist_id not in seen:
            seen[artist_id] = self._store.get_artist(artist_id)
        return seen[artist_id]

    @staticmethod
    def _parse_terms(q: str | None) -> Sequence[str]:
        """Split a search box into the words that must all appear.

        Whitespace is the only separator, and nothing here is clever about
        quoting or operators: a curator typing `blue harbour` means both words,
        and a query language on a household collection is a thing to learn rather
        than a thing to use.
        """
        if q is None:
            return ()
        terms = q.split()
        if len(terms) > MAX_SEARCH_TERMS:
            raise ServiceError(f"A search takes at most {MAX_SEARCH_TERMS} words, got {len(terms)}.")
        return tuple(terms)

    @staticmethod
    def _parse_facets(facets: Mapping[str, Sequence[str]] | None) -> Mapping[VocabularyKind, Sequence[str]]:
        """Resolve the chosen facet kinds, refusing one this vocabulary does not have.

        A kind is refused rather than ignored: silently dropping an unknown filter
        returns a *wider* result than the caller asked for, which reads as the
        filter having been applied and found this many works.
        """
        if not facets:
            return {}
        parsed: dict[VocabularyKind, Sequence[str]] = {}
        for name, values in facets.items():
            try:
                kind = VocabularyKind(name)
            except ValueError as exc:
                valid = ", ".join(member.value for member in VocabularyKind)
                raise ServiceError(f"Unknown facet {name!r}. Valid facets are: {valid}.") from exc
            chosen = tuple(value for value in values if value.strip())
            if chosen:
                parsed[kind] = chosen
        return parsed

    @staticmethod
    def _parse_status(status: str | None) -> ArtworkStatus | None:
        if status is None:
            return None
        try:
            return ArtworkStatus(status)
        except ValueError as exc:
            valid = ", ".join(sorted(member.value for member in ArtworkStatus))
            raise ServiceError(f"Unknown status {status!r}. Valid values are: {valid}.") from exc

    @staticmethod
    def _require_hex(value: str) -> str:
        text = value.strip().lower()
        if len(text) != 7 or not text.startswith("#") or any(character not in "0123456789abcdef" for character in text[1:]):
            raise ServiceError(f"A mat colour must be a hex triplet like '#27285b', got {value!r}.")
        return text
