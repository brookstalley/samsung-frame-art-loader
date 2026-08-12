"""Which part of a seeded artist's name is the family name.

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


def parts_for(name: str) -> tuple[str | None, str | None] | None:
    """The family and given parts of this name, or None if nobody has said.

    The two answers are different and the caller has to be able to tell them
    apart: `(None, None)` is "this record has no name parts", which is settled,
    and `None` is "this table does not cover this name", which is owed.
    """
    return SEEDED_NAME_PARTS.get(name)
