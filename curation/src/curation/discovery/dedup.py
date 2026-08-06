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
  seam, because it corrupts the displayed title too. Two forms, both real: inside
  markdown, and bare with its URL in brackets after it. The bare one reached a
  curator's review cards seven times before it was recognised.
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
twice — once under each. **That migration is paid by a mechanism rather than by
each change:** `DiscoveryService.reconcile` re-cleans every stored title at
startup and rewrites the key of any it changed, so a rule improved here reaches
rows already on disk. It is idempotent and normally a no-op. The debt was real —
seven rows sat in a catalogue keyed under a citation this module now strips, and
a rejection of any of them would not have suppressed the same painting proposed
cleanly.
"""

import re
import unicodedata
from urllib.parse import urlsplit

#: An inline markdown link, `[text](url)`. A search-augmented answer cites as it
#: writes and does not confine that to prose: real runs returned titles like
#: `The Night Watch (...) [rijksmuseum.nl](https://...)`.
_MARKDOWN_LINK = re.compile(r"\[([^\]]*)\]\(\s*<?[^)\s]*>?\s*\)")

#: A URL that arrived without the markdown wrapper around it.
_BARE_URL = re.compile(r"https?://\S+")

#: A hostname as it appears in running text. The last segment must be alphabetic,
#: which is what a top-level domain is and what a title's own numbering is not:
#: `No.5` and `Op.12` are dot-joined word characters exactly as `tate.org.uk` is,
#: and only the final segment tells them apart.
_HOSTNAME = r"[\w-]+(?:\.[\w-]+)*\.[A-Za-z]{2,}"

#: The same citation written without markdown around the hostname:
#: `blog.artsper.com (https://blog.artsper.com/en/a-closer-look/dali/)`. Seven
#: real proposals carried this, and `_MARKDOWN_LINK` cannot see it — there are no
#: brackets to match, so the hostname is plain text and only the URL was ever
#: removed.
#:
#: The hostname is optional here and the bracketed URL is not, because the URL is
#: the part that is unambiguously not a title. What the optional half costs is
#: covered by `_drop_citation` below, which drops it only when it can prove it.
_BARE_CITATION = re.compile(rf"\s*(?:({_HOSTNAME})\s*)?\(\s*(https?://[^\s)]*)\s*\)?")

#: The same citation after `_BARE_URL` has already eaten it, which is what the
#: catalogue holds: `https?://\S+` is greedy to the next space, so it consumed the
#: `)` that closed the wrapper and left the `(` orphaned — `Lobster Telephone
#: (1938) - cited from tate.org.uk (`. Recognising the damaged form is what lets
#: `reconcile` repair rows written before the rule above existed, rather than
#: needing a one-off script that would then be dead code.
#:
#: **Here the hostname cannot be proved**, because the URL that would have named
#: its host is exactly what the old rule removed. The alphabetic top-level domain
#: is what stands in for that proof, and it is why the shape of `_HOSTNAME`
#: matters more here than above: this rule rewrites rows already on disk, and the
#: only evidence left in one is the shape of the text.
_DAMAGED_CITATION = re.compile(rf"\s*{_HOSTNAME}\s*\($")

#: Link text that is a hostname rather than words — `artic.edu`,
#: `access-ok.okeeffemuseum.org`. Across 128 captured proposals every citation
#: appearing in a title field looked like this, and not one was part of the name.
_HOSTLIKE = re.compile(r"^[\w-]+(?:\.[\w-]+)+$")

#: What a removed citation leaves hanging: the dash, pipe or comma it was joined on.
_DANGLING_TAIL = re.compile(r"[\s–—,;|/-]+$")

#: What a removed citation leaves hanging when the model introduced it in words
#: instead of in punctuation — `- cited from`, `– see`. `_DANGLING_TAIL` reaches
#: the dash but stops at the first letter, so without this the seven real rows
#: read `The Persistence of Memory (1931) - cited from`.
#:
#: **Applied only when a citation was actually removed, never as a blind trailing
#: strip**, because these are ordinary words: Ingres painted `The Source`, and a
#: rule that took the last word off any title ending in one would merge it with
#: `The`. Requiring a citation to have just been dropped is what makes the words
#: evidence rather than coincidence.
_CITATION_LEAD_IN = re.compile(
    r"[\s–—,;|/-]*\b(?:cited|sourced|source|via|see|from|image|images)\b(?:\s+(?:from|at|on|by))?\s*$",
    re.IGNORECASE,
)

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

    **Dropped whole means the words that introduced it too.** A model writes a
    citation two ways — inside markdown, or bare with its URL in brackets after
    it — and either can be joined to the title by prose rather than by a dash.
    Removing only the link left `The Persistence of Memory (1931) - cited from`
    in the catalogue seven times over, which reads as a defect in the title and
    keys as a different painting from the same work proposed cleanly.

    Deliberately not a general sanitiser: it removes link *syntax*, not
    punctuation, diacritics or parentheses, all of which occur in real titles.

    **Order is load-bearing, and it is the only thing keeping the citation rules
    out of a markdown link.** `_BARE_CITATION` matches a bracketed URL with or
    without a hostname in front of it, so it fits `](https://nga.gov/...)` as
    readily as `nga.gov (https://nga.gov/...)`. Running the markdown pass first is
    what means it never sees one: by then the whole link is gone. An earlier draft
    ran them the other way round, took the URL out from under the markdown rule
    and stranded the `[nga.gov]` that rule was the only thing able to recognise,
    which cost ten of the corpus's united works.

    That safety used to live in the pattern — the hostname was mandatory, and `]`
    is not a hostname character — and it was moved into the sequence deliberately.
    A mandatory hostname made `Composition No.5 (https://example.com/x)` clean to
    `Composition`, because a title's last word is dot-joined word characters
    exactly as a hostname is. `_drop_citation` tells those apart by asking the URL
    which host it names, and asking requires matching the URL whether or not a
    hostname precedes it. `test_the_bare_citation_rules_do_not_reach_inside_a_markdown_one`
    is what now holds the order.

    **Can return an empty string**, for a value that was nothing but a citation.
    Callers decide what that means: the engine seam drops the proposal, and
    `reconcile` leaves the stored row alone rather than overwriting a title with
    nothing.
    """
    dropped = False

    def unlink(match: re.Match[str]) -> str:
        nonlocal dropped
        text = match.group(1).strip()
        if _HOSTLIKE.match(text):
            dropped = True
            return ""
        return text

    cleaned = _MARKDOWN_LINK.sub(unlink, value)
    cleaned, bare = _BARE_CITATION.subn(_drop_citation, cleaned)
    cleaned, damaged = _DAMAGED_CITATION.subn(" ", cleaned)
    cleaned = _WHITESPACE.sub(" ", _BARE_URL.sub(" ", cleaned)).strip()
    cleaned = _DANGLING_TAIL.sub("", cleaned).strip()
    if not (dropped or bare or damaged):
        return cleaned
    # Idempotent because this branch is not reached on a second application:
    # there is no citation left to remove, so the words that introduced one are
    # never treated as a lead-in on a value that has already been cleaned.
    return _DANGLING_TAIL.sub("", _CITATION_LEAD_IN.sub("", cleaned)).strip()


def _drop_citation(match: re.Match[str]) -> str:
    """Remove a bracketed URL, and the hostname before it only where it *is* the host.

    **The word before a citation's brackets is not always the citation's.** It is
    the hostname when a model writes `tate.org.uk (https://www.tate.org.uk/...)`,
    and it is the title's own last word when one writes `Composition No.5
    (https://example.com/x)` — both are dot-joined word characters, and taking the
    second leaves `Composition`, which merges every numbered canvas by that
    painter under one identity. That is the failure a curator never sees, so the
    rule is not allowed to guess: the URL names its own host, and the word is
    dropped only when the two agree.

    Agreement is by suffix, because a citation names the site and the URL names
    the server — `tate.org.uk` against `www.tate.org.uk` is one source, not two.
    The bracketed URL goes either way: it is unambiguously not part of a title.

    **A URL that will not parse keeps the word.** `urlsplit` raises on an
    unbalanced `[` or `]` in the authority — it reads one as the start of an IPv6
    address — and a model is as free to emit `(https://tate.org.uk])` as anything
    else. Raising here would be the expensive kind of failure twice over: at the
    engine seam it fails a run that has already been paid for, and inside
    `reconcile` it fails *startup*, for as long as the row is stored, which is a
    plane that will not boot because of one bad title. Unparseable means the
    hostname cannot be proved, and unproved means the word stays.
    """
    named, url = match.group(1), match.group(2)
    if named is None:
        return " "
    try:
        host = urlsplit(url).hostname or ""
    except ValueError:
        return f" {named}"
    site = named.casefold()
    return " " if host == site or host.endswith(f".{site}") else f" {named}"


def title_key(title: str) -> str:
    """The identity of a work's name, with cataloguing variation normalised away.

    One half of `work_dedup_key`, exposed because comparing a *requested* work
    against a *found* one needs the halves separately: a work proposed without an
    artist still has to be recognisable in a museum record that names one, and a
    whole-key comparison would answer no to every such pair.
    """
    return _normalise(_canonical_title(clean_name(title)))


def artist_key(artist: str) -> str:
    """The identity of an artist's name. The other half of `work_dedup_key`.

    Empty for a name that normalises to nothing, which a caller must read as
    "unattributed" rather than as a name that failed to match — the two lead to
    opposite decisions when judging whether a found work is the right one.
    """
    return _normalise(_artist_alias(clean_name(artist)))


def work_dedup_key(*, title: str, artist: str | None = None) -> str:
    """Derive the identity two proposals of the same work should share.

    Case, accents, punctuation and runs of whitespace are all cataloguing
    variation rather than differences between works, so they are normalised away.
    Accents are stripped rather than preserved because a model asked for "Dali"
    and a museum recording "Dalí" mean the same person, and a key that separated
    them would suppress neither.

    Composed from the two halves above rather than deriving its own, so a caller
    comparing halves and a caller comparing keys can never come to disagree about
    what makes two works the same one.
    """
    return f"{(artist_key(artist) if artist is not None else '') or _NO_ARTIST}{_SEPARATOR}{title_key(title)}"


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
