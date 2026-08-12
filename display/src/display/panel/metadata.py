"""What a label says, read off a manifest entry.

The first of the three tiers, and the only one shared across display devices: the
same text is arranged differently by a 1448×1072 e-paper panel and by a monitor
drawing into a mat area, but it is the same text.

**Every field is optional, and that is a fact about the corpus rather than
defensive coding.** These works come from museum APIs and from acquisition runs;
a print may have no dimensions, a photograph no medium, an anonymous work no
artist at all. `title` is the only one this product effectively always has, and
even it is absent for untitled works whose institutions record nothing. So the
label is built from what is present and says nothing about what is not — an empty
line where a value is missing would be worse than the missing value.

**Nothing here is escaped for a markup language.** The renderer downstream is
told to treat this as literal text, which is the fix for the injection that a
2024-era label had by construction: it passed description text to Pango markup,
so a title containing `<` produced either mangled type or a parse failure
(`data-model.md`). Escaping here instead would push knowledge of one renderer's
markup into the tier that is supposed to be renderer-agnostic.
"""

from dataclasses import dataclass, fields
from typing import Any


@dataclass(frozen=True, slots=True)
class LabelText:
    """One work's label, as words.

    **The artist leads, and the work follows.** A wall label conventionally opens
    with the title, and on a 6-inch panel read from 7 feet that is what wastes
    it: measured on the panel, a 44-character title at a legible size took 502 px
    of 942 usable and drove the year, the medium and the dimensions off the
    bottom. The family name is seven characters where the title was forty-four,
    so the same facts then fit at a larger size. The ordering the operator asked
    for and the ordering the panel can hold turned out to be the same one
    (`accessibility-spec.md` § The label's content model).

    **Field order here is no longer the label's order** — `lines()` is, and that
    is the change worth noticing before moving a field. The layout tier still
    sizes by position and drops from the end, so `lines()` remains the priority
    ordering; what it stopped being is a straight read-off of these fields, since
    the identification block is now composed from four of them.
    """

    title: str | None = None
    #: What the source called the artist, undivided. Still carried when the parts
    #: below are known, because a display that sets a plain line needs the whole
    #: and a work whose artist has no recorded parts has nothing else.
    artist: str | None = None
    #: Which part of the name is the family name — the part a panel leads with
    #: and sets apart from the rest. Supplied by the catalogue rather than split
    #: out of `artist` here: no rule over one string is right for both "van Gogh"
    #: and "Frank Lloyd Wright", and a display plane guessing at it would be
    #: inventing a fact about a person.
    artist_family_name: str | None = None
    artist_given_name: str | None = None
    artist_nationality: str | None = None
    artist_dates: str | None = None
    date_created: str | None = None
    medium: str | None = None
    dimensions: str | None = None
    #: A line written for a wall label, and the only one that identifies nothing —
    #: which is why it is last, and so the first thing a surface too small for
    #: everything gives up. Not the holding institution's description, which is
    #: paragraphs long and has never been on this label.
    commentary: str | None = None

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing here worth drawing.

        A work with no label text at all is not an error — it is a work whose
        institution published none, and what reaches the panel is a blank surface
        rather than an apology, because a label reading "unknown" beside a picture
        is worse than no label beside a picture.

        **Nothing branches on this**, and that is the design rather than an
        oversight: the empty case needs no special path, because laying out no
        lines and drawing the result reaches the blank surface by the ordinary
        road. This says the same thing about a `LabelText` that `lines()` does,
        in the form a reader asking the question would reach for.
        """
        return not any(self.lines())

    def lines(self) -> tuple[str, ...]:
        """The non-empty values, least-droppable first.

        Not "wall-label order" — this label departs from it twice, knowingly: the
        artist leads the work, and the identification block is one line rather
        than three.

        Whitespace-only values count as absent. They arrive: a museum record with
        a `medium` of `" "` is common enough that treating it as present puts a
        blank line in the middle of every label that has one.
        """
        candidates = (
            self.identification,
            self.title,
            self.date_created,
            self.medium,
            self.dimensions,
            self.commentary,
        )
        return tuple(value.strip() for value in candidates if value is not None and value.strip())

    @property
    def identification(self) -> str | None:
        """Who made this, where they were from and when they lived — as one line.

        **Three lines became one, and on the reference panel that is worth about
        260 px** against a measured slack of roughly 66 px, which makes it the
        single change deciding whether anything optional fits at all. It is also
        what a museum actually prints: name, nationality and life dates are set
        as a single run — "Katsushika Hokusai, Japanese, 1760–1849" — and this
        product spent three line-boxes and their leading saying it.

        **The name is inverted to `FAMILY, Given`, which is an index convention
        rather than a wall-label one, and was chosen knowingly.** On a rotating
        display the family name is the token a passer-by scans from across the
        room, so it leads. The comma after it does double duty — inversion marker
        and list separator — and what is meant to disambiguate the two is weight
        rather than punctuation: with the family name set in bold capitals a
        reader takes `ANDERS` and then everything else, instead of four equal
        comma-separated parts.

        **That weight is not rendered today, and this line is the one place a
        reader would assume otherwise.** Nothing downstream applies a style: the
        contract from here is a flat string per line and one size per block, so
        the panel currently shows four undifferentiated parts. Which is a real
        cost of the collapse rather than a detail — it is recorded as the thing to
        look at in `accessibility-spec.md` § The label's content model, and the
        styled runs it waits on are a deliverable of their own. The ordering is
        settled here regardless, so that whatever applies the weight and whatever
        decides the sizes cannot disagree about which run is which.

        **Falls back to the whole name, unstyled, when neither part is known.**
        An artist with no recorded parts is a fact about the record — an
        anonymous master, a culture, a workshop, or simply a name nobody has
        split yet — and not a licence to guess which word is the family one.
        """
        family = _present(self.artist_family_name)
        given = _present(self.artist_given_name)
        if family is not None and given is not None:
            name: str | None = f"{family}, {given}"
        else:
            # Whichever single part is known stands alone rather than being
            # padded out of `artist`: a label reading "Rembrandt" is correct,
            # and one reading "Rembrandt, Rembrandt Harmenszoon van Rijn" is not.
            name = family or given or _present(self.artist)
        parts = [part for part in (name, _present(self.artist_nationality), _present(self.artist_dates)) if part is not None]
        # No name and no nationality and no dates is an anonymous work, which is
        # a normal record here — the label simply opens with the title.
        return ", ".join(parts) if parts else None


def _present(value: str | None) -> str | None:
    """The value with its whitespace trimmed, or None if there was nothing in it.

    The same rule `lines()` applies, hoisted so that a value which is
    whitespace-only cannot slip into the identification line as an empty
    fragment — which would surface as a stray comma rather than as a short label.
    """
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def read_label(label: dict[str, Any] | None) -> LabelText:
    """Take a manifest entry's label block as text, ignoring anything unrecognised.

    **Unknown keys are dropped rather than rejected.** Curation may publish a
    field this device's version does not know about, and a display plane that
    refused a manifest over one would take the wall down for a change that was
    meant to be additive — against a norm that says a stale manifest is correct
    behaviour rather than degradation.

    Non-string values are dropped for the same reason and with less regret: a
    number where text belongs is curation's bug, and rendering `None` or `17` onto
    a wall label would be this plane repeating it in public.
    """
    if not isinstance(label, dict):
        return LabelText()
    # `fields()` rather than `__slots__`, which happens to hold the same names and
    # holds them only because the decorator was asked for slots — a size and
    # immutability choice, not a declaration of what this reader accepts. Dropping
    # that argument would turn a reader of the manifest into an `AttributeError`.
    known = {field.name: label.get(field.name) for field in fields(LabelText)}
    return LabelText(**{name: value for name, value in known.items() if isinstance(value, str)})
