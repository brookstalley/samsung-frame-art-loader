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
from display.panel.styling import Case, Line, Run, Slant, Weight

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
        return not self.candidates()

    def candidates(self) -> tuple[Candidate, ...]:
        """The non-empty values as styled runs, in reading order, each with its tier.

        Not "wall-label order" — this label departs from it twice, knowingly: the
        artist leads the work, and the identification block is one line rather
        than three.

        **Reading order, and no longer priority order.** This used to return the
        lines least-droppable first, so that a layout dropping from the end needed
        no second ranking. That shortcut broke when the tombstone collapsed into
        one line: nationality and life dates now *share* the leading line, which
        made two droppable facts undroppable and set them at the largest size on
        the label. Priority is a fact's tier first and its position second, which
        is what `Tier` carries and what the engine composes — so the title is set
        below the identification line and admitted before the nationality on it.

        Whitespace-only values count as absent. They arrive: a museum record with
        a `medium` of `" "` is common enough that treating it as present puts a
        blank line in the middle of every label that has one.

        **Runs rather than strings, and that contract had to give.** Two of the
        three typographic decisions this label makes are about *part* of a line —
        the family name set apart from the rest of the identification block, the
        title set in italic — and a tuple of strings has nowhere to put either.
        The tier below no longer receives text it could only set one way.

        **The mandatory facts are the artist's name and the work's title**, and
        nothing else — the ruling recorded in `content.Tier`. The name is two
        candidates rather than one because the ladder breaks between them: a long
        family name takes a line of its own and lets the given name follow at the
        floor, which costs less height than wrapping the pair at the larger size.
        """
        joined = (Run(SEPARATOR),)
        facts = (
            *self._name_candidates(),
            _fact(self.artist_nationality, Tier.OPTIONAL, continues_line=joined),
            _fact(self.artist_dates, Tier.OPTIONAL, continues_line=joined),
            _fact(self.title, Tier.MANDATORY, slant=Slant.ITALIC),
            _fact(self.date_created, Tier.OPTIONAL),
            _fact(self.medium, Tier.OPTIONAL),
            _fact(self.dimensions, Tier.OPTIONAL),
            _fact(self.commentary, Tier.OPTIONAL),
        )
        return tuple(fact for fact in facts if fact is not None)

    @property
    def identification(self) -> Line | None:
        """Who made this, where they were from and when they lived — as one line.

        **The line as it is set when it all fits**, which is what a caller wanting
        to read the tombstone means by it. The engine composes the same facts from
        `candidates()` and may set them across two lines or drop the tail, so this
        is the content rather than the layout.

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
        and list separator — and what disambiguates the two is weight rather than
        punctuation: with the family name set in bold capitals a reader takes
        `ANDERS` and then everything else, instead of four equal comma-separated
        parts.

        **The weight is why this returns runs and not a string.** The bold and the
        capitals apply to a stretch of a line, and the line is composed here
        because this is the last place the boundary is known: downstream, a
        reader looking for where the family name ends has only commas to go on,
        and a name or a nationality may contain one. So the boundary is carried
        rather than re-derived, and whatever sets the weight and whatever decides
        the sizes are looking at the same runs.

        **Only the family name is styled.** A given name standing alone — the
        record has one part and it is not the family one — is set as recorded,
        because bold capitals here mean "this is the family name" and setting a
        given name that way would be a claim about the person rather than about
        the type.

        **Falls back to the whole name, unstyled, when neither part is known.**
        An artist with no recorded parts is a fact about the record — an
        anonymous master, a culture, a workshop, or simply a name nobody has
        split yet — and not a licence to guess which word is the family one.
        """
        name = self._name_runs()
        facts = [_present(self.artist_nationality), _present(self.artist_dates)]
        runs = list(name)
        for fact in facts:
            if fact is None:
                continue
            # The separator is only ever *between* things, so it is appended with
            # the fact that needs it rather than after the one before — which is
            # what leaves an anonymous work's line opening with a stray comma.
            if runs:
                runs.append(Run(SEPARATOR))
            runs.append(Run(fact))
        # No name and no nationality and no dates is an anonymous work, which is
        # a normal record here — the label simply opens with the title.
        return tuple(runs) if runs else None

    def _name_runs(self) -> Line:
        """The artist's name, styled, as it reads when it all fits on one line.

        Composed from the candidates rather than beside them, so the two cannot
        drift: the one-line reading and the two-line one are the same facts and
        the same separator, differing only in whether the engine took the break.
        """
        runs: list[Run] = []
        for candidate in self._name_candidates():
            if runs:
                runs.extend(candidate.continues_line)
            runs.extend(candidate.runs)
        return tuple(runs)

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
            return () if whole is None else (Candidate(runs=(Run(whole),), tier=Tier.MANDATORY),)

        surname = Candidate(runs=(Run(family, weight=Weight.BOLD, case=Case.CAPITALS),), tier=Tier.MANDATORY)
        if given is None:
            return (surname,)
        return (surname, Candidate(runs=(Run(given),), tier=Tier.MANDATORY, continues_line=(Run(SEPARATOR),)))


def _fact(
    value: str | None,
    tier: Tier,
    *,
    slant: Slant = Slant.UPRIGHT,
    continues_line: Line = (),
) -> Candidate | None:
    """One field as a candidate, or nothing when the field is absent.

    The title is the only caller that passes a slant — titles are set in italic,
    including *Untitled*, which is a museum convention rather than a decision this
    product took. Everything else on a label is a fact about the object and is set
    as recorded.

    `continues_line` is passed by the two facts that share the identification
    line, and is what they are set *after* rather than a claim that they will be:
    an engine that could not fit them starts their line instead, and the
    separator is never set.
    """
    present = _present(value)
    if present is None:
        return None
    return Candidate(runs=(Run(present, slant=slant),), tier=tier, continues_line=continues_line)


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
