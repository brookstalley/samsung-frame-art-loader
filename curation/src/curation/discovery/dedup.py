"""The work identity that stops discovery re-proposing works a curator declined.

**Chosen by measurement, against 128 proposals captured from 22 real runs.** The
same intent asked repeatedly returns the same painting under a different name
almost every time, and how often the identity survives that is the only figure
that matters: it is exactly the fraction of a curator's rejections that keep
working. Normalised artist and title alone — the obvious derivation, and the one
that shipped first — held **7 of 36** recurring works together. The rules below
hold **29 of 36**.

**Every rule here answers an observed rewrite, not an imagined one.** In order of
what they recovered:

- *A citation in the title.* Handled before this module sees it, at the engine
  seam, because it corrupts the displayed title too.
- *An appended year.* `Abstraction Blue` came back as `Abstraction Blue (1927)`
  minutes later, from the same model on the same intent. The single largest cause.
- *A cataloguing clause.* `..., from the series Thirty-six Views of Mount Fuji`.
- *An alternate or translated title in parentheses.* `Coquelicots` appeared as
  `(Poppies)`, `(Poppy Field)` and `(The Poppies)` across four runs.
- *A parenthesised alias on the artist.* `El Greco (Domenikos Theotokopoulos)`
  and `El Greco` are one painter.

**A rule for bilingual `Original / English` compounds was written and then
removed**, and the reason is the discipline this module exists to hold. That form
appeared *only* when an intent explicitly asked for titles in both languages —
zero rows in 128 realistic proposals carry it. Which half to keep could not be
decided from evidence either: keeping the first fails the one real case observed
(a Vermeer returned twice under two different original-language names sharing one
English gloss), and keeping the last would have been chosen from that single
observation. A rule that fires on a form the product does not produce, in a
direction nothing supports, can only merge works — the unrecoverable direction —
so it is not worth its risk.

**The two failure directions are not symmetric, and that is what settles every
close call here.** Splitting one work into two identities means the curator is
asked about the same painting twice — irritating, visible, and self-correcting.
Merging two works into one identity means a rejection silently withholds a
painting nobody turned down: the curator is never shown it and never learns it
existed. So a rule earns its place only when it cannot merge distinct works, and
two tempting rules were measured, found to raise the aggregate, and rejected for
exactly that reason:

- *Stripping any trailing parenthetical* would collapse `Abstraktes Bild (742-4)`
  to `Abstraktes Bild`, and Richter painted hundreds under that name.
- *Reducing an artist to first and last name* turns `Hans Holbein the Younger`
  into `hans younger`, discarding the surname that identifies him.

**The seven that still split have two shapes, both known and both left alone
deliberately.**

*Six carry a trailing provenance tail* — `..., ca. 1633-35, The Metropolitan
Museum of Art` — and all six come from proposals where the model volunteered
holding-institution detail. A rule for it was written and measured: it held 31 of
36 while *breaking* a work it had previously held together, truncating `James
Stuart (1612-1655), Duke of Richmond and Lennox` to `James Stuart` by exposing
the sitter's lifespan to the date rule. A rule whose failure mode is silently
shortening a title to two words cannot be trusted with suppression.

*One is a patronymic* — `Jacob Isaacksz van Ruisdael` against `Jacob van
Ruisdael`. Joining them means dropping name tokens, and the rule that does it
turns `Hans Holbein the Younger` into `hans younger`.

Both residuals are asserted by the corpus test, so "the remainder is these two
patterns" fails when it stops being true rather than decaying quietly.

**Replacing this is a re-key of existing rows, not just a change of function.**
Keys already written under an older rule have to be recomputed when the rule
changes, or suppression splits into two regimes and the same work is proposed
twice — once under each. Anything replacing this owes that migration.
"""

import re
import unicodedata

#: An inline markdown link, `[text](url)`. A search-augmented answer cites as it
#: writes and does not confine that to prose: real runs returned titles like
#: `The Night Watch (...) [rijksmuseum.nl](https://...)`.
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(\s*<?[^)\s]*>?\s*\)")

#: A URL that arrived without the markdown wrapper around it.
_BARE_URL = re.compile(r"https?://\S+")

#: Link text that is a hostname rather than words — `artic.edu`,
#: `access-ok.okeeffemuseum.org`. Across 128 captured proposals every citation
#: appearing in a title field looked like this, and not one was part of the name.
_HOSTLIKE = re.compile(r"^[\w-]+(?:\.[\w-]+)+$")

#: What a removed citation leaves hanging: the dash, pipe or comma it was joined on.
_DANGLING_TAIL = re.compile(r"[\s–—,;|/-]+$")

#: Everything that is not a letter, a digit or a space. Punctuation varies with
#: the cataloguer rather than with the work — "Portrait of Madame X" and
#: "Portrait of Madame X." are one painting — so it is dropped rather than
#: normalised, and dropping is what makes the two spellings land on one key.
_NOISE = re.compile(r"[^\w\s]", re.UNICODE)

_WHITESPACE = re.compile(r"\s+")

#: What an artist-less work is keyed under. The brackets are load-bearing rather
#: than decorative: normalisation strips every non-word character, so no real
#: artist name can produce this string — which is what stops a work by an artist
#: actually called "Unattributed" from sharing an identity with every work whose
#: artist phase 1 could not name. A bare word here collides with exactly that.
_NO_ARTIST = "(unattributed)"

#: Between artist and title. Chosen because normalisation has already removed
#: every punctuation mark from both halves, so it cannot appear inside either —
#: which is what stops one (artist, title) pair from being re-read as another.
_SEPARATOR = "::"

#: A year, at the informal precision a catalogue writes one: 1927, c. 1665,
#: ca. 1580.
_YEAR = r"(?:ca?\.?\s*)?(?:1[0-9]{3}|20[0-9]{2})"

#: A trailing parenthetical holding only a date — `(1927)`, `(1950-51)`,
#: `(ca. 1633-35)`. **Trailing only, and that is the whole safety of it.** A date
#: inside a title is frequently the identity: `James Stuart (1612-1655), Duke of
#: Richmond and Lennox` carries the sitter's lifespan, and a rule reaching that
#: would leave two words behind.
_TRAILING_DATE_PAREN = re.compile(rf"\s*\(\s*{_YEAR}\s*(?:[-–—/]\s*(?:{_YEAR}|[0-9]{{2}}))?\s*\)\s*$")

#: The same date trailing without parentheses: `Composition VIII, 1923`.
_TRAILING_DATE_COMMA = re.compile(rf"\s*,\s*{_YEAR}\s*(?:[-–—/]\s*(?:{_YEAR}|[0-9]{{2}}))?\s*$")

#: A cataloguing clause a museum appends and a model repeats inconsistently.
_TRAILING_CLAUSE = re.compile(r",?\s*(?:from the series|also known as)\s.*$", re.IGNORECASE)

#: A trailing parenthetical carrying no digit — an alternate or translated title
#: rather than a catalogue number. `(The Poppies)` yes; `(742-4)` no.
_TRAILING_WORD_PAREN = re.compile(r"\s*\(\s*[^()0-9]*\s*\)\s*$")

#: Any trailing parenthetical, used only on the artist half, where a parenthesis
#: is an alias rather than a way of telling two works apart.
_TRAILING_PAREN = re.compile(r"\s*\([^()]*\)\s*$")

#: Titles naming no work in particular. These are the one place dropping a
#: parenthetical is dangerous rather than helpful: `Untitled (Composition
#: Studies)` reduced to `Untitled` merges every untitled canvas by that artist,
#: and the curator never sees the ones it swallows.
#:
#: **Enumerated and English-only, which is a known limitation in the harmful
#: direction.** A generic title in another language — `Landschaft (Studie)` —
#: reads as distinctive here, so its parenthetical is dropped and two works can
#: merge. Enumeration is nonetheless what there is: length and word count do not
#: separate these from real one-word titles, since `Coquelicots` is as short as
#: `Untitled`. Anything added here should be added because a real proposal
#: carried it, not on the guess that a model might one day emit it.
_UNINFORMATIVE = frozenset(
    {
        "untitled",
        "no title",
        "composition",
        "abstraction",
        "study",
        "sketch",
        "landscape",
        "portrait",
        "self portrait",
        "still life",
    }
)


def clean_name(value: str) -> str:
    """A work's name or an artist's, with citation markup removed.

    Lives here beside the identity it protects, and is applied by both the engine
    seam — which needs it because the markup would otherwise reach the curator's
    review card — and `work_dedup_key` below. Sharing it is not tidiness: the key
    is persisted and indexed, so a caller that reached the derivation with an
    uncleaned title would write a degraded identity that nothing later can tell
    from a good one.

    Idempotent, so applying it at both points costs nothing.

    A citation whose text is a hostname is dropped whole. Keeping the visible
    half leaves `Manhattan (1932) - americanart.si.edu`, which is not the title
    and is worse than either alternative — the date it strands is no longer at the
    end, so no rule that reads a trailing date can reach it. Where the link text
    is words it is kept, since a model that linked the name itself would otherwise
    lose it entirely.

    Deliberately not a general sanitiser: it removes link *syntax*, not
    punctuation, diacritics or parentheses, all of which occur in real titles.
    """

    def unlink(match: re.Match[str]) -> str:
        text = match.group(1).strip()
        return "" if _HOSTLIKE.match(text) else text

    cleaned = _WHITESPACE.sub(" ", _BARE_URL.sub(" ", _MARKDOWN_LINK.sub(unlink, value))).strip()
    return _DANGLING_TAIL.sub("", cleaned).strip()


def work_dedup_key(*, title: str, artist: str | None = None) -> str:
    """Derive the identity two proposals of the same work should share.

    Case, accents, punctuation and runs of whitespace are all cataloguing
    variation rather than differences between works, so they are normalised away.
    Accents are stripped rather than preserved because a model asked for "Dali"
    and a museum recording "Dalí" mean the same person, and a key that separated
    them would suppress neither.
    """
    artist_name = _artist_alias(clean_name(artist) if artist is not None else None)
    return f"{_normalise(artist_name) or _NO_ARTIST}{_SEPARATOR}{_normalise(_canonical_title(clean_name(title)))}"


def _canonical_title(title: str) -> str:
    """The title without the decoration a catalogue adds and a model repeats.

    Applied until it settles, because the forms stack: one proposal arrived as
    `Abstraktes Bild (742-4) (1991)`, where the date has to go and the catalogue
    number has to stay.
    """
    previous = None
    while previous != title:
        previous = title
        title = _TRAILING_CLAUSE.sub("", title).strip()
        title = _TRAILING_DATE_PAREN.sub("", title).strip()
        title = _TRAILING_DATE_COMMA.sub("", title).strip()
        title = _drop_alternate_title(title)
    return title


def _drop_alternate_title(title: str) -> str:
    """Drop a trailing descriptive parenthetical, unless what remains names nothing.

    `Coquelicots (The Poppies)` and `Coquelicots` are one painting under two
    names. `Untitled (Composition Studies)` and `Untitled` are not — the first
    identifies a work and the second identifies none, so collapsing them is the
    merge this refuses to make.
    """
    candidate = _TRAILING_WORD_PAREN.sub("", title).strip()
    if not candidate or candidate == title:
        return title
    if _normalise(candidate) in _UNINFORMATIVE:
        return title
    return candidate


def _artist_alias(artist: str | None) -> str | None:
    """The artist without a parenthesised alias after the name.

    `El Greco (Domenikos Theotokopoulos)` and `El Greco` are one painter. Nothing
    else is removed: a name is short enough that every token in it is doing work,
    and dropping any of them is how two painters become one.
    """
    if artist is None:
        return None
    stripped = _TRAILING_PAREN.sub("", artist).strip()
    return stripped or artist


def _normalise(value: str | None) -> str:
    """Casefold, strip accents, drop punctuation, collapse whitespace."""
    if value is None:
        return ""
    # NFKD splits an accented character into its base and the accent, so
    # discarding combining marks leaves the base letter rather than the whole
    # character. Casefolding after that, because it is the stronger form of
    # lowercasing and handles the cases a museum's own metadata actually carries.
    decomposed = unicodedata.normalize("NFKD", value)
    stripped = "".join(char for char in decomposed if not unicodedata.combining(char))
    return _WHITESPACE.sub(" ", _NOISE.sub(" ", stripped)).strip().casefold()
