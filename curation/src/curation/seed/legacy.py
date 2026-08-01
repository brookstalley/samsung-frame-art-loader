"""Reading the 2024 index — the file the wall running today was curated from.

The index is an **input** to this plane and never a schema it adopts. Records are
parsed into the shapes below and then minted through the catalogue's own service
layer, so nothing here writes and nothing here decides what a valid work is.

**The index's own reading of an artist is not trusted.** It carries both the
source's words (`artist_details`) and its own parse of them
(`artist_nationality`, `creator_born`, `creator_died`), and the two disagree.
Constantin Brancusi's stored death year is 1952 where the source text says 1957 —
1957 is right. The parenthetical form, "Georgia O'Keeffe (American, 1887–1986)",
yielded no nationality at all, and neither did "American, born 1930". So the
source's words win here, and the stored fields fill only what the words do not
carry — which is how an artist with no `artist_details` line still gets a
nationality.

**Per-device state is deliberately not read.** The index carries `tv_content_id`
and `tv_content_thumb_md5`, which are facts about one television rather than
about a work, and `label_file`, whose `_w648_h480` suffix names a panel. None of
the three has a field here to land in.
"""

import json
import re
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Final
from urllib.parse import urlparse

from curation.persistence.records import AcquisitionMethod, SourceClass

#: Where the index's masters and its finished television renders sit under
#: ART_ROOT. Both trees are written by the 2024 pipeline and read by the wall
#: today, so these are observed names rather than a layout chosen here.
RAW_DIRECTORY: Final[str] = "raw"
READY_DIRECTORY: Final[str] = "ready"

#: A four-digit year. Anchored to plausible ones so that a catalogue number or a
#: pixel dimension elsewhere in a clause cannot be read as a date.
_YEAR: Final[re.Pattern[str]] = re.compile(r"\b(1\d{3}|20\d{2})\b")

#: Hosts whose acquisition behaviour the 2024 pipeline established. Both serve
#: tiled gigapixel images and both are fetched with dezoomify, which is the
#: distinction `SourceClass` exists to record — it lets acquisition branch once
#: rather than test a provider string in several places.
_KNOWN_HOSTS: Final[dict[str, str]] = {
    "www.artic.edu": "artic",
    "artsandculture.google.com": "google_arts_culture",
}


class LegacyIndexError(RuntimeError):
    """The index file is not the document this reader knows how to read."""


@dataclass(frozen=True, slots=True)
class ParsedArtist:
    """An artist as the source's own words describe them.

    `lifespan_text` is set only for a form two integers cannot express. Rendered
    from the years alone a living artist reads as "1930–", which looks like a
    missing death date rather than someone who is alive.
    """

    name: str
    nationality: str | None = None
    born: int | None = None
    died: int | None = None
    lifespan_text: str | None = None

    def filled_from(self, other: ParsedArtist) -> ParsedArtist:
        """This artist with anything it does not know taken from another reading.

        Two records for the same artist are not always described equally well —
        one may carry the source's full line and the other only a bare name — and
        an artist row is written once. Merging before any write is what keeps the
        richer reading from depending on which record happened to come first.
        """
        return replace(
            self,
            nationality=self.nationality if self.nationality is not None else other.nationality,
            born=self.born if self.born is not None else other.born,
            died=self.died if self.died is not None else other.died,
            lifespan_text=self.lifespan_text if self.lifespan_text is not None else other.lifespan_text,
        )


@dataclass(frozen=True, slots=True)
class LegacyRecord:
    """One entry of the 2024 index, in the terms the catalogue uses.

    Paths are relative to ART_ROOT, because that is the only way the catalogue
    stores a path — the tree can then be mounted anywhere without a stored value
    becoming wrong.
    """

    url: str
    title: str
    artist: ParsedArtist
    raw_path: str
    ready_path: str
    mat_hex: str
    provider: str
    source_class: SourceClass
    acquisition_method: AcquisitionMethod
    date_created: str | None = None
    medium: str | None = None
    dimensions: str | None = None
    description: str | None = None


def read_index(path: Path) -> Sequence[LegacyRecord]:
    """Parse the index at `path` into records, in the order it lists them.

    Order is preserved because it is the only recency signal the file carries:
    it holds no timestamps, so where two entries describe the same work the later
    one is the only reasonable candidate for the more recent.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LegacyIndexError(f"{path} is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise LegacyIndexError(f"{path} should hold an object, got {type(document).__name__}.")
    entries = document.get("art")
    if not isinstance(entries, list):
        raise LegacyIndexError(f"{path} has no 'art' list of records.")
    default_resize = document.get("default_resize")
    return [_record(entry, index=position, default_resize=default_resize, source=path) for position, entry in enumerate(entries)]


def parse_artist(*, artist: str, details: str | None, nationality: str | None, born: object, died: object) -> ParsedArtist:
    """Read one artist from the source's words, falling back to the index's parse.

    `artist` is the only field always present, and for one record it carries the
    whole clause — "Juan Gris (Spanish, 1887–1927)" — because that record has no
    `artist_details` line at all. So it serves as both the name and, where there
    is nothing better, the description.
    """
    clause = _detail_clause(details, artist)
    parsed_nationality: str | None = None
    parsed_born: int | None = None
    parsed_died: int | None = None
    lifespan_text: str | None = None

    if clause is not None:
        segments = _segments(clause)
        # Everything before the first segment carrying a year is the description
        # of the person; the rest is dates. That keeps "American, born Russia
        # (Latvia)" whole, which is how the holding institution's own label reads,
        # while still finding the years at the end of it.
        first_dated = next((position for position, segment in enumerate(segments) if _YEAR.search(segment)), len(segments))
        if first_dated:
            parsed_nationality = ", ".join(segments[:first_dated])
        years = [int(year) for year in _YEAR.findall(clause)]
        if len(years) >= 2:
            parsed_born, parsed_died = years[0], years[1]
        elif len(years) == 1:
            parsed_born = years[0]
        if parsed_born is not None and parsed_died is None and "born" in clause.lower():
            lifespan_text = f"born {parsed_born}"

    return ParsedArtist(
        name=artist_name(artist),
        nationality=parsed_nationality if parsed_nationality is not None else _text(nationality),
        born=parsed_born if parsed_born is not None else _year(born),
        died=parsed_died if parsed_died is not None else _year(died),
        lifespan_text=lifespan_text,
    )


def artist_name(artist: str) -> str:
    """The artist's name with a description clause taken back out of it.

    Left alone, "Juan Gris (Spanish, 1887–1927)" would be stored as a name and
    printed on the label that way. The year is what tells a description clause
    from an alternate name: "Mark Rothko (Marcus Rothkowitz)" has none, and the
    parenthetical there is part of who the artist is.
    """
    name = artist.strip()
    for parenthetical in _parentheticals(name):
        if _YEAR.search(parenthetical):
            name = name.replace(f"({parenthetical})", " ")
    return " ".join(name.split())


def ready_path_for(raw_file: str, resize_option: str) -> str:
    """Where the 2024 pipeline wrote the finished television render for a master.

    The geometry is deliberately not in this name. The old pipeline encoded a
    panel size into its label filenames and that is why the recovered index
    points at a panel nobody owns any more; the render's real size is measured
    from the file instead.
    """
    stem = PurePosixPath(raw_file).stem
    return f"{READY_DIRECTORY}/{stem}_r{resize_option}.jpg"


def _record(entry: object, *, index: int, default_resize: object, source: Path) -> LegacyRecord:
    if not isinstance(entry, dict):
        raise LegacyIndexError(f"{source} record {index} should be an object, got {type(entry).__name__}.")
    metadata = entry.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    url = _required(entry, "url", index=index, source=source)
    raw_file = _required(entry, "raw_file", index=index, source=source)
    resize_option = _text(entry.get("resize_option")) or _text(default_resize)
    if resize_option is None:
        raise LegacyIndexError(f"{source} record {index} has no resize_option and the file declares no default_resize.")
    provider, source_class, acquisition_method = _acquisition(url)
    return LegacyRecord(
        url=url,
        title=_required(metadata, "title", index=index, source=source),
        artist=parse_artist(
            artist=_required(metadata, "artist", index=index, source=source),
            details=_text(metadata.get("artist_details")),
            nationality=_text(metadata.get("artist_nationality")),
            born=metadata.get("creator_born"),
            died=metadata.get("creator_died"),
        ),
        raw_path=f"{RAW_DIRECTORY}/{raw_file}",
        ready_path=ready_path_for(raw_file, resize_option),
        mat_hex=_required(entry, "mat_hexrgb", index=index, source=source),
        provider=provider,
        source_class=source_class,
        acquisition_method=acquisition_method,
        date_created=_text(metadata.get("date_created")),
        medium=_text(metadata.get("medium")),
        dimensions=_text(metadata.get("dimensions")),
        description=_text(metadata.get("description")),
    )


def _acquisition(url: str) -> tuple[str, SourceClass, AcquisitionMethod]:
    """How a work at this host is obtained, and what kind of place it is.

    An unrecognised host is treated as a plain web page fetched over HTTP rather
    than refused: the classification is a starting point for re-acquisition, and
    guessing that an unknown site serves tiles would send the fetcher down a path
    that cannot work.
    """
    host = urlparse(url).netloc.lower()
    provider = _KNOWN_HOSTS.get(host)
    if provider is None:
        return host or "unknown", SourceClass.CONTEMPORARY_WEB, AcquisitionMethod.DIRECT_HTTP
    return provider, SourceClass.INSTITUTIONAL, AcquisitionMethod.DEZOOMIFY


def _detail_clause(details: str | None, artist: str) -> str | None:
    """The source's description of the artist, reduced to a single clause."""
    text = details if details is not None else artist
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None
    # A parenthetical on the first line is the clause only when it carries a
    # year. Without that test "Mark Rothko (Marcus Rothkowitz)" reads as one and
    # the artist's other name becomes their nationality. Checked before the
    # second line because one record's first line is an attribution — "Designed
    # by Raoul Dufy (French, 1877–1953)" — whose following lines describe the
    # printer rather than the artist.
    for parenthetical in _parentheticals(lines[0]):
        if _YEAR.search(parenthetical):
            return parenthetical.strip()
    if len(lines) > 1:
        return lines[1]
    return None


def _parentheticals(text: str) -> Iterator[str]:
    """Every outermost parenthesised span, contents only.

    Nesting is tracked because one clause has it — "born Russia (Latvia)" sits
    inside a parenthetical of its own — and a reader that stopped at the first
    closing bracket would cut that clause in half.
    """
    depth = 0
    start = 0
    for position, character in enumerate(text):
        if character == "(":
            if depth == 0:
                start = position + 1
            depth += 1
        elif character == ")" and depth:
            depth -= 1
            if depth == 0:
                yield text[start:position]


def _segments(text: str) -> list[str]:
    """Split a clause on its separators, ignoring those inside parentheses."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for character in text:
        if character == "(":
            depth += 1
        elif character == ")" and depth:
            depth -= 1
        if character in ",;" and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(character)
    parts.append("".join(current).strip())
    return [part for part in parts if part]


def _required(source_object: dict[str, Any], field: str, *, index: int, source: Path) -> str:
    value = _text(source_object.get(field))
    if value is None:
        raise LegacyIndexError(f"{source} record {index} has no {field}.")
    return value


def _text(value: object) -> str | None:
    """A field's text, with blank and absent treated alike."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _year(value: object) -> int | None:
    """A year the index stored, which it wrote sometimes as a number and sometimes as text."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    return int(text) if text.isdigit() else None
