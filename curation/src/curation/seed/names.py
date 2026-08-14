"""What the e-paper label needs to know about a seeded artist and cannot derive.

Two authored lookups: which part of the name is the family name, and the short
form of a nationality the label has no room to print whole. Both exist for the
same reason — the fact is a judgement about a particular person, and every rule
that would produce it is wrong for somebody in this very corpus.


**Authored data, not a rule.** The e-paper label leads with the family name and
sets it apart from the rest, so it has to know which part that is — and the 2024
index stores one undivided string per artist. Every heuristic over that string is
wrong for some name in this very corpus: "Frank Lloyd Wright" defeats last-word,
"Georgia O'Keeffe" defeats first-word, "Katsushika Hokusai" inverts the order it
looks like it follows, and "Moche" is not a person. The surname heuristic in
`discovery/artic.py` documents the same unreliability from the other end.

So the split is written down, once, for the names the 2024 corpus actually holds.
It is a lookup rather than an algorithm on purpose: a lookup can be read and
corrected by whoever notices a wrong one on the wall, and it says nothing at all
about a name it does not contain — which is the behaviour a guess cannot have.

**A name absent from this table is not an error.** It gets no parts, the label
falls back to the whole name unstyled, and `ingest` reports it so that whoever
added a work knows a line of this file is owed. That is the same outcome as a
record that is not a person, and deliberately so: both are "nobody has said",
and the label's job in both cases is to print what it was given rather than to
improvise a hierarchy.
"""

from typing import Final

#: Index name → (family name, given name). `None` means the record has no such
#: part rather than that it is unknown — a culture, a workshop, an anonymous
#: master. The label treats the two identically, because a name it cannot split
#: and a name with nothing to split are the same fact to a typesetter.
#:
#: Ordering follows the 2024 index so a reader can diff this against it.
SEEDED_NAME_PARTS: Final[dict[str, tuple[str | None, str | None]]] = {
    "Charles Demuth": ("Demuth", "Charles"),
    "Joan Miró": ("Miró", "Joan"),
    "Georgia O'Keeffe": ("O'Keeffe", "Georgia"),
    "Constantin Brancusi": ("Brancusi", "Constantin"),
    # Three given names' worth of usage, one family name. Last-word is right
    # here and wrong two rows down, which is the whole argument for the table.
    "Frank Lloyd Wright": ("Wright", "Frank Lloyd"),
    "Mark Rothko": ("Rothko", "Mark"),
    "Harry Callahan": ("Callahan", "Harry"),
    "Jasper Johns": ("Johns", "Jasper"),
    "Ellsworth Kelly": ("Kelly", "Ellsworth"),
    "Paul Klee": ("Klee", "Paul"),
    "Arthur Dove": ("Dove", "Arthur"),
    "Raoul Dufy": ("Dufy", "Raoul"),
    "Josef Albers": ("Albers", "Josef"),
    "Robert Gober": ("Gober", "Robert"),
    "Clyfford Still": ("Still", "Clyfford"),
    "Victor Vasarely": ("Vasarely", "Victor"),
    "Ana Elisa Egreja": ("Egreja", "Ana Elisa"),
    "Juan Gris": ("Gris", "Juan"),
    "René Magritte": ("Magritte", "René"),
    "Vasily Kandinsky": ("Kandinsky", "Vasily"),
    # Japanese order: the family name leads. Reading the last word as the family
    # name would set HOKUSAI where the catalogues of every institution holding
    # him — and the Library of Congress heading — set Katsushika.
    "Katsushika Hokusai": ("Katsushika", "Hokusai"),
    "Pierre Andrieu": ("Andrieu", "Pierre"),
    "Pierre-Auguste Renoir": ("Renoir", "Pierre-Auguste"),
    "Salvador Dalí": ("Dalí", "Salvador"),
    # A pre-Columbian culture, not a person. Neither part, so the label prints
    # "Moche" whole and unstyled rather than inventing a surname for a people.
    "Moche": (None, None),
    "John Steuart Curry": ("Curry", "John Steuart"),
    "Franz Kline": ("Kline", "Franz"),
    "Alexander Calder": ("Calder", "Alexander"),
    "Marilyn Minter": ("Minter", "Marilyn"),
    "Jeff Koons": ("Koons", "Jeff"),
    "Piet Mondrian": ("Mondrian", "Piet"),
}


#: Index name → the short nationality the e-paper label sets for them.
#:
#: **Authored for the same reason the split above is**, and covering only the
#: names that need it. What a holding institution prints under "nationality" is
#: prose: of the seeded corpus's 27 recorded nationalities, 22 are already
#: demonyms and five are not. Four of those five overflow the label's biography
#: line at the panel's floor size, so they are shortened here; the fifth, Moche's
#: "North coast, Peru", fits and is left exactly as recorded.
#:
#: **A short form, not a correction.** The recorded string stays in the catalogue
#: — it is the provenance, and it says things the short form does not. What is
#: chosen here is the leading claim: the institution's own first word about where
#: the artist was from, which is what a wall label has room to say.
#:
#: **Nothing derives these.** "Born Moscow (formerly Russian Empire, now Russia)"
#: → "Russian" is a judgement about a person, and a rule that made it would be
#: inventing a fact — the same reason the name split is a table.
SEEDED_DISPLAY_NATIONALITIES: Final[dict[str, str]] = {
    # 49 characters, the longest on the wall, and the record that forced this
    # table: set with the life dates it sets a line nearly three times the panel.
    "Vasily Kandinsky": "Russian",
    # The three "X, born Y" forms. The comma is the problem as much as the
    # length — on a line that already separates nationality from dates with one,
    # it reads as a third list item rather than as a qualification.
    "Mark Rothko": "American",
    "Paul Klee": "German",
    "Constantin Brancusi": "French",
}


def parts_for(name: str) -> tuple[str | None, str | None] | None:
    """The family and given parts of this name, or None if nobody has said.

    The two answers are different and the caller has to be able to tell them
    apart: `(None, None)` is "this record has no name parts", which is settled,
    and `None` is "this table does not cover this name", which is owed.
    """
    return SEEDED_NAME_PARTS.get(name)


def display_nationality_for(name: str) -> str | None:
    """The short nationality this artist's label sets, or None to use the recorded one.

    One answer rather than two, unlike `parts_for`: a name this table does not
    carry and a nationality that needs no shortening are the same instruction to
    the label — set what the catalogue recorded.
    """
    return SEEDED_DISPLAY_NATIONALITIES.get(name)
