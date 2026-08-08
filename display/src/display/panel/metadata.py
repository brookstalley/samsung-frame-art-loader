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

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class LabelText:
    """One work's label, as words.

    Ordered as a museum wall label is: who made it, what it is called, when, out
    of what, how big. That order is the layout's default and not its obligation —
    a surface too small for all of it drops from the bottom, which is why the
    least identifying fields sit there.
    """

    title: str | None = None
    artist: str | None = None
    artist_nationality: str | None = None
    artist_dates: str | None = None
    date_created: str | None = None
    medium: str | None = None
    dimensions: str | None = None

    @property
    def is_empty(self) -> bool:
        """Whether there is nothing here worth drawing.

        A work with no label text at all is not an error — it is a work whose
        institution published none. The caller shows an empty surface rather than
        an apology, because a label reading "unknown" beside a picture is worse
        than no label beside a picture.
        """
        return not any(self.lines())

    def lines(self) -> tuple[str, ...]:
        """The non-empty values, in wall-label order.

        Whitespace-only values count as absent. They arrive: a museum record with
        a `medium` of `" "` is common enough that treating it as present puts a
        blank line in the middle of every label that has one.
        """
        candidates = (
            self.title,
            self.artist,
            self.artist_nationality,
            self.artist_dates,
            self.date_created,
            self.medium,
            self.dimensions,
        )
        return tuple(value.strip() for value in candidates if value is not None and value.strip())


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
    known = {field: label.get(field) for field in LabelText.__slots__}
    return LabelText(**{field: value for field, value in known.items() if isinstance(value, str)})
