"""The words the client has for the states the server can send it.

The browser renders enum values as sentences a curator acts on — "no wired
collection holds it" rather than `not_held`. A value with no entry in those maps
falls through to the raw token, which is a diagnostic label leaking onto a
screen: readable to whoever wrote the enum, meaningless to the person deciding
whether to re-search.

So the maps are checked against the enums rather than trusted. This is the same
bargain `test_design_tokens.py` strikes with the stylesheet: the client is not a
Python module and nothing else would notice the day a sixth reason is added, so
the check reads the real files — every module the client is built from. A member added without a sentence fails here,
which is the point at which it is cheap to write one.
"""

import re
import shutil
import subprocess

import pytest

from curation.discovery.conversation import SUGGESTION_KINDS
from curation.http.pages import STATIC_DIR
from curation.persistence.discovery_records import (
    AffinityDerivation,
    AffinitySentiment,
    ResolutionStatus,
    RunStatus,
    TurnRole,
    UnresolvedReason,
    Verdict,
    WorkProvenance,
)
from curation.persistence.records import VocabularyKind

#: Every module the client is made of, boot and `core/` and `screens/` alike.
#:
#: Sorted so the concatenation below is stable, and gathered by glob rather than
#: listed: the client became a tree of ES modules when the navigation was
#: reshaped, and a hand-written list is a list that stops including the newest
#: screen — silently, since every check here would go on passing against the
#: modules it still knew about.
CLIENT_PATHS = sorted(STATIC_DIR.rglob("*.js"))

#: The whole client as one text. Every check below asks "does the client say
#: this", which was one file's question and is now the tree's; concatenating is
#: what keeps the question the same one after the split.
CLIENT = "\n".join(path.read_text(encoding="utf-8") for path in CLIENT_PATHS)


def test_the_client_is_more_than_one_module():
    """The glob found a tree, so every check below reads the whole client.

    A `rglob` that matched one file — or none — would leave these checks passing
    against whatever it happened to find, which is the failure mode that made the
    hand-written list unacceptable in the first place. This is the assertion that
    the gathering worked.
    """
    names = {path.relative_to(STATIC_DIR).as_posix() for path in CLIENT_PATHS}
    assert "app.js" in names, "the client's boot module is missing from what these checks read"
    assert any(name.startswith("core/") for name in names), "no core module was gathered"
    assert any(name.startswith("screens/") for name in names), "no screen module was gathered"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed; this check is opportunistic")
@pytest.mark.parametrize("path", CLIENT_PATHS, ids=lambda path: path.name)
def test_the_client_parses(path):
    """A syntax error here kills the entire browser surface and no other test notices.

    Every Python test asserts what the *server* sends and that the script is
    served; none of them runs a line of it. So a stray brace ships a page that
    loads, fetches nothing, and shows the "Loading the catalogue…" placeholder
    forever, against a fully green suite — the shape of failure this product
    exists to refuse.

    **Per module, not over the concatenation.** Two files joined end to end parse
    as neither of them — an unbalanced brace in the first would be closed by the
    second and the check would pass on a client that cannot load.

    **This is a check, not a toolchain.** It shells out to whatever `node`
    happens to be on the machine and skips when there is none, so it adds no
    dependency and no build step, and the deliberate decision against a Node
    toolchain on a Pi is untouched. It cannot say the client is *correct* — only
    that it is parseable, which is the cheapest fact worth having about a file
    nothing else executes.
    """
    result = subprocess.run(
        ["node", "--check", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"{path.name} does not parse:\n{result.stderr}"


def _literal_body(name: str) -> str:
    """The raw text inside a top-level `const <name> = { ... }` object literal.

    The two readers below both strip or extract before they answer; this is what
    is left for a literal whose values are neither bare identifiers nor strings.
    Brace-counted for the reason they are: a non-greedy pattern stops at the
    first `}` and silently reads a truncated object, and a check that reads half
    its input passes for the wrong reason.
    """
    opening = re.search(rf"^(?:export )?const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
    assert opening, f"the client has no top-level `const {name} = {{`"
    start = opening.end()
    depth = 0
    for index in range(start, len(CLIENT)):
        if CLIENT[index] == "{":
            depth += 1
        elif CLIENT[index] == "}":
            depth -= 1
            if depth == 0:
                return CLIENT[start + 1 : index]
    raise AssertionError(f"`{name}` is never closed")


def _object_keys(name: str) -> set[str]:
    """The keys of a top-level `const <name> = { ... }` object literal in the client.

    Brace-counted rather than matched with a non-greedy regex, for the reason
    recorded in `test_design_tokens.py`: a pattern that stops at the first `}`
    silently reads a truncated object, and a check that reads half its input
    passes for the wrong reason.
    """
    opening = re.search(rf"^(?:export )?const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
    assert opening, f"the client has no top-level `const {name} = {{`"
    start = opening.end()
    depth = 0
    for index in range(start, len(CLIENT)):
        if CLIENT[index] == "{":
            depth += 1
        elif CLIENT[index] == "}":
            depth -= 1
            if depth == 0:
                # String values are removed before keys are looked for. The
                # sentences in these maps are prose, and prose acquires a colon
                # eventually — at which point a scan of the raw body would report
                # a key that does not exist and fail against a correct client.
                body = re.sub(r'"(?:[^"\\]|\\.)*"', '""', CLIENT[start + 1 : index])
                return set(re.findall(r"([A-Za-z_][A-Za-z0-9_]*)\s*:", body))
    raise AssertionError(f"`{name}` is never closed")


def _object_values(name: str) -> dict[str, str]:
    """The `key: "string"` pairs of a top-level `const <name> = { ... }` literal.

    The sibling above deliberately strips string values before reading keys, so
    it cannot answer "does this key have words behind it" — which is a separate
    failure and, until this existed, an unchecked one: a map with the right key
    set and an empty value renders a badge with nothing in it, and every keys
    test stays green.
    """
    opening = re.search(rf"^(?:export )?const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
    assert opening, f"the client has no top-level `const {name} = {{`"
    start = opening.end()
    depth = 0
    for index in range(start, len(CLIENT)):
        if CLIENT[index] == "{":
            depth += 1
        elif CLIENT[index] == "}":
            depth -= 1
            if depth == 0:
                body = CLIENT[start + 1 : index]
                return dict(re.findall(r'([A-Za-z_][A-Za-z0-9_]*)\s*:\s*"((?:[^"\\]|\\.)*)"', body))
    raise AssertionError(f"`{name}` is never closed")


@pytest.mark.parametrize("name", ["REASON_SENTENCES", "REASON_WORDS"])
def test_every_unresolved_reason_has_words_for_a_curator(name):
    """A run that resolved nothing has to say which kind of nothing, in English.

    Chunk-independent statement of the requirement: the reason exists so a
    curator knows whether to re-search, re-word the intent, or accept that the
    work may not exist — and only one of the five points at the last of those.
    A raw `identity_refused` on the page communicates none of that.
    """
    assert _object_keys(name) == {str(reason) for reason in UnresolvedReason}


def test_every_resolution_status_has_words_for_a_curator():
    assert _object_keys("RESOLUTION_WORDS") == {str(status) for status in ResolutionStatus}


@pytest.mark.parametrize("name", ["RESOLUTION_WORDS", "REASON_WORDS", "REASON_SENTENCES"])
def test_every_phrase_a_curator_reads_actually_has_words_in_it(name):
    """Right keys, empty value: a badge that renders nothing and passes every keys test.

    The keys checks above strip string values before reading keys, so none of
    them can see this. A mutation sweep emptying `RESOLUTION_WORDS.pending`
    survived all three suites — the browser tests assert the two entries that
    were reworded, and nothing looked at the third.

    Asserted over every map rather than the one the sweep found, because the
    hole is in the *shape* of the keys checks and applies to all of them
    equally.
    """
    values = _object_values(name)
    assert values, f"`{name}` parsed to no string values at all — this guard would pass vacuously"

    empty = sorted(key for key, phrase in values.items() if not phrase.strip())
    assert not empty, f"{name} carries {empty} with no words behind them; each renders as an empty badge"


def test_every_run_status_is_named_in_the_client():
    """`runSentence` says what a run's state means, and it must cover all of them.

    **A weaker check than the maps above, deliberately, and worth being exact
    about what it does and does not prove.** The sentences are an if-chain rather
    than an object literal because several branches read the tally, the run kind
    and whether image resolution is wired — they are not one-liners and a map of
    bare strings could not hold them. So this asserts only that each status value
    appears somewhere in the client, not that it has a branch, nor that the
    branch is right.

    What it does buy is the property that matters: a tenth `RunStatus` added to
    the enum fails here, at the moment it is cheap to write a sentence for.
    Without it the fallback renders "This run is halted_by_something." — a raw
    diagnostic token in the one sentence on the page that exists to tell a
    curator what happened and what to do about it.
    """
    for status in RunStatus:
        assert f'"{status}"' in CLIENT, f"the client has no sentence naming the {status} state"


def test_every_turn_role_has_a_name_a_reader_would_recognise():
    """The transcript labels each turn with who said it, and both roles need words.

    Same bargain as the run statuses above: without it a third role would render
    as its own enum value beside the sentence it introduces — `system` above a
    reply, which reads as a fault rather than as an answer.
    """
    for role in TurnRole:
        assert f"{role}:" in CLIENT or f'"{role}"' in CLIENT, f"the client has no name for a {role} turn"


def test_every_suggestion_kind_has_words_for_a_curator():
    """A kind with no entry renders as the enum's own token beside an artist's name."""
    for kind in SUGGESTION_KINDS:
        assert f"{kind}:" in CLIENT, f"the client has no word for a {kind} suggestion"


def test_every_resolution_status_has_a_glyph():
    """Colour is never the sole carrier of state, so the glyph is not optional."""
    assert _object_keys("RESOLUTION_GLYPHS") == {str(status) for status in ResolutionStatus}


@pytest.mark.parametrize("name", ["VERDICT_WORDS", "VERDICT_GLYPHS"])
def test_every_decided_verdict_has_words_and_a_glyph(name):
    """Accept and reject must be distinguishable without colour, by decision.

    `design_decisions.accessibility_approach` names the candidate grid outright,
    and the glyph is the half a stylesheet cannot supply. A fifth verdict added
    to the enum would otherwise reach a card as `awaiting_third_opinion` — the
    raw token, on the one screen where the whole point is that the curator knows
    what they are looking at.

    `pending` is excluded because an undecided work draws no badge at all, which
    is how the ordinary case is shown: a badge on every card makes the two
    decided states harder to pick out rather than easier.
    """
    assert _object_keys(name) == {str(verdict) for verdict in Verdict if verdict is not Verdict.PENDING}


def test_provenance_is_still_the_two_values_the_client_renders_as_a_pair():
    """The client draws provenance as offered-or-not, which only two values allow.

    A third member would be rendered as "asked for" — silently, and wrongly, on
    the one distinction the supplement exists to keep visible. This fails at the
    moment the member is added rather than at the moment a curator accepts an
    offered work believing they asked for it.
    """
    assert {str(provenance) for provenance in WorkProvenance} == {"proposed", "offered"}


def test_every_facet_kind_has_a_word_the_work_screen_can_label_it_with():
    """The typed vocabulary reaches a museum label, so every kind needs one.

    `VocabularyKind` is shared with `Affinity.kind` precisely so that what a work
    *is* and what a curator *likes* are said in one set of terms — which means a
    seventh member arrives for reasons that have nothing to do with this screen,
    and reaches it as its raw token. The Work screen falls through to that token
    rather than dropping the fact, so nothing on the page would look broken; it
    would simply read `date_range` where a label belongs.
    """
    assert _object_keys("FACET_KIND_WORDS") == {str(kind) for kind in VocabularyKind}


def test_every_facet_kind_label_actually_has_a_word_in_it():
    """Right keys, empty value: a term with nothing in it, and every keys test green."""
    values = _object_values("FACET_KIND_WORDS")
    assert values, "`FACET_KIND_WORDS` parsed to no string values at all — this guard would pass vacuously"

    empty = sorted(key for key, phrase in values.items() if not phrase.strip())
    assert not empty, f"`FACET_KIND_WORDS` has keys with no words behind them: {empty}"


def test_every_taste_kind_has_a_heading_the_screen_can_group_under():
    """The Taste screen groups by kind, and a kind with no heading has no group.

    Same shared vocabulary and the same failure as the Work screen's labels, one
    screen along: a seventh member arrives for reasons that have nothing to do
    with taste, and reaches this page as a raw token over a list of judgments.
    The Taste screen renders only the kinds it has headings for, so an unlabelled
    kind is worse than an ugly one — the judgments under it are *not drawn*, and
    the curator sees no evidence they exist.
    """
    assert _object_keys("TASTE_KIND_WORDS") == {str(kind) for kind in VocabularyKind}


@pytest.mark.parametrize("name", ["SENTIMENT_WORDS", "SENTIMENT_GLYPHS"])
def test_every_sentiment_has_words_and_a_shape(name):
    """Warmth is exactly the thing a first draft renders as a colour ramp.

    `accessibility-spec.md` binds this surface and colour is never the sole
    carrier of state, so each of the four gets a distinguishable glyph as well as
    a word — and a fifth sentiment added to the enum fails here rather than
    arriving on the page as its own token beside no shape at all.
    """
    assert _object_keys(name) == {str(member) for member in AffinitySentiment}


def test_every_derivation_has_a_sentence_saying_what_the_claim_is():
    """The Taste screen exists to make derivation visible, so a bare token defeats it.

    "inferred" on its own tells a curator nothing about whether the product is
    repeating them or guessing at them — which is precisely the thing they need
    in order to decide whether to overrule the row.
    """
    assert _object_keys("DERIVATION_WORDS") == {str(member) for member in AffinityDerivation}


@pytest.mark.parametrize("name", ["TASTE_KIND_WORDS", "SENTIMENT_WORDS", "SENTIMENT_GLYPHS", "DERIVATION_WORDS"])
def test_every_taste_phrase_a_curator_reads_actually_has_words_in_it(name):
    """Right keys, empty value — the hole the keys checks above cannot see."""
    values = _object_values(name)
    assert values, f"`{name}` parsed to no string values at all — this guard would pass vacuously"

    empty = sorted(key for key, phrase in values.items() if not phrase.strip())
    assert not empty, f"`{name}` carries {empty} with no words behind them"


def test_the_three_reactions_are_the_pairs_of_fields_taste_is_held_in():
    """Each reaction writes a `sentiment` and an `open_to_more`, and both are named.

    The two-fields rule is only paid for at the point a control writes them, and
    a reaction table that carried a sentiment alone would default the openness —
    where the default that reads as safe is the one that silently blacklists an
    artist the curator asked to keep hearing about. Read off the client rather
    than agreed to, because nothing else in this repository executes it.
    """
    body = _literal_body("REACTIONS")

    for reaction in ("more like this", "not this", "tell me more"):
        assert f'"{reaction}"' in body, f"the client has no control writing {reaction!r}"
    assert body.count("sentiment:") == body.count("open_to_more:") == 3
    # And the pair that the whole design exists for: cool, and still open.
    assert '"tell me more": { sentiment: "cool", open_to_more: true }' in body
