"""Turning caller input into a storable field, for the fields several entities share.

These rules live here because more than one entity has to obey them and a copy
per entity is a copy that drifts. That holds across services as well as across
entities: a candidate work and a catalogued work both refuse an empty title, and
they refuse it in the same words.
"""

import re
from enum import StrEnum
from html import escape
from html.parser import HTMLParser
from pathlib import PurePosixPath
from typing import Final

from curation.services.errors import ServiceError

#: The only markup the catalogue keeps, and what the tags sources actually send
#: are folded into. The label renderer hands description text to Pango, so
#: anything outside this set is a rendering failure rather than a cosmetic one —
#: and the 2024 code did this substitution inline at render time, which meant
#: every renderer had to remember to.
_EQUIVALENT: Final[dict[str, str]] = {"i": "i", "em": "i", "b": "b", "strong": "b"}

#: Tags that carry no emphasis but do separate text. Dropping them outright would
#: run two paragraphs into one sentence.
_BREAKING: Final[frozenset[str]] = frozenset({"p", "br", "div"})

#: Tags whose *contents* are code rather than prose. Every other unknown tag is
#: unwrapped and its text kept, which is right for `<span>` and wrong for these:
#: a scraped page carrying a script block would otherwise put the script's source
#: on the label, as visible text, with nothing reporting it.
_DISCARDED: Final[frozenset[str]] = frozenset({"script", "style"})

_BLANK_LINES: Final[re.Pattern[str]] = re.compile(r"\n{3,}")


def require_text(value: str, *, field: str) -> str:
    """Accept text with something in it, and nothing else.

    Whitespace is stripped first, so a field holding only spaces is refused
    rather than stored as a value that reads as present and displays as absent.
    """
    text = value.strip()
    if not text:
        raise ServiceError(f"{field} cannot be empty.")
    return text


def require_member[E: StrEnum](value: object, *, enum: type[E], field: str) -> E:
    """Accept the enum member or its string value, and nothing else.

    Callers reach the service layer from a tool or an HTTP handler, where every
    value started as text — so the string form has to work — but an unknown one
    has to fail here rather than reach a column as a value nothing can read back.
    """
    try:
        return enum(value)
    except ValueError as exc:
        valid = ", ".join(sorted(member.value for member in enum))
        raise ServiceError(f"Unknown {field} {value!r}. Valid values are: {valid}.") from exc


def relative_path(value: str, *, field: str) -> str:
    """Check a path is stored the only way the catalogue stores paths.

    Every path in a record is relative to `ART_ROOT`. That is what lets the
    catalogue be copied to a backup, restored on another machine, and read by
    both planes without any of them agreeing on where the art tree sits — and it
    is the fix for a home directory having been baked into the 2024 config. A
    path that climbs out with `..` breaks the same promise as one that starts at
    the root, so both are refused here.
    """
    text = value.strip()
    if not text:
        raise ServiceError(f"{field} cannot be empty.")
    candidate = PurePosixPath(text)
    if candidate.is_absolute():
        raise ServiceError(f"{field} must be relative to ART_ROOT, got the absolute path {text!r}.")
    if ".." in candidate.parts:
        raise ServiceError(f"{field} must stay inside ART_ROOT, but {text!r} climbs out of it.")
    return str(candidate)


def description_markup(value: str | None) -> str | None:
    """Reduce a source's description to the markup the label renderer can take.

    `<em>` and `<strong>` become their Pango equivalents, paragraph and line
    breaks become blank lines, every other tag is dropped, and everything that is
    not one of the two surviving tags is escaped. The output is always balanced,
    because Pango refuses to parse markup that is not and a description that
    arrives with an unclosed tag would otherwise fail at render time — on the
    panel, where nobody is watching.
    """
    if value is None:
        return None
    normaliser = _Normaliser()
    normaliser.feed(value)
    return normaliser.result() or None


class _Normaliser(HTMLParser):
    """Rewrites a fragment into balanced `<i>`/`<b>` markup and escaped text."""

    def __init__(self) -> None:
        # Character references are resolved into the text stream, then escaped
        # again on the way out, so `&amp;` survives as `&amp;` and a bare `&`
        # becomes one rather than reaching Pango as a broken entity.
        super().__init__(convert_charrefs=True)
        self._parts: list[str] = []
        self._open: list[str] = []
        #: How many code elements are open. An unclosed one silences the rest of
        #: the fragment, which is the safe direction to fail.
        self._muted = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _DISCARDED:
            self._muted += 1
            return
        kept = _EQUIVALENT.get(tag)
        if kept is not None:
            self._parts.append(f"<{kept}>")
            self._open.append(kept)
        elif tag in _BREAKING:
            self._parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _DISCARDED:
            self._muted = max(0, self._muted - 1)
            return
        kept = _EQUIVALENT.get(tag)
        if kept is None:
            if tag in _BREAKING:
                self._parts.append("\n\n")
            return
        if kept not in self._open:
            # A closer with no opener: the source's own markup was unbalanced,
            # and echoing it would pass that on to the renderer.
            return
        # Close everything opened inside it as well, innermost first, so that
        # crossed tags come out nested rather than interleaved.
        while self._open:
            innermost = self._open.pop()
            self._parts.append(f"</{innermost}>")
            if innermost == kept:
                break

    def handle_data(self, data: str) -> None:
        if self._muted:
            return
        self._parts.append(escape(data))

    def result(self) -> str:
        """The normalised text, with anything left open closed."""
        self.close()
        while self._open:
            self._parts.append(f"</{self._open.pop()}>")
        collapsed = _BLANK_LINES.sub("\n\n", "".join(self._parts))
        return collapsed.strip()
