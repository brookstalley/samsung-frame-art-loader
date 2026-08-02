"""The work identity that stops discovery re-proposing works a curator declined.

**This derivation is provisional, and deliberately so.** It is the starting
hypothesis for a measurement that has not been made — normalised artist and
title, which is the obvious candidate and not a demonstrated one. It ships ahead
of that measurement because the column it fills is required and phase 1 mints
rows the moment it exists, so waiting would mean either a nullable identity or no
discovery at all.

**Two failure modes are known and unmeasured**, and they pull in opposite
directions. Titles that carry no identity — "Untitled", "Composition", "Study" —
collide works that are not the same work, and one rejection then suppresses a
painting nobody turned down. Titles that vary by translation, date suffix or
punctuation — "Les Demoiselles d'Avignon" against "The Young Ladies of Avignon" —
split one work across two keys, and suppression silently stops working. Which
matters more, and what fixes it, is what real phase-1 output is for.

**Replacing this is a re-key of existing rows, not just a change of function.**
Keys already written under this rule have to be recomputed when the rule changes,
or suppression splits into two regimes and the same work is proposed twice — once
under each. Anything replacing this owes that migration.
"""

import re
import unicodedata

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


def work_dedup_key(*, title: str, artist: str | None = None) -> str:
    """Derive the identity two proposals of the same work should share.

    Case, accents, punctuation and runs of whitespace are all cataloguing
    variation rather than differences between works, so they are normalised away.
    Accents are stripped rather than preserved because a model asked for "Dali"
    and a museum recording "Dalí" mean the same person, and a key that separated
    them would suppress neither.
    """
    return f"{_normalise(artist) or _NO_ARTIST}{_SEPARATOR}{_normalise(title)}"


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
