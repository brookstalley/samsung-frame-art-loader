"""Which artist a candidate's free-text attribution names, if any we already hold.

A discovered work arrives with `proposed_artist` as free text — whatever the
model wrote — and the catalogue holds `Artist` rows. Deciding whether those name
the same painter is the last step of acceptance, and the only one where being
wrong writes another person's name onto a physical label.

**The two failure directions are not symmetric, and that settles the rule.**
Splitting one painter into two rows costs a duplicate: it is visible in the
catalogue, it can be merged later, and nothing about the works themselves is
wrong meanwhile. Merging two painters into one row attributes a work to someone
who did not paint it, on a label nobody will re-check, and leaves no trace that a
decision was ever made. So a match must be certain, and every uncertain case
splits.

Certain means **exact identity under `dedup.artist_key`** — the same
normalisation the work identity uses, so casefolding, accents, punctuation and a
parenthesised alias are handled once rather than twice. `El Greco (Domenikos
Theotokopoulos)` and `El Greco` are one painter here because they are one painter
there, and if that derivation is ever refined this call site refines with it.

**What that deliberately does not close** is the way names vary and titles do
not: `Jacob Isaacksz van Ruisdael` and `Jacob van Ruisdael` are one painter and
key apart. Every heuristic that would close it was measured against the corpus
and buys the merge direction to do so — reducing a name to its first and last
tokens turns `Hans Holbein the Younger` into `hans younger` — so the split is
taken on purpose. It is taken *visibly*: a name that mints a new row while an
existing row plausibly names the same painter says so, which turns a silent
duplicate into a reported one somebody can act on.

**An empty key is not a key.** `artist_key` returns empty for a name that
normalises to nothing, and it means *unattributed* rather than *no match found*.
Two unattributed works share that empty string, so matching on it would collapse
every unattributed work in the catalogue into one artist named nothing — the
worst reachable merge, and reachable without any name resembling any other. An
unattributed candidate takes no artist at all, which is what `artist_id`'s
nullability is for.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from curation.discovery.dedup import artist_key, clean_name
from curation.persistence.records import Artist


@dataclass(frozen=True, slots=True)
class Attribution:
    """What a candidate's proposed artist resolves to, and what to say about it.

    Exactly one of `matched` and `mint` is set, unless the candidate is
    unattributed, in which case neither is. A caller reading `matched is None` as
    "mint a row" without checking `mint` would invent an artist named nothing for
    every work that names no artist.

    `near_misses` is only ever populated alongside `mint`: it is the reason a
    reader is being told about a new row at all. It is advisory in the strict
    sense — nothing here acted on it, and a caller that ignores it gets the same
    catalogue as a caller that reports it.
    """

    matched: Artist | None
    mint: str | None
    near_misses: Sequence[Artist]

    @property
    def is_unattributed(self) -> bool:
        """Whether the candidate named no artist we can act on."""
        return self.matched is None and self.mint is None


def resolve(proposed_artist: str | None, artists: Sequence[Artist]) -> Attribution:
    """Decide which held artist a proposed name is, or that it is a new one.

    `artists` is every artist the catalogue holds. Keys are derived here rather
    than stored beside the rows on purpose: a stored key is a copy of a
    derivation, and the copy goes stale silently the day the derivation is
    refined — which the work-identity spike has already done once. Deriving on
    read costs a scan of a table that grows by one row per newly-seen painter,
    against a catalogue sized by what fits on one wall.
    """
    if proposed_artist is None:
        return Attribution(matched=None, mint=None, near_misses=())
    key = artist_key(proposed_artist)
    if not key:
        # Normalises to nothing — a decorative dash, punctuation, "n/a". This is
        # the unattributed case and must never be treated as a lookup key.
        return Attribution(matched=None, mint=None, near_misses=())
    for artist in artists:
        if artist_key(artist.name) == key:
            return Attribution(matched=artist, mint=None, near_misses=())
    return Attribution(
        matched=None,
        # The cleaned name rather than the raw text or the key: the key is
        # lowercase and stripped of the accents a name is spelled with, and the
        # raw text may carry the decoration `clean_name` exists to remove. What
        # is stored is what a label renders.
        mint=clean_name(proposed_artist),
        near_misses=_near_misses(key, artists),
    )


def _near_misses(key: str, artists: Sequence[Artist]) -> Sequence[Artist]:
    """Held artists that plausibly name the same painter as this key.

    The test is a shared token that is somebody's *last* token — the position a
    surname occupies in every form this product has seen. `jacob isaacksz van
    ruisdael` and `jacob van ruisdael` share `ruisdael`, which ends both. `hans
    holbein` and `hans memling` share only `hans`, which ends neither, so a
    shared forename does not report every painter who has it.

    **That one condition is the whole rule, and it is why nothing here filters
    tokens by length or against a list of particles.** Both were written and both
    were inert: a particle is never anybody's last token, so `van` shared between
    `vincent van gogh` and `jacob van ruisdael` already fails the test, and
    initials are not last either, so `j m w turner` needs no special case. A
    minimum length is worse than inert — it discards exactly the surnames that
    are short. `wu li` reduces to nothing under a three-character floor and would
    silently never report against `zhang li`, which is the notice failing for
    whole naming traditions while looking correct on every European name.

    Reporting too little is the safe direction here and reporting too much is
    merely noisy, because nothing downstream acts on this: it is a sentence in a
    response, not an argument to a write.
    """
    tokens = key.split()
    if not tokens:
        return ()
    last = tokens[-1]
    found: list[Artist] = []
    for artist in artists:
        other = artist_key(artist.name).split()
        if not other:
            continue
        shared = set(tokens) & set(other)
        if last in shared or other[-1] in shared:
            found.append(artist)
    return tuple(found)
