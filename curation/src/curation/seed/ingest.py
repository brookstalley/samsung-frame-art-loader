"""Minting the 2024 index's works into the catalogue, and saying what it cost.

Every write goes through `CatalogueService`, so a work that arrived from the old
index obeys the same constraints as one that arrived from discovery — identity is
a minted UUID, the source URL is an attribute of a source row and never an
identity, and the mat colour supersedes rather than overwrites.

**Silence is not success here.** A record can seed into a work that is missing
its master image, or into a label with no nationality on it, and neither of those
raises anything. So the run returns a report naming every such work with a
reason, and a caller that shows only the count is showing half the result.

**Re-running is expected to be safe and is expected to help.** Nothing here
creates a second work for a record already seeded; what it does instead is fill
in whatever was absent last time. That is what makes the report actionable — it
names a missing render, you put the file in the tree, you run it again, and the
work reaches the wall. A run that only refused to duplicate would report a
problem it gave you no way to fix.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Final

from curation.persistence.records import MatMethod, RenditionKind, RightsStatus
from curation.seed.images import read_image_facts
from curation.seed.legacy import LegacyRecord, ParsedArtist
from curation.seed.names import parts_for
from curation.services.catalogue import MAX_LIST_LIMIT, CatalogueService

log = logging.getLogger(__name__)


class SeedError(RuntimeError):
    """Seeding reached a state its own writes should have made impossible."""


#: What is recorded about where a seeded mat colour came from. The value is the
#: one the wall is running today, arrived at over time by hand; re-deriving it
#: would replace a settled choice with this system's first guess at one.
MAT_REASON: Final[str] = "Carried from the 2024 index as the colour the wall is already running."


class SeedNote(StrEnum):
    """Why a seeded work is worth a curator's attention.

    Each value is something a person would do differently about: an absent
    nationality is a label that will read short, an absent master is
    acquisition's job, and a discarded duplicate is a choice this run made on the
    curator's behalf that they may want to revisit.

    **There is deliberately no note for an absent death year.** Two of these
    artists are alive, so the absence is usually correct, and a report that
    flagged it would list works that are not incomplete — which is the fastest
    way to teach someone to stop reading a report.
    """

    NATIONALITY_ABSENT = "nationality_absent"
    BIRTH_YEAR_ABSENT = "birth_year_absent"
    MEDIUM_ABSENT = "medium_absent"
    DIMENSIONS_ABSENT = "dimensions_absent"
    ORIGINAL_FILE_ABSENT = "original_file_absent"
    ORIGINAL_UNREADABLE = "original_unreadable"
    RENDITION_FILE_ABSENT = "rendition_file_absent"
    RENDITION_UNREADABLE = "rendition_unreadable"
    RENDITION_STALE = "rendition_stale"
    DUPLICATE_RECORD_DISCARDED = "duplicate_record_discarded"
    ARTIST_NAME_PARTS_ABSENT = "artist_name_parts_absent"


#: A sentence per cause, in terms of what it means rather than what it is called.
#: Every member of `SeedNote` has one, which a test enforces — a cause added
#: without a sentence would otherwise reach a curator as a bare enum value.
_DETAIL: Final[dict[SeedNote, str]] = {
    SeedNote.NATIONALITY_ABSENT: "No nationality is known, so its label will read name and dates only.",
    SeedNote.BIRTH_YEAR_ABSENT: "No birth year is known, so its label will carry no artist dates.",
    SeedNote.MEDIUM_ABSENT: "No medium is recorded, so its label will not say what the work is made of.",
    SeedNote.DIMENSIONS_ABSENT: "No physical dimensions are recorded; it still reaches the wall, but its label omits the size.",
    SeedNote.ORIGINAL_FILE_ABSENT: "Its master image is not in the tree at {path}, so it has nothing to render from.",
    SeedNote.ORIGINAL_UNREADABLE: (
        "Its master image at {path} could not be read as a JPEG; a zero-length or truncated file reads this way."
    ),
    SeedNote.RENDITION_FILE_ABSENT: (
        "Its television render is not in the tree at {path}, so it will not reach the wall until one is made."
    ),
    SeedNote.RENDITION_UNREADABLE: (
        "Its television render at {path} could not be read as a JPEG, so its size could not be measured."
    ),
    SeedNote.RENDITION_STALE: (
        "Its television render at {path} was made from an earlier master, so it stays off the wall until the renderer "
        "replaces it — seeding will not adopt a render it did not record, because it cannot tell which master made one."
    ),
    SeedNote.DUPLICATE_RECORD_DISCARDED: (
        "The index describes this work {count} times; the last was taken and the earlier mat colour {discarded} was dropped."
    ),
    SeedNote.ARTIST_NAME_PARTS_ABSENT: (
        "Nothing says which part of {name} is the family name, so its label sets the whole name unstyled; "
        "add a line to curation/src/curation/seed/names.py to have the panel lead with it."
    ),
}


@dataclass(frozen=True, slots=True)
class SeedNoteEntry:
    """One cause, and the sentence a curator reads instead of the enum."""

    note: SeedNote
    detail: str


@dataclass(frozen=True, slots=True)
class SeededWork:
    """What became of one work's worth of index records."""

    url: str
    title: str
    work_id: str
    #: False when the work was already in the catalogue and this run only filled
    #: in what was missing — which is what a second run of the same index does.
    created: bool
    notes: Sequence[SeedNoteEntry] = ()


@dataclass(frozen=True, slots=True)
class SeedReport:
    """What one run did, including — deliberately — what it could not do."""

    records_read: int
    works: Sequence[SeededWork]

    @property
    def created(self) -> Sequence[SeededWork]:
        """Works this run put in the catalogue for the first time."""
        return [work for work in self.works if work.created]

    @property
    def already_present(self) -> Sequence[SeededWork]:
        """Works a previous run had already seeded."""
        return [work for work in self.works if not work.created]

    @property
    def noted(self) -> Sequence[SeededWork]:
        """Works that did not seed cleanly, whatever the reason."""
        return [work for work in self.works if work.notes]

    @property
    def records_collapsed(self) -> int:
        """Records that described a work another record had already described.

        Works plus this accounts for every record read, which is the property
        that makes the report a complete statement about the index rather than a
        list of the parts that went well.
        """
        return self.records_read - len(self.works)


def seed_catalogue(records: Sequence[LegacyRecord], *, catalogue: CatalogueService, art_root: Path) -> SeedReport:
    """Bring every record into the catalogue, and report what each one cost."""
    collapsed = _collapse(records)
    artists = _merge_artists(record for record, _ in collapsed)
    existing = _Existing.of(catalogue)
    # Before the loop, so that rows minted below — which are given their parts at
    # creation — are not written a second time to say what they already say.
    _name_stored_artists(catalogue)

    works: list[SeededWork] = []
    for record, notes in collapsed:
        work_id = existing.urls.get(record.url)
        created = work_id is None
        if work_id is None:
            work_id = _mint(record, catalogue=catalogue, artist=artists[record.artist.name], existing=existing)
        entry = [*notes, *_label_notes(record, artist=artists[record.artist.name])]
        entry.extend(_attach_images(record, work_id=work_id, catalogue=catalogue, art_root=art_root))
        _attach_mat(record, work_id=work_id, catalogue=catalogue)
        works.append(SeededWork(url=record.url, title=record.title, work_id=work_id, created=created, notes=entry))

    report = SeedReport(records_read=len(records), works=works)
    log.info(
        "seeded %d work(s) from %d record(s): %d new, %d already present, %d collapsed, %d with notes",
        len(report.works),
        report.records_read,
        len(report.created),
        len(report.already_present),
        report.records_collapsed,
        len(report.noted),
    )
    return report


def _name_stored_artists(catalogue: CatalogueService) -> int:
    """Give artists already in the catalogue the name parts the table knows.

    **The backfill, and the reason it lives in the ordinary seeding run rather
    than in a command of its own.** Every artist in this catalogue was written
    before the family and given parts existed as fields, from an index that gave
    one undivided string — so the rows are right about everything except the one
    thing the panel now needs. Re-running the seed is already the documented way
    to fill in what a previous run could not (see this module's docstring), and a
    separate one-shot command would be a second thing to remember on the machine
    where it matters and nowhere else.

    Idempotent by comparison rather than by a marker: a row that already says
    what the table says is left untouched, so a second run writes nothing and the
    third writes nothing either. Artists the table does not cover are left alone
    entirely — `_label_notes` reports them per work, which is where a curator is
    already reading.

    **It re-asserts rather than gap-fills, and the difference matters the day
    something else writes these fields.** A row whose parts disagree with the
    table is rewritten, not skipped — which is what makes correcting a wrong
    split a one-line edit here followed by a re-run, and is the only way a
    correction reaches a catalogue that is already seeded. The same rule would
    revert a hand-edited split, which nothing can produce today because no
    surface writes these two fields. Whatever gains one has to rule on which
    outranks the other; until then this table is the sole author.
    """
    named = 0
    for artist in catalogue.list_artists():
        parts = parts_for(artist.name)
        if parts is None or (artist.family_name, artist.given_name) == parts:
            continue
        family, given = parts
        catalogue.name_parts_for(artist.id, family_name=family, given_name=given)
        named += 1
    if named:
        log.info("named %d artist(s) that predated the family and given name fields", named)
    return named


@dataclass(slots=True)
class _Existing:
    """What the catalogue already holds, keyed the two ways seeding asks about it.

    The URL map is a **dedup lookup and not an identity**: it answers "has this
    index record been seeded before", which is a question about a past run rather
    than about what the work is. The work's identity remains the UUID it was
    minted with, and the URL stays where it belongs, on a source row.
    """

    urls: dict[str, str] = field(default_factory=dict)
    artists: dict[str, str] = field(default_factory=dict)

    @classmethod
    def of(cls, catalogue: CatalogueService) -> _Existing:
        """Read the whole catalogue once, rather than query it per record.

        A full scan is affordable because seeding is a one-shot operation over a
        catalogue of this size, and it needs nothing the store does not already
        offer — an index keyed on a source URL would be a second identity for a
        work, which is the thing the model most deliberately does not have.
        """
        existing = cls()
        offset = 0
        while True:
            page = catalogue.list_artworks(limit=MAX_LIST_LIMIT, offset=offset)
            if not page.entries:
                return existing
            for entry in page.entries:
                if entry.artist is not None:
                    existing.artists.setdefault(entry.artist.name, entry.artist.id)
                for source in catalogue.list_sources(entry.artwork.id):
                    existing.urls.setdefault(source.url, entry.artwork.id)
            if not page.truncated:
                return existing
            offset += len(page.entries)


def _collapse(records: Sequence[LegacyRecord]) -> list[tuple[LegacyRecord, list[SeedNoteEntry]]]:
    """Reduce records describing one work to the last of them.

    The index holds two entries for one painting — same URL, same master file,
    same title — differing only in mat colour. Seeding both would put the same
    work in the catalogue twice, which is the one thing a minted identity exists
    to prevent. The index carries no timestamps, so its order is the only signal
    of which choice is the more recent, and the earlier colour is reported rather
    than dropped quietly.
    """
    latest: dict[str, LegacyRecord] = {}
    superseded: dict[str, list[str]] = {}
    order: list[str] = []
    for record in records:
        if record.url in latest:
            superseded.setdefault(record.url, []).append(latest[record.url].mat_hex)
        else:
            order.append(record.url)
        latest[record.url] = record

    collapsed: list[tuple[LegacyRecord, list[SeedNoteEntry]]] = []
    for url in order:
        dropped = superseded.get(url, [])
        notes = (
            [_note(SeedNote.DUPLICATE_RECORD_DISCARDED, count=len(dropped) + 1, discarded=", ".join(dropped))] if dropped else []
        )
        collapsed.append((latest[url], notes))
    return collapsed


def _merge_artists(records: Iterable[LegacyRecord]) -> dict[str, ParsedArtist]:
    """One reading per artist, combining what each record knew about them.

    Merged before anything is written because nothing edits what the *source*
    said about an artist afterwards: without this, how well an artist is
    described would depend on which of their works the index happened to list
    first. The one later write a row does take — `_name_stored_artists` — touches
    only the family and given parts, which no source supplied and this merge
    therefore has nothing to say about.
    """
    merged: dict[str, ParsedArtist] = {}
    for record in records:
        known = merged.get(record.artist.name)
        merged[record.artist.name] = record.artist if known is None else known.filled_from(record.artist)
    return merged


def _mint(record: LegacyRecord, *, catalogue: CatalogueService, artist: ParsedArtist, existing: _Existing) -> str:
    """Create the work, its artist if it is new, and the source it came from."""
    artist_id = existing.artists.get(artist.name)
    if artist_id is None:
        # `(None, None)` for a name the table does not carry, which is the same
        # thing it says about a record that is not a person. The difference
        # between "nobody has said" and "there is nothing to say" is reported to
        # the curator by `_label_notes`; to the row itself they are one state,
        # because the label does the same thing with both.
        family, given = parts_for(artist.name) or (None, None)
        artist_id = catalogue.add_artist(
            name=artist.name,
            nationality=artist.nationality,
            born=artist.born,
            died=artist.died,
            lifespan_text=artist.lifespan_text,
            family_name=family,
            given_name=given,
        ).id
        existing.artists[artist.name] = artist_id

    work = catalogue.add_artwork(
        title=record.title,
        artist_id=artist_id,
        date_created=record.date_created,
        medium=record.medium,
        dimensions=record.dimensions,
        description=record.description,
    )
    catalogue.add_source(
        artwork_id=work.id,
        url=record.url,
        provider=record.provider,
        source_class=record.source_class,
        acquisition_method=record.acquisition_method,
        # Seeding makes no rights judgement. The index records none, and reading
        # one off the host would be inventing a legal conclusion from an address —
        # so every seeded source says the rights are unknown, which is what is
        # true of them.
        rights_status=RightsStatus.UNKNOWN,
        is_primary=True,
    )
    existing.urls[record.url] = work.id
    return work.id


def _label_notes(record: LegacyRecord, *, artist: ParsedArtist) -> list[SeedNoteEntry]:
    """What this work's physical label will be missing when it is set."""
    notes: list[SeedNoteEntry] = []
    # `None` only — a table entry of `(None, None)` is a settled answer about a
    # record that is not a person, and reporting it would ask a curator to supply
    # a surname for the Moche.
    if parts_for(artist.name) is None:
        notes.append(_note(SeedNote.ARTIST_NAME_PARTS_ABSENT, name=artist.name))
    if artist.nationality is None:
        notes.append(_note(SeedNote.NATIONALITY_ABSENT))
    if artist.born is None:
        notes.append(_note(SeedNote.BIRTH_YEAR_ABSENT))
    if record.medium is None:
        notes.append(_note(SeedNote.MEDIUM_ABSENT))
    if record.dimensions is None:
        notes.append(_note(SeedNote.DIMENSIONS_ABSENT))
    return notes


def _attach_images(record: LegacyRecord, *, work_id: str, catalogue: CatalogueService, art_root: Path) -> list[SeedNoteEntry]:
    """Record the master and the finished render, as far as the tree allows."""
    notes: list[SeedNoteEntry] = []
    master = art_root / record.raw_path

    if not master.exists():
        notes.append(_note(SeedNote.ORIGINAL_FILE_ABSENT, path=record.raw_path))
    else:
        facts = read_image_facts(master)
        if facts is None:
            notes.append(_note(SeedNote.ORIGINAL_UNREADABLE, path=record.raw_path))
        else:
            catalogue.record_original(
                artwork_id=work_id,
                source_id=_primary_source_id(catalogue, work_id=work_id, url=record.url),
                path=record.raw_path,
                width=facts.width,
                height=facts.height,
                byte_size=facts.byte_size,
                content_hash=facts.content_hash,
                # Unrecorded, and deliberately not asserted as complete. These
                # files were produced by the 2024 pipeline and are being adopted,
                # not fetched — nothing observed whether their tiles all arrived,
                # and a seed that claimed `ok` would be inventing the fact rather
                # than reading it. Readers treat unrecorded as complete, so the
                # corpus is still protected from a gappy re-fetch replacing it.
                fetch_status=None,
            )

    render = art_root / record.ready_path
    if not render.exists():
        notes.append(_note(SeedNote.RENDITION_FILE_ABSENT, path=record.ready_path))
        return notes
    render_facts = read_image_facts(render)
    if render_facts is None:
        notes.append(_note(SeedNote.RENDITION_UNREADABLE, path=record.ready_path))
        return notes
    # Asked of the catalogue rather than of this run: a work seeded earlier may
    # already hold a master even when this run could not find one, and a render
    # is stamped with the hash of whatever master the work actually has.
    if catalogue.get_original(work_id) is None:
        return notes

    # **A render already recorded is never recorded again.** Recording stamps it
    # with the master's *current* hash, so re-recording one made from an earlier
    # master would declare a superseded acquisition current — and the staleness
    # rule that keeps it off the wall could then never fire for any work a seed
    # run had touched. Leaving it alone lets it read stale, which is what it is.
    held = [view for view in catalogue.list_renditions(work_id) if view.rendition.kind is RenditionKind.TV_DISPLAY]
    if held:
        if any(view.stale for view in held):
            notes.append(_note(SeedNote.RENDITION_STALE, path=record.ready_path))
        return notes

    catalogue.record_rendition(
        artwork_id=work_id,
        kind=RenditionKind.TV_DISPLAY,
        target_width=render_facts.width,
        target_height=render_facts.height,
        path=record.ready_path,
    )
    return notes


def _attach_mat(record: LegacyRecord, *, work_id: str, catalogue: CatalogueService) -> None:
    """Record the mat colour the index carried.

    Re-recording what is already in force is the service's own no-op, so a
    second run of the same index leaves the history exactly where it was.
    """
    catalogue.record_mat_color(artwork_id=work_id, hex_rgb=record.mat_hex, method=MatMethod.MANUAL, reason=MAT_REASON)


def _primary_source_id(catalogue: CatalogueService, *, work_id: str, url: str) -> str:
    """The source row this record's URL was recorded as."""
    for source in catalogue.list_sources(work_id):
        if source.url == url:
            return source.id
    raise SeedError(f"Work {work_id!r} carries no source for {url!r}, which seeding should have created.")


def _note(note: SeedNote, **context: object) -> SeedNoteEntry:
    return SeedNoteEntry(note=note, detail=_DETAIL[note].format(**context))
