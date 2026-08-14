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

**This tier says how its text is set, and that is not the same as knowing a
renderer.** A line arrives as styled runs (`styling.py`) because only here is it
known which characters are the family name and which are the title — a boundary
that is destroyed by joining them into a string and cannot be recovered by
splitting on commas, since a name or a nationality may contain one. What the runs
carry is weight, slant and case; how a device realises those is still entirely
the renderer's business, and the vocabulary is deliberately not one renderer's.
"""

from dataclasses import dataclass, fields
from typing import Any

from display.panel.content import Candidate, Tier
from display.panel.styling import Case, Run, Slant, Weight

#: What separates the facts sharing the identification line. Its own run rather
#: than punctuation glued to the fact after it, so that a tier deciding what to
#: drop or how to size a run is never handed a nationality with a comma stuck to
#: its front.
SEPARATOR = ", "


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

    **Field order here is no longer the label's order** — `candidates()` is, and
    that is the change worth noticing before moving a field. What `candidates()`
    yields is *reading* order, top of the label to the bottom; **priority is the
    tier first and the reading position second**, which is why each fact carries
    a `Tier`. The layout tier no longer sizes by position or drops from the end,
    and a field moved here on the assumption that it does will change which facts
    survive a small surface.
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
        road. This says the same thing about a `LabelText` that `candidates()`
        does, in the form a reader asking the question would reach for.
        """
        return not self.candidates()

    def candidates(self) -> tuple[Candidate, ...]:
        """The non-empty values as styled runs, in reading order, each with its tier.

        Not "wall-label order" — this label departs from it knowingly: the artist
        leads the work.

        **Reading order, and no longer priority order.** This used to return the
        lines least-droppable first, so that a layout dropping from the end needed
        no second ranking. That shortcut broke when the tombstone collapsed into
        one line: nationality and life dates *shared* the leading line, which made
        two droppable facts undroppable and set them at the largest size on the
        label. They have their own line since 2026-08-13, and the ranking outlived
        the arrangement that forced it — priority is a fact's tier first and its
        position second, which is what `Tier` carries and what the engine
        composes, so the title is set below the biography and admitted before it.

        Whitespace-only values count as absent. They arrive: a museum record with
        a `medium` of `" "` is common enough that treating it as present puts a
        blank line in the middle of every label that has one.

        **Runs rather than strings, and that contract had to give.** Two of the
        three typographic decisions this label makes are about *part* of a line —
        the family name set apart from the rest of the name, the
        title set in italic — and a tuple of strings has nowhere to put either.
        The tier below no longer receives text it could only set one way.

        **The mandatory facts are the artist's name and the work's title**, and
        nothing else — the ruling recorded in `content.Tier`. The name is two
        candidates rather than one because the ladder breaks between them: a long
        family name takes a line of its own and lets the given name follow at the
        floor, which costs less height than wrapping the pair at the larger size.
        """
        facts = (
            *self._name_candidates(),
            self._biography_candidate(),
            _fact(self.title, Tier.MANDATORY, slant=Slant.ITALIC),
            _fact(self.date_created, Tier.OPTIONAL),
            _fact(self.medium, Tier.OPTIONAL),
            _fact(self.dimensions, Tier.OPTIONAL),
            _fact(self.commentary, Tier.OPTIONAL),
        )
        return tuple(fact for fact in facts if fact is not None)

    def _name_candidates(self) -> tuple[Candidate, ...]:
        """The artist's name, as the one or two facts the ladder may break between.

        **Two candidates rather than one, and that is what the ladder needs.**
        The name gives up its line before it gives up its size: when
        `KATSUSHIKA, Hokusai` will not hold at the identification tier, the family
        name takes a line of its own and the given name follows at the floor,
        which is cheaper in height than wrapping the pair at the larger size. A
        single candidate could only be wrapped or shrunk.

        **Both parts are mandatory**, so neither is ever dropped — an engine free
        to drop the given name would have a cheaper move available than shrinking,
        and would take it.
        """
        family = _present(self.artist_family_name)
        given = _present(self.artist_given_name)
        if family is None:
            # Whichever single part is known stands alone rather than being
            # padded out of `artist`: a label reading "Rembrandt" is correct,
            # and one reading "Rembrandt, Rembrandt Harmenszoon van Rijn" is not.
            whole = given or _present(self.artist)
            return () if whole is None else (Candidate(runs=(Run(whole),), tier=Tier.MANDATORY, names_the_maker=True),)

        surname = Candidate(
            runs=(Run(family, weight=Weight.BOLD, case=Case.CAPITALS),), tier=Tier.MANDATORY, names_the_maker=True
        )
        if given is None:
            return (surname,)
        return (
            surname,
            Candidate(runs=(Run(given),), tier=Tier.MANDATORY, continues_line=(Run(SEPARATOR),), names_the_maker=True),
        )

    def _biography_candidate(self) -> Candidate | None:
        """Where the artist was from and when they lived, as one line of its own.

        **One fact rather than two, and off the name's line entirely.** Until
        2026-08-13 the nationality and the dates joined the name, which made the
        identification line four comma-separated parts and — because the leading
        line takes the identification tier — set a demonym and a pair of years as
        large as the name itself. Read at the panel, the lifespan came back as
        "too large, equal with the name", and the line breaker split it mid-fact:
        `KATSUSHIKA,` / `Hokusai, Japanese` / `1760–1849`. On its own line it sits
        at the floor by position, which is the museum tombstone and what
        `accessibility-spec.md` § The label's content model now specifies.

        **Joined here rather than left as two joinable candidates**, because a
        joinable fact attaches to whatever line is under construction: with the
        nationality absent or dropped, the dates would have found the *name's*
        line and re-created exactly the arrangement this moved away from. One
        candidate cannot do that. What it costs is the ability to drop half the
        clause, which is a trade worth making — the two are one clause in the
        practice this label follows, and half of one reads as a fault rather than
        as an abbreviation.
        """
        nationality = _present(self.artist_nationality)
        dates = _present(self.artist_dates)
        parts = [part for part in (nationality, dates) if part is not None]
        if not parts:
            return None
        return Candidate(runs=(Run(SEPARATOR.join(parts)),), tier=Tier.OPTIONAL)


def _fact(
    value: str | None,
    tier: Tier,
    *,
    slant: Slant = Slant.UPRIGHT,
) -> Candidate | None:
    """One field as a candidate, or nothing when the field is absent.

    The title is the only caller that passes a slant — titles are set in italic,
    including *Untitled*, which is a museum convention rather than a decision this
    product took. Everything else on a label is a fact about the object and is set
    as recorded.

    **Every fact this builds takes a line of its own**, so it passes no
    `continues_line`. The only joining this label still does is the given name
    onto the family name, which `_name_candidates` composes; the nationality and
    the dates joined here until 2026-08-13, when they moved onto a line of their
    own and became a single candidate.
    """
    present = _present(value)
    if present is None:
        return None
    return Candidate(runs=(Run(present, slant=slant),), tier=tier)


def _present(value: str | None) -> str | None:
    """The value with its whitespace trimmed, or None if there was nothing in it.

    The same rule `candidates()` applies, hoisted so that a value which is
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
