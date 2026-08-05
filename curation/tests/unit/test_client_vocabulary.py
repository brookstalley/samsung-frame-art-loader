"""The words the client has for the states the server can send it.

The browser renders enum values as sentences a curator acts on — "no wired
collection holds it" rather than `not_held`. A value with no entry in those maps
falls through to the raw token, which is a diagnostic label leaking onto a
screen: readable to whoever wrote the enum, meaningless to the person deciding
whether to re-search.

So the maps are checked against the enums rather than trusted. This is the same
bargain `test_design_tokens.py` strikes with the stylesheet: the client is not a
Python module and nothing else would notice the day a sixth reason is added, so
the check reads the real file. A member added without a sentence fails here,
which is the point at which it is cheap to write one.
"""

import re
import shutil
import subprocess

import pytest

from curation.http.pages import STATIC_DIR
from curation.persistence.discovery_records import (
    ResolutionStatus,
    RunStatus,
    UnresolvedReason,
    WorkProvenance,
)

CLIENT_PATH = STATIC_DIR / "app.js"
CLIENT = CLIENT_PATH.read_text(encoding="utf-8")


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed; this check is opportunistic")
def test_the_client_parses():
    """A syntax error here kills the entire browser surface and no other test notices.

    Every Python test asserts what the *server* sends and that the script is
    served; none of them runs a line of it. So a stray brace ships a page that
    loads, fetches nothing, and shows the "Loading the catalogue…" placeholder
    forever, against a fully green suite — the shape of failure this product
    exists to refuse.

    **This is a check, not a toolchain.** It shells out to whatever `node`
    happens to be on the machine and skips when there is none, so it adds no
    dependency and no build step, and the deliberate decision against a Node
    toolchain on a Pi (Chunk 10B) is untouched. It cannot say the client is
    *correct* — only that it is parseable, which is the cheapest fact worth
    having about a file nothing else executes.
    """
    result = subprocess.run(
        ["node", "--check", str(CLIENT_PATH)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, f"the browser client does not parse:\n{result.stderr}"


def _object_keys(name: str) -> set[str]:
    """The keys of a top-level `const <name> = { ... }` object literal in the client.

    Brace-counted rather than matched with a non-greedy regex, for the reason
    recorded in `test_design_tokens.py`: a pattern that stops at the first `}`
    silently reads a truncated object, and a check that reads half its input
    passes for the wrong reason.
    """
    opening = re.search(rf"^const {re.escape(name)} = (?={{)", CLIENT, re.MULTILINE)
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


def test_every_resolution_status_has_a_glyph():
    """Colour is never the sole carrier of state, so the glyph is not optional."""
    assert _object_keys("RESOLUTION_GLYPHS") == {str(status) for status in ResolutionStatus}


def test_provenance_is_still_the_two_values_the_client_renders_as_a_pair():
    """The client draws provenance as offered-or-not, which only two values allow.

    A third member would be rendered as "asked for" — silently, and wrongly, on
    the one distinction the supplement exists to keep visible. This fails at the
    moment the member is added rather than at the moment a curator accepts an
    offered work believing they asked for it.
    """
    assert {str(provenance) for provenance in WorkProvenance} == {"proposed", "offered"}
