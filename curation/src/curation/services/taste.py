"""What the product has accumulated about the curator, and the rules for writing it.

An affinity is a standing judgment about a thing — an artist, a movement, an era,
a subject, a medium, a palette — retained across conversations and consulted when
discovery proposes. It is the product's memory of its operator, which is why the
whole of this module is about *provenance*: a taste model that cannot say where a
judgment came from is one the curator can only argue with, never fix.

**Every invariant here is enforced on the write path and none of them is stored.**
That is not a stylistic preference, it is a requirement of the deletion ruling:
deleting a conversation nulls `Affinity.source_turn_id`, so `inferred` rows
legally exist with no turn. A `NOT NULL` or a cascading foreign key would make the
delete either impossible or destructive, which is the opposite of what the ruling
asks for — the judgment survives, the citation goes. So the rule lives here, where
it can refuse a *write* without saying anything about a row that already exists.

**`rationale` is what makes that survivable.** It is required for `inferred` and
`observed` because after a delete it is the only evidence left, and an inferred
judgment with neither turn nor rationale is one the product can neither explain
nor revisit.
"""

import logging
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

from curation.persistence.discovery import DiscoveryStore
from curation.persistence.discovery_records import Affinity, AffinityDerivation, AffinitySentiment
from curation.persistence.records import VocabularyKind
from curation.services.errors import ServiceError
from curation.services.fields import require_member, require_text
from curation.services.store import store_write

log = logging.getLogger(__name__)

#: The derivations that must carry a rationale, and why the set is these two.
#: `stated` has the curator's own words as its account and needs no second one;
#: the other two are claims *about* the curator, and after a conversation is
#: deleted the rationale is the only evidence either of them can be left with.
NEEDS_RATIONALE: Final[frozenset[AffinityDerivation]] = frozenset({AffinityDerivation.INFERRED, AffinityDerivation.OBSERVED})

#: How strong a claim each derivation makes about where a judgment came from, so
#: that a weaker one cannot silently overwrite a stronger.
#:
#: **This ordering is the builder's ruling, not a quotation from an artifact**,
#: and it is written here so the next reader argues with the reasoning rather than
#: with a bare dict. `api-contract.md` § `art_taste` fixes what an upsert does to
#: provenance — it replaces it wholesale, and may never keep the old turn under a
#: new judgment — and the build plan additionally requires that `set` "refuses to
#: overwrite provenance with a weaker one". These are the ranks that phrase means:
#: `stated` is the curator's own words, `observed` is their own behaviour as the
#: product recorded it, and `inferred` is a model's reading of what they said.
#: A model may correct its own earlier reading; it may not overwrite what the
#: curator said or did. Equal ranks pass, because a re-inference over an inference
#: is exactly the correction Q14 exists to allow.
_PROVENANCE_RANK: Final[dict[AffinityDerivation, int]] = {
    AffinityDerivation.INFERRED: 1,
    AffinityDerivation.OBSERVED: 2,
    AffinityDerivation.STATED: 3,
}


@dataclass(frozen=True, slots=True)
class AffinityWrite:
    """One judgment as a caller offers it, before anything has been stored.

    Its own type rather than a bag of keyword arguments because two callers — the
    HTTP route and the MCP binding — assemble the identical thing, and the
    validation below is what both of them are for.
    """

    kind: VocabularyKind
    value: str
    sentiment: AffinitySentiment
    open_to_more: bool
    derivation: AffinityDerivation
    rationale: str | None = None
    source_turn_id: str | None = None
    artist_id: str | None = None


def validated_write(
    *,
    kind: object,
    value: str,
    sentiment: object,
    open_to_more: object,
    derivation: object,
    rationale: str | None = None,
    source_turn_id: str | None = None,
    artist_id: str | None = None,
) -> AffinityWrite:
    """Turn what a caller sent into a judgment that may be stored, or refuse it.

    **This is the write path the `inferred ⇒ source_turn_id` invariant lives on**,
    and the only one. It is a function rather than a method so that every future
    writer — the review path that will one day assert `observed`, a rebuild that
    re-derives judgments when the eliciting prompt improves — goes through the
    same checks without having to be a caller of `set_affinity`.

    `sentiment` and `open_to_more` are both required, with no default for either.
    They are two fields precisely so "meh on Magritte, but open to learning more"
    is writable, and the default that reads as safe — do not offer more — is the
    one that silently blacklists an artist the curator asked to keep hearing about.
    """
    chosen_kind = require_member(kind, enum=VocabularyKind, field="kind")
    chosen_sentiment = require_member(sentiment, enum=AffinitySentiment, field="sentiment")
    chosen_derivation = require_member(derivation, enum=AffinityDerivation, field="derivation")
    if not isinstance(open_to_more, bool):
        raise ServiceError(
            f"open_to_more must be true or false, got {open_to_more!r}. It is a separate fact from sentiment: "
            "a lukewarm judgment that is still open to more is the case the two fields exist for."
        )
    named = require_text(value, field="value")

    account = None if rationale is None or not rationale.strip() else rationale.strip()
    if chosen_derivation in NEEDS_RATIONALE and account is None:
        raise ServiceError(
            f"An {chosen_derivation!r} judgment needs a rationale — the account of the judgment in the "
            "curator's terms. Deleting a conversation drops the turn a judgment cites, so this rationale is "
            "the only evidence such a row can be left with."
        )
    if chosen_derivation is AffinityDerivation.INFERRED and source_turn_id is None:
        raise ServiceError(
            "An inferred judgment must cite the conversation turn it was read out of. Write it as 'stated' if "
            "the curator said it themselves — that needs no turn, because their own words are the provenance."
        )
    return AffinityWrite(
        kind=chosen_kind,
        value=named,
        sentiment=chosen_sentiment,
        open_to_more=open_to_more,
        derivation=chosen_derivation,
        rationale=account,
        source_turn_id=source_turn_id,
        artist_id=artist_id,
    )


@dataclass(frozen=True, slots=True)
class AffinityView:
    """A judgment, and the thread a curator can follow back from it.

    `conversation_id` is resolved here rather than stored on the record, because
    the affinity cites a *turn* and a turn already knows its conversation — a
    second copy would be one more thing the delete has to remember to null. It
    is `None` for a judgment that cites nothing, which is every `stated` one and
    every `inferred` one whose conversation has been deleted.

    Resolved in the service rather than in each surface, so a browser link and a
    tool result cannot disagree about which thread produced a judgment.
    """

    affinity: Affinity
    conversation_id: str | None = None


class TasteService:
    """The curator's standing judgments: reading them, correcting them, forgetting one."""

    def __init__(self, store: DiscoveryStore) -> None:
        self._store = store

    # -- reads ----------------------------------------------------------------

    def list_affinities(
        self,
        *,
        kind: object = None,
        sentiment: object = None,
        derivation: object = None,
    ) -> Sequence[AffinityView]:
        """Every judgment, narrowed by any of the three things worth narrowing by.

        Unpaged, and that is a decision rather than an omission: this returns a
        household's entire taste, which is tens of rows. The moment it stops being
        tens, `api-contract.md` § Conditional Patterns' limit-and-report-the-total
        rule is what bounds it, and this method is where that lands.
        """
        found = self._store.list_affinities(
            kind=None if kind is None else require_member(kind, enum=VocabularyKind, field="kind"),
            sentiment=None if sentiment is None else require_member(sentiment, enum=AffinitySentiment, field="sentiment"),
            derivation=(None if derivation is None else require_member(derivation, enum=AffinityDerivation, field="derivation")),
        )
        return [self._viewed(affinity) for affinity in found]

    def get_affinity(self, affinity_id: str) -> AffinityView:
        found = self._store.get_affinity(affinity_id)
        if found is None:
            raise ServiceError(f"No affinity with id {affinity_id!r}.")
        return self._viewed(found)

    def _viewed(self, affinity: Affinity) -> AffinityView:
        """The judgment with the thread its citation belongs to, where there is one.

        A cited turn that is not there is treated exactly as no citation: the
        delete nulls the column rather than leaving a dangling id, so this is
        belt-and-braces — and a link onto a conversation that is gone would be
        worse than no link.
        """
        if affinity.source_turn_id is None:
            return AffinityView(affinity=affinity)
        turn = self._store.get_conversation_turn(affinity.source_turn_id)
        return AffinityView(affinity=affinity, conversation_id=None if turn is None else turn.conversation_id)

    # -- writes ---------------------------------------------------------------

    def set_affinity(
        self,
        *,
        kind: object,
        value: str,
        sentiment: object,
        open_to_more: object,
        derivation: object = AffinityDerivation.STATED,
        rationale: str | None = None,
        source_turn_id: str | None = None,
    ) -> AffinityView:
        """Write one judgment over whatever was there, or write the first one.

        **An upsert, and named `set` for that reason.** A judgment is unique on
        (`kind`, `value`) — one live opinion per thing, corrected in place rather
        than accumulating contradictions the product would then have to arbitrate
        between. `create` would be a lie on the second call and `update` on the
        first.

        **A caller may not write `observed`.** That value means the product read
        the judgment out of accept-and-reject behaviour in review, and only the
        review path can assert it truthfully. An `observed` row written by a
        caller is a fabricated observation, indistinguishable afterwards from one
        the product earned — and Q14's rebuild would then have nothing to rebuild
        from.

        **The upsert replaces the provenance with its own, and never keeps the old
        turn under a new judgment.** A row can already carry a `source_turn_id`
        from an earlier derivation; leaving it in place would produce a row whose
        cited turn did not produce the judgment stored on it, which is
        indistinguishable afterwards from real provenance. What it refuses
        outright is a *weaker* provenance overwriting a stronger one — see
        `_PROVENANCE_RANK`, whose ordering is stated there as a ruling.
        """
        write = validated_write(
            kind=kind,
            value=value,
            sentiment=sentiment,
            open_to_more=open_to_more,
            derivation=derivation,
            rationale=rationale,
            source_turn_id=source_turn_id,
        )
        if write.derivation is AffinityDerivation.OBSERVED:
            raise ServiceError(
                "A judgment cannot be set as 'observed'. That means the product read it out of what was "
                "accepted and rejected in review, which only the review path can say truthfully. Write "
                "'stated' if the curator said it, or 'inferred' with the turn it was read out of."
            )
        if source_turn_id is not None and self._store.get_conversation_turn(source_turn_id) is None:
            raise ServiceError(f"No conversation turn with id {source_turn_id!r}.")

        now = datetime.now(UTC)
        standing = self._store.find_affinity(kind=write.kind, value=write.value)
        if standing is None:
            fresh = Affinity(
                id=str(uuid.uuid4()),
                kind=write.kind,
                value=write.value,
                sentiment=write.sentiment,
                open_to_more=write.open_to_more,
                derivation=write.derivation,
                created_at=now,
                updated_at=now,
                rationale=write.rationale,
                source_turn_id=write.source_turn_id,
            )
            store_write(self._store.add_affinity, fresh)
            log.info(
                "a taste was recorded",
                extra={"event": "taste.set", "kind": str(fresh.kind), "derivation": str(fresh.derivation)},
            )
            return self._viewed(fresh)

        if _PROVENANCE_RANK[write.derivation] < _PROVENANCE_RANK[standing.derivation]:
            raise ServiceError(
                f"This judgment about {write.value!r} is already recorded as {standing.derivation}, and "
                f"{write.derivation} is a weaker claim about where it came from. A model's reading cannot "
                "overwrite what the curator said or did; ask them, and write it as 'stated'."
            )
        corrected = Affinity(
            id=standing.id,
            kind=standing.kind,
            value=standing.value,
            sentiment=write.sentiment,
            open_to_more=write.open_to_more,
            # Provenance is replaced wholesale, `source_turn_id` included. Keeping
            # the old turn under the new judgment is the one shape forbidden here.
            derivation=write.derivation,
            created_at=standing.created_at,
            updated_at=now,
            rationale=write.rationale,
            source_turn_id=write.source_turn_id,
            artist_id=standing.artist_id,
        )
        store_write(self._store.update_affinity, corrected)
        log.info(
            "a taste was corrected",
            extra={"event": "taste.set", "kind": str(corrected.kind), "derivation": str(corrected.derivation)},
        )
        return self._viewed(corrected)

    def delete_affinity(self, affinity_id: str) -> AffinityView:
        """Forget one judgment, and return what was forgotten.

        Returned rather than acknowledged with an id, because this is not
        recoverable and the confirmation a surface reports should name the thing
        that is gone rather than the handle it was addressed by.
        """
        going = self.get_affinity(affinity_id)
        store_write(self._store.delete_affinity, affinity_id)
        log.info("a taste was forgotten", extra={"event": "taste.deleted", "kind": str(going.affinity.kind)})
        return going
