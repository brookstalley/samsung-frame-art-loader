"""Real works from the wall's own catalogue, chosen for the ways they break things.

**Not a sample of the corpus — a sample of its failure modes.** Every record here
is a real one, with the name split the seed table actually stores
(`curation/src/curation/seed/names.py`), because the label's hardest decisions are
all decided by particular words: how long the family name is, whether the
nationality is a demonym, whether there is a title at all. Invented records get
those wrong in the polite direction and a label engine tested only against them
looks correct.

**Copied rather than imported, and the duplication is the architecture.** The
display plane does not depend on the curation plane — it reads a manifest file and
nothing else (`architecture.md` § Direction), and an import across that seam would
be the one place the two planes touched. What these records are *for* is being the
manifest's label blocks, which is exactly what they are: the keys here are
`LabelText`'s fields, so `read_label` takes them unchanged.

The properties in `test_label_properties.py` cross the whole permutation space; these
are the specific records a human would want to look at, and the ones whose
measurements the artifacts quote.

**It ships in the package rather than sitting in the test tree, and the reason is
the second reader.** `tools/label_preview.py` draws these on the real panel — that
is what "records a human would want to look at" means in practice, and it is the
only instrument that can settle legibility. An operator instrument reaching into
`tests/` for its content would break wherever the tests are not present, which is
every deployment that installs the package rather than cloning it. Nothing in the
daemon imports this; what it costs to carry is a few kilobytes of text.
"""

from typing import Final

#: The reference record, and the one every panel measurement in
#: `accessibility-spec.md` was taken against. Long title, long family name set in
#: bold capitals, and every optional field populated — the case where the drop
#: rule and the name ladder both have to act. The name inverts the Western order
#: it appears to follow, so a wrong split is legible as a mistake rather than
#: merely different.
HOKUSAI: Final[dict[str, str]] = {
    "title": "Under the Well of the Great Wave off Kanagawa",
    "artist": "Katsushika Hokusai",
    "artist_family_name": "Katsushika",
    "artist_given_name": "Hokusai",
    "artist_nationality": "Japanese",
    "artist_dates": "1760–1849",
    "date_created": "c. 1830–32",
    "medium": "Colour woodblock print on paper",
    "dimensions": "25.7 × 37.9 cm (10 1/8 × 14 15/16 in.)",
    "commentary": "One of thirty-six views, and the one that outran the series.",
}

#: The short-name case, and the one that proves the ladder is a preference rather
#: than a rule: `O'KEEFFE, Georgia` fits on one line, and an engine told "two
#: lines" would break it for nothing. Also the apostrophe, which is where a
#: character-counting byte offset first goes wrong.
OKEEFFE: Final[dict[str, str]] = {
    "title": "Cow's Skull with Calico Roses",
    "artist": "Georgia O'Keeffe",
    "artist_family_name": "O'Keeffe",
    "artist_given_name": "Georgia",
    "artist_nationality": "American",
    "artist_dates": "1887–1986",
    "date_created": "1931",
    "medium": "Oil on canvas",
    "dimensions": "91.4 × 61 cm (36 × 24 in.)",
}

#: **A culture rather than a person, and the record that has no name parts at
#: all.** The seed table deliberately says nothing about it, so the label falls
#: back to the whole name unstyled — the behaviour a heuristic could not have,
#: since every heuristic would have split this into a family name and a given one.
#: Its nationality is also a *place* rather than a demonym, which
#: `accessibility-spec.md` records as one of the two records where the convention
#: does not hold.
MOCHE: Final[dict[str, str]] = {
    "title": "Stirrup Spout Vessel",
    "artist": "Moche",
    "artist_nationality": "North coast, Peru",
    "date_created": "100 BCE–500 CE",
    "medium": "Ceramic and pigment",
    "dimensions": "24.1 × 14 cm",
}

#: The other record where the nationality is not a demonym — a birthplace clause
#: with no demonym in it at all, and the longest one on the wall. It is what makes
#: the identification line overflow on a record whose name is short.
KANDINSKY: Final[dict[str, str]] = {
    "title": "Painting with Green Center",
    "artist": "Vasily Kandinsky",
    "artist_family_name": "Kandinsky",
    "artist_given_name": "Vasily",
    "artist_nationality": "Born Moscow (formerly Russian Empire, now Russia)",
    "artist_dates": "1866–1944",
    "date_created": "1913",
    "medium": "Oil on canvas",
    "dimensions": "108.9 × 118.4 cm",
}

#: **Three words, and the family name is the last of them** — the record that
#: defeats first-word splitting, where Hokusai defeats last-word. Its title is the
#: longest on the wall, which is the case that decides whether a mandatory fact
#: shrinks or a surface simply refuses it.
WRIGHT: Final[dict[str, str]] = {
    "title": "Triptych Window from the Avery Coonley Playhouse, Riverside, Illinois",
    "artist": "Frank Lloyd Wright",
    "artist_family_name": "Wright",
    "artist_given_name": "Frank Lloyd",
    "artist_nationality": "American",
    "artist_dates": "1867–1959",
    "date_created": "1912",
    "medium": "Leaded glass",
    "dimensions": "224.2 × 109.2 cm",
}

#: The nearly-empty label: an anonymous untitled work, which is the case the fill
#: rule exists for at the other end. A fixed hierarchy leaves most of the panel
#: blank here while it overflows on Hokusai, and both are the same corpus.
ANONYMOUS: Final[dict[str, str]] = {
    "medium": "Albumen print",
    "date_created": "c. 1870",
}

#: A work with a title and nothing else — no artist at all, so the identification
#: line does not exist and the label opens with the work. The case where the
#: leading line is mandatory for a different reason than usual.
UNATTRIBUTED: Final[dict[str, str]] = {
    "title": "Untitled",
    "date_created": "1968",
    "medium": "Gelatin silver print",
}

#: A record whose only artist fact is a nationality — no name, no dates. It is the
#: one that would open with a stray comma if the separator rode the fact *before*
#: the one that needs it, and the reason it does not.
NATIONALITY_ONLY: Final[dict[str, str]] = {
    "title": "Water Jar",
    "artist_nationality": "Japanese",
    "medium": "Stoneware",
}

#: Every record above, for the tests that assert a property across all of them.
#: Named individually as well, because a failure reading "corpus[3]" tells nobody
#: which record broke.
CORPUS: Final[tuple[tuple[str, dict[str, str]], ...]] = (
    ("hokusai", HOKUSAI),
    ("okeeffe", OKEEFFE),
    ("moche", MOCHE),
    ("kandinsky", KANDINSKY),
    ("wright", WRIGHT),
    ("anonymous", ANONYMOUS),
    ("unattributed", UNATTRIBUTED),
    ("nationality-only", NATIONALITY_ONLY),
)
