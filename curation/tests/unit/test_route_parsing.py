"""How the client reads an address, checked without a browser.

`information-architecture.md` § Navigation Structure requires that "every screen
and every consequential state (a search query, an active filter set, a run, a
conversation) is addressable", and the navigation reshape is what extended the
fragment past a bare view name to carry that state. The grammar it grew —
`#<view>[/<id>][?<key>=<value>&…]` — is a pure function over two strings, so it
is tested as one.

**Why not a browser test.** The browser suite costs a 200MB download, runs
serially against real two-second poll intervals, and is deselected by default.
None of that buys anything here: `core/route.js` imports nothing, touches no DOM
and returns a plain object, so the honest level for it is a unit test. What the
browser suite owes is that the *router* wires this into navigation — that a Work
returns to the destination it was opened from, that an old bookmark opens the new
screen — and those tests exist beside it.

**The same bargain `test_client_vocabulary.py` strikes.** This shells out to
whatever `node` is on the machine and skips when there is none. It adds no
dependency, no `package.json`, and no build step; the decision against a Node
toolchain on a Pi is untouched.
"""

import json
import shutil
import subprocess

import pytest

from curation.http.pages import STATIC_DIR

ROUTE_MODULE = STATIC_DIR / "core" / "route.js"

pytestmark = pytest.mark.skipif(
    shutil.which("node") is None,
    reason="node is not installed; this check is opportunistic",
)

#: A route table with the shape the client's own has: three destinations, two
#: screens that address one thing, two contextual screens that do not.
#:
#: Written here rather than read out of `app.js`, and the duplication is
#: deliberate: what is under test is how the parser treats a table, not what this
#: product's table happens to contain today. A parser tested only against the
#: real table would silently stop covering the `detail` branch the day the last
#: detail screen was renamed.
#: What `core/route.js` spells the third mode. Written here so this file can
#: build a table, and checked against the module's own export below — a literal
#: that drifted would leave every optional-id test asserting the behaviour of a
#: route the parser reads as *requiring* an id, which is a green run about the
#: wrong grammar.
OPTIONAL_ID = "optional"

ROUTES = {
    "walls": {},
    "collection": {},
    "discover": {},
    "work": {"detail": True},
    "run": {"detail": True},
    "theme": {"detail": OPTIONAL_ID},
    "health": {},
}


def parse(fragment: str, *, path: str = "") -> dict:
    """Run `parseRoute` in node and hand back what it returned."""
    driver = f"""
        const module = await import({json.dumps(ROUTE_MODULE.as_uri())});
        const routes = {json.dumps(ROUTES)};
        const answer = module.parseRoute({json.dumps(fragment)}, routes, {{ path: {json.dumps(path)} }});
        process.stdout.write(JSON.stringify(answer));
    """
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", driver],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"parseRoute could not be run:\n{result.stderr}"
    return json.loads(result.stdout)


def format_route(view: str, detail_id=None, params=None) -> str:
    driver = f"""
        const module = await import({json.dumps(ROUTE_MODULE.as_uri())});
        process.stdout.write(
          module.formatRoute({json.dumps(view)}, {json.dumps(detail_id)}, {json.dumps(params or {})}),
        );
    """
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", driver],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, f"formatRoute could not be run:\n{result.stderr}"
    return result.stdout


# -- the view and its id ------------------------------------------------------


def test_a_destination_is_read_from_its_own_name():
    assert parse("#collection") == {"view": "collection", "id": None, "params": {}}


def test_a_screen_that_addresses_one_thing_carries_its_id():
    assert parse("#run/abc-123") == {"view": "run", "id": "abc-123", "params": {}}


def test_a_screen_that_addresses_one_thing_is_not_entered_without_one():
    """`#work` renders the detail for nothing, which is a blank screen and a fetch of `undefined`.

    Falling back is what makes a truncated or half-typed address land somewhere
    a curator can act from.
    """
    assert parse("#work")["view"] == "walls"


def test_an_id_is_decoded():
    """Ids come back in links and bookmarks, and a theme name can hold a space."""
    assert parse("#work/a%20work%2Fwith%20slashes")["id"] == "a work/with slashes"


def test_this_test_and_the_client_spell_the_third_mode_the_same_way():
    """Otherwise every optional-id test below is about a route requiring an id.

    A misspelled `detail` value is still truthy, so the parser would demand an
    id, `#theme` would fall through to the fallback, and the tests asserting the
    index would fail for a reason that reads like a routing bug. Cheaper to say
    so here.
    """
    driver = f"""
        const module = await import({json.dumps(ROUTE_MODULE.as_uri())});
        process.stdout.write(module.OPTIONAL_ID);
    """
    result = subprocess.run(["node", "--input-type=module", "--eval", driver], capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"OPTIONAL_ID could not be read:\n{result.stderr}"
    assert result.stdout == OPTIONAL_ID


# -- a screen that is both an index and a detail ------------------------------


def test_a_screen_whose_id_is_optional_is_entered_without_one():
    """`#theme` is the index of themes, which is a screen and has to open.

    The third mode exists because `information-architecture.md` § Navigation
    Structure requires every consequential state to be addressable and one theme
    is one — while creating a theme and managing the set of them still have to
    live somewhere, and Collection's rail is a filter over the grid rather than a
    manager.
    """
    assert parse("#theme") == {"view": "theme", "id": None, "params": {}}


def test_a_screen_whose_id_is_optional_carries_one_when_it_is_given():
    assert parse("#theme/theme-winter") == {"view": "theme", "id": "theme-winter", "params": {}}


def test_an_optional_id_that_is_empty_is_the_index_rather_than_the_fallback():
    """`#theme/` is what a hand-trimmed or half-copied address looks like.

    The two branches read the tail differently — one rejects an empty string, the
    other never sees it — so this is the case that tells "entered as the index"
    from "fell through to the product's home", and both would render a screen.
    """
    assert parse("#theme/") == {"view": "theme", "id": None, "params": {}}


def test_an_optional_id_that_will_not_decode_is_used_as_it_stands():
    """The same bargain the required-id route strikes, and it must not diverge."""
    assert parse("#theme/%zz")["id"] == "%zz"


def test_state_travels_on_an_optional_id_route_with_and_without_the_id():
    route = parse("#theme?from=walls")
    assert route == {"view": "theme", "id": None, "params": {"from": "walls"}}
    assert parse("#theme/theme-winter?from=walls")["id"] == "theme-winter"


def test_an_optional_id_route_is_still_reachable_by_its_served_path():
    """`pages.py` has served `/themes` since the client was built.

    The path branch and the fragment branch each decide whether a route can be
    entered without an id, and this is the assertion that stops the third mode
    being added to one of them: written twice, the theme index would answer to
    `#theme` and send `/themes` to the product's home.
    """
    assert parse("", path="/themes") == {"view": "theme", "id": None, "params": {}}


def test_a_screen_that_requires_an_id_is_still_refused_without_one():
    """The regression the third mode could most easily cause, pinned from both sides.

    `#work` renders the detail for nothing, and `#work/` is the same address with
    a trailing slash somebody's copy-paste left behind. Neither may become a
    screen now that "no tail" has a legitimate meaning for a different route.
    """
    assert parse("#work")["view"] == "walls"
    assert parse("#work/")["view"] == "walls"


def test_an_id_that_will_not_decode_is_used_as_it_stands():
    """A malformed escape must not take the client down before it has painted.

    `decodeURIComponent` throws on `%zz`, and `readHash` runs at boot — so the
    alternative to using the raw text is a page that loads and shows nothing at
    all, with no error a curator could act on.
    """
    assert parse("#work/%zz")["id"] == "%zz"


# -- the state the reshape added ----------------------------------------------


def test_a_search_is_part_of_the_address():
    """The requirement in as many words: a curator can bookmark what they searched."""
    assert parse("#collection?q=kandinsky")["params"] == {"q": "kandinsky"}


def test_several_pieces_of_state_travel_together():
    route = parse("#collection?q=blue&movement=baroque&density=contact")
    assert route["params"] == {"q": "blue", "movement": "baroque", "density": "contact"}


def test_state_travels_on_a_screen_that_also_carries_an_id():
    route = parse("#work/abc?from=walls")
    assert route == {"view": "work", "id": "abc", "params": {"from": "walls"}}


def test_a_space_survives_the_round_trip():
    """`+` is an ordinary character in a fragment, so a space is `%20` both ways.

    Reading `+` as a space — which `URLSearchParams` does, correctly, for a form
    -encoded query string — would turn a bookmarked search for "Rothko + Newman"
    into one for "Rothko   Newman" and quietly find nothing.
    """
    address = format_route("collection", None, {"q": "Rothko + Newman"})
    assert parse(address)["params"]["q"] == "Rothko + Newman"


def test_a_key_written_by_hand_with_no_value_is_kept():
    """Dropping it silently is the omission this product refuses; an empty value is a fact."""
    assert parse("#collection?matted")["params"] == {"matted": ""}


def test_state_is_written_in_one_order_however_it_was_built():
    """Two spellings of one state make an identical navigation look like a new one.

    The router compares the address it composed against the address bar to decide
    whether a `go` is a navigation or a repaint, so an unstable key order would
    repaint the screen under a curator mid-scroll.
    """
    one = format_route("collection", None, {"q": "blue", "movement": "baroque"})
    other = format_route("collection", None, {"movement": "baroque", "q": "blue"})
    assert one == other == "#collection?movement=baroque&q=blue"


def test_a_cleared_field_is_the_absence_of_state_rather_than_empty_state():
    """`?q=` is a search for nothing; no `q` at all is not searching. They differ."""
    assert format_route("collection", None, {"q": ""}) == "#collection"


# -- the addresses the surface used to answer to ------------------------------


@pytest.mark.parametrize(
    ("old", "now"),
    [("#works", "collection"), ("#manifest", "walls"), ("#discovery", "discover"), ("#themes", "theme")],
)
def test_an_address_from_before_the_three_destinations_opens_the_screen_that_took_over(old, now):
    """These have been real, reloadable paths since the client was built.

    A bookmark that lands on the default screen is a curator told, wrongly, that
    what they saved is gone.
    """
    assert parse(old)["view"] == now


def test_an_old_address_keeps_its_state_across_the_rename():
    assert parse("#works?q=hopper") == {"view": "collection", "id": None, "params": {"q": "hopper"}}


# -- falling back --------------------------------------------------------------


def test_the_path_is_consulted_when_there_is_no_fragment():
    """`pages.py` serves the deep links, and they have to open what they name.

    Without this every typed or bookmarked path fell through to the default
    screen — the server answered 200 and the client then rendered something
    else, which is a worse failure than a 404 because it looks like it worked.
    """
    assert parse("", path="/discover")["view"] == "discover"


def test_a_fragment_outranks_the_path():
    assert parse("#walls", path="/collection")["view"] == "walls"


def test_an_address_naming_nothing_lands_on_the_product_home():
    assert parse("#nonsense", path="/nonsense")["view"] == "walls"
    assert parse("")["view"] == "walls"
