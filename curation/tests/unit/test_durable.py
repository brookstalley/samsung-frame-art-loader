"""The durable store's own contract, against a schema of its own.

Deliberately not the catalogue's schema: this layer knows about tables, keys and
rows and nothing about artworks, and a test that reached for `artworks` would
quietly re-couple the two halves the module exists to separate.

The refusal translation exercised here is the behaviour that had no direct test
before persistence was split — it was reachable only through the service layer,
which is how a duplicate id and a missing parent could have swapped messages
without a single test noticing.
"""

import pytest

from curation.persistence.catalogue import StorageError, StoreMisuseError
from curation.persistence.durable import OrderBy, SqliteDurableStore

_SCHEMA = """
CREATE TABLE IF NOT EXISTS makers (
    id    TEXT PRIMARY KEY,
    name  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS things (
    id         TEXT PRIMARY KEY,
    label      TEXT NOT NULL,
    maker_id   TEXT REFERENCES makers(id),
    kind       TEXT
);

-- The catalogue's own tables are all keyed by a single `id`, but the contract
-- this store matches is keyed by a column-to-value mapping of any width, and
-- the entities arriving next include join rows. These two tables are what keep
-- the composite path exercised rather than merely claimed.
CREATE TABLE IF NOT EXISTS placements (
    thing_id  TEXT NOT NULL,
    shelf     TEXT NOT NULL,
    position  INTEGER,
    PRIMARY KEY (thing_id, shelf)
);

-- Every column belongs to the key, which is the shape a plain join row takes.
CREATE TABLE IF NOT EXISTS pairings (
    left_id   TEXT NOT NULL,
    right_id  TEXT NOT NULL,
    PRIMARY KEY (left_id, right_id)
);

-- No primary key at all. Nothing in this product declares such a table, which is
-- exactly why the store's answer to one should be pinned rather than discovered.
CREATE TABLE IF NOT EXISTS notes (
    body  TEXT
);
"""


@pytest.fixture
def store(tmp_path):
    """An empty store on a scratch file."""
    durable = SqliteDurableStore(tmp_path / "store.sqlite", _SCHEMA)
    yield durable
    durable.close()


def _thing(store, id_, label, *, kind=None, maker_id=None):
    return store.upsert(
        "things",
        {"id": id_, "label": label, "kind": kind, "maker_id": maker_id},
        pk=("id",),
        on_conflict="raise",
    )


# -- reading ------------------------------------------------------------------


def test_a_stored_row_comes_back_by_its_key(store):
    _thing(store, "t1", "Kettle")

    assert store.fetch_one("things", {"id": "t1"})["label"] == "Kettle"


def test_fetching_an_absent_key_is_a_miss_not_an_error(store):
    assert store.fetch_one("things", {"id": "nope"}) is None


def test_a_row_cannot_be_addressed_without_a_key(store):
    with pytest.raises(StoreMisuseError) as caught:
        store.fetch_one("things", {})

    # Naming the key it wanted is what turns this from a puzzle into a fix.
    assert "needs its whole primary key" in str(caught.value)
    assert "'id'" in str(caught.value)


# -- writing and conflict policy ----------------------------------------------


def test_raise_refuses_a_key_that_is_already_present(store):
    _thing(store, "t1", "Kettle")

    with pytest.raises(StorageError, match="already in the catalogue"):
        _thing(store, "t1", "Teapot")

    # And the refusal left the stored row alone.
    assert store.fetch_one("things", {"id": "t1"})["label"] == "Kettle"


def test_ignore_still_writes_a_row_that_is_not_yet_there(store):
    written = store.upsert("things", {"id": "t1", "label": "Kettle"}, pk=("id",), on_conflict="ignore")

    assert written == 1
    assert store.fetch_one("things", {"id": "t1"})["label"] == "Kettle"


def test_ignore_declines_the_write_and_reports_that_it_wrote_nothing(store):
    _thing(store, "t1", "Kettle")

    written = store.upsert("things", {"id": "t1", "label": "Teapot"}, pk=("id",), on_conflict="ignore")

    assert written == 0
    assert store.fetch_one("things", {"id": "t1"})["label"] == "Kettle"


def test_update_replaces_the_columns_it_was_given(store):
    _thing(store, "t1", "Kettle", kind="vessel")

    written = store.upsert("things", {"id": "t1", "label": "Teapot", "kind": "vessel"}, pk=("id",), on_conflict="update")

    assert written == 1
    assert store.fetch_one("things", {"id": "t1"})["label"] == "Teapot"


def test_update_leaves_columns_the_payload_omitted_alone(store):
    """`update` merges into the stored row rather than replacing it.

    The rest of the schema leans on this: a status transition writes the status
    and the timestamp, and must not blank the description by not mentioning it.
    """
    _thing(store, "t1", "Kettle", kind="vessel")

    store.upsert("things", {"id": "t1", "label": "Teapot"}, pk=("id",), on_conflict="update")

    stored = store.fetch_one("things", {"id": "t1"})
    assert stored["label"] == "Teapot"
    assert stored["kind"] == "vessel"


def test_an_unknown_conflict_policy_names_the_ones_that_exist(store):
    with pytest.raises(StoreMisuseError, match="ignore, raise, update"):
        store.upsert("things", {"id": "t1", "label": "Kettle"}, pk=("id",), on_conflict="clobber")


# -- refusal translation ------------------------------------------------------


def test_a_missing_parent_is_reported_as_a_missing_record_not_a_foreign_key(store):
    with pytest.raises(StorageError) as caught:
        _thing(store, "t1", "Kettle", maker_id="ghost")

    assert "refers to a record that is not in the catalogue" in str(caught.value)


def test_an_empty_required_field_is_reported_as_such(store):
    with pytest.raises(StorageError, match="a required field was empty"):
        store.upsert("things", {"id": "t1", "label": None}, pk=("id",), on_conflict="raise")


def test_a_refusal_never_leaks_the_drivers_table_and_column_names(store):
    _thing(store, "t1", "Kettle")

    with pytest.raises(StorageError) as caught:
        _thing(store, "t1", "Teapot")

    # The sqlite3 text for this is "UNIQUE constraint failed: things.id".
    message = str(caught.value)
    assert "things.id" not in message
    assert "UNIQUE" not in message


def test_a_refusal_carries_the_bare_reason_for_a_caller_that_knows_the_subject(store):
    _thing(store, "t1", "Kettle")

    with pytest.raises(StorageError) as caught:
        _thing(store, "t1", "Teapot")

    assert caught.value.reason == "it is already in the catalogue."


# -- deleting -----------------------------------------------------------------


def test_deleting_removes_the_row(store):
    _thing(store, "t1", "Kettle")

    store.delete("things", {"id": "t1"})

    assert store.fetch_one("things", {"id": "t1"}) is None


def test_deleting_a_row_that_is_not_there_is_not_an_error(store):
    store.delete("things", {"id": "never-existed"})


# -- scanning -----------------------------------------------------------------


def test_scanning_without_filters_returns_every_row(store):
    _thing(store, "t1", "Kettle")
    _thing(store, "t2", "Teapot")

    assert {row["id"] for row in store.scan("things")} == {"t1", "t2"}


def test_scanning_with_a_filter_returns_only_matching_rows(store):
    _thing(store, "t1", "Kettle", kind="vessel")
    _thing(store, "t2", "Chisel", kind="tool")

    assert [row["id"] for row in store.scan("things", {"kind": "tool"})] == ["t2"]


def test_scanning_an_unmatched_filter_is_empty_not_an_error(store):
    _thing(store, "t1", "Kettle", kind="vessel")

    assert store.scan("things", {"kind": "absent"}) == []


def test_filtering_for_an_unset_column_finds_the_rows_that_have_none(store):
    """`= NULL` is never true in SQL, so the naive rendering answers "none" always.

    That is a wrong answer wearing the shape of a right one — the same failure the
    whole-key rule refuses — and it is silent, since an empty list is exactly what
    a genuinely unmatched filter returns.
    """
    _thing(store, "t1", "Kettle", kind=None)
    _thing(store, "t2", "Chisel", kind="tool")

    assert [row["id"] for row in store.scan("things", {"kind": None})] == ["t1"]


def test_an_unset_filter_combines_with_an_ordinary_one(store):
    _thing(store, "t1", "Kettle", kind=None)
    _thing(store, "t2", "Kettle", kind="tool")
    _thing(store, "t3", "Anvil", kind=None)

    assert [row["id"] for row in store.scan("things", {"label": "Kettle", "kind": None})] == ["t1"]


def test_an_ordered_page_can_filter_for_an_unset_column_too(store):
    _thing(store, "t1", "Kettle", kind=None)
    _thing(store, "t2", "Chisel", kind="tool")
    _thing(store, "t3", "Anvil", kind=None)

    rows, total = store.select_page("things", order_by=(OrderBy("label"),), filters={"kind": None})

    assert [row["label"] for row in rows] == ["Anvil", "Kettle"]
    # The total counts the same filtered set, or a page footer would contradict it.
    assert total == 2


# -- ordered pages ------------------------------------------------------------


def test_a_page_is_ordered_by_the_terms_it_was_given(store):
    _thing(store, "t1", "Chisel")
    _thing(store, "t2", "Anvil")
    _thing(store, "t3", "Bellows")

    rows, _ = store.select_page("things", order_by=(OrderBy("label"),))

    assert [row["label"] for row in rows] == ["Anvil", "Bellows", "Chisel"]


def test_ordering_can_ignore_case_so_a_list_reads_as_a_person_expects(store):
    _thing(store, "t1", "anvil")
    _thing(store, "t2", "Bellows")

    rows, _ = store.select_page("things", order_by=(OrderBy("label", ignore_case=True),))

    # Case-sensitively, every capital sorts before every lowercase letter, which
    # would put "Bellows" first.
    assert [row["label"] for row in rows] == ["anvil", "Bellows"]


def test_a_page_reports_the_unpaged_total_not_the_page_size(store):
    for index in range(5):
        _thing(store, f"t{index}", f"Thing {index}")

    rows, total = store.select_page("things", order_by=(OrderBy("label"),), limit=2, offset=0)

    assert len(rows) == 2
    assert total == 5


def test_the_total_counts_the_filtered_set_not_the_table(store):
    _thing(store, "t1", "Kettle", kind="vessel")
    _thing(store, "t2", "Chisel", kind="tool")
    _thing(store, "t3", "Anvil", kind="tool")

    rows, total = store.select_page("things", order_by=(OrderBy("label"),), filters={"kind": "tool"}, limit=1)

    assert total == 2
    assert [row["label"] for row in rows] == ["Anvil"]


def test_consecutive_pages_do_not_repeat_or_skip_a_row(store):
    for index in range(4):
        _thing(store, f"t{index}", f"Thing {index}")

    first, _ = store.select_page("things", order_by=(OrderBy("label"), OrderBy("id")), limit=2, offset=0)
    second, _ = store.select_page("things", order_by=(OrderBy("label"), OrderBy("id")), limit=2, offset=2)

    assert [row["id"] for row in first] + [row["id"] for row in second] == ["t0", "t1", "t2", "t3"]


def test_omitting_the_limit_returns_the_whole_ordered_set(store):
    for index in range(3):
        _thing(store, f"t{index}", f"Thing {index}")

    rows, total = store.select_page("things", order_by=(OrderBy("label"),))

    assert len(rows) == total == 3


def test_an_offset_without_a_limit_still_skips(store):
    """SQLite refuses OFFSET without LIMIT, so an unhandled offset would be dropped silently."""
    for index in range(4):
        _thing(store, f"t{index}", f"Thing {index}")

    rows, total = store.select_page("things", order_by=(OrderBy("label"),), offset=2)

    assert [row["id"] for row in rows] == ["t2", "t3"]
    assert total == 4


def test_a_page_without_an_order_is_refused_rather_than_served_arbitrarily(store):
    with pytest.raises(StoreMisuseError, match="must declare its order"):
        store.select_page("things", order_by=())


# -- composite primary keys ---------------------------------------------------


def _placement(store, thing_id, shelf, position, *, on_conflict="raise"):
    return store.upsert(
        "placements",
        {"thing_id": thing_id, "shelf": shelf, "position": position},
        pk=("thing_id", "shelf"),
        on_conflict=on_conflict,
    )


def test_a_composite_key_addresses_exactly_one_row(store):
    _placement(store, "t1", "top", 1)
    _placement(store, "t1", "bottom", 2)

    assert store.fetch_one("placements", {"thing_id": "t1", "shelf": "top"})["position"] == 1
    assert store.fetch_one("placements", {"thing_id": "t1", "shelf": "bottom"})["position"] == 2


def test_a_partial_composite_key_is_refused_not_answered_arbitrarily(store):
    """Half a key is a valid WHERE clause matching several rows.

    Answering it would hand back whichever row the file returned first — a wrong
    answer wearing the shape of a right one.
    """
    _placement(store, "t1", "top", 1)
    _placement(store, "t1", "bottom", 2)

    with pytest.raises(StoreMisuseError, match="needs its whole primary key"):
        store.fetch_one("placements", {"thing_id": "t1"})


def test_a_partial_composite_key_cannot_delete_a_row_either(store):
    _placement(store, "t1", "top", 1)
    _placement(store, "t1", "bottom", 2)

    with pytest.raises(StoreMisuseError, match="needs its whole primary key"):
        store.delete("placements", {"thing_id": "t1"})

    assert len(store.scan("placements")) == 2


def test_a_conflict_target_that_is_not_the_real_key_is_refused(store):
    """`ON CONFLICT` against a non-key column resolves nothing, so `update` would insert duplicates."""
    _placement(store, "t1", "top", 1)

    with pytest.raises(StoreMisuseError, match="needs its whole primary key"):
        store.upsert(
            "placements",
            {"thing_id": "t1", "shelf": "top", "position": 9},
            pk=("thing_id",),
            on_conflict="update",
        )


def test_a_repeated_composite_key_is_refused(store):
    _placement(store, "t1", "top", 1)

    with pytest.raises(StorageError, match="already in the catalogue"):
        _placement(store, "t1", "top", 9)


def test_update_on_a_composite_key_changes_only_the_non_key_columns(store):
    _placement(store, "t1", "top", 1)

    written = _placement(store, "t1", "top", 7, on_conflict="update")

    assert written == 1
    assert store.fetch_one("placements", {"thing_id": "t1", "shelf": "top"})["position"] == 7
    # The key itself is untouched, so the other placement is still its own row.
    assert len(store.scan("placements")) == 1


def test_deleting_by_composite_key_leaves_its_siblings(store):
    _placement(store, "t1", "top", 1)
    _placement(store, "t1", "bottom", 2)

    store.delete("placements", {"thing_id": "t1", "shelf": "top"})

    assert [row["shelf"] for row in store.scan("placements")] == ["bottom"]


def test_a_row_that_is_all_key_can_be_written_twice_without_error(store):
    """`update` has nothing to set when every column is part of the key.

    A join row is exactly that shape, and the naive statement for it does not
    parse — so this is the branch that turns an upsert into a no-op instead.
    """
    pairing = {"left_id": "t1", "right_id": "t2"}
    assert store.upsert("pairings", pairing, pk=("left_id", "right_id"), on_conflict="update") == 1

    assert store.upsert("pairings", pairing, pk=("left_id", "right_id"), on_conflict="update") == 0
    assert len(store.scan("pairings")) == 1


def test_a_null_key_component_is_refused_rather_than_matched_as_is_null(store):
    """A null is a legitimate filter value and an illegitimate key value.

    SQLite does not enforce NOT NULL on a TEXT primary key, so `IS NULL` on a key
    column can match several rows — and `fetch_one` would then return an arbitrary
    one, which is the whole-key rule's failure in a different disguise.
    """
    _placement(store, "t1", "top", 1)

    with pytest.raises(StoreMisuseError, match="cannot be null"):
        store.fetch_one("placements", {"thing_id": "t1", "shelf": None})

    with pytest.raises(StoreMisuseError, match="cannot be null"):
        store.delete("placements", {"thing_id": "t1", "shelf": None})

    # The refusals changed nothing.
    assert len(store.scan("placements")) == 1


def test_a_table_without_a_key_cannot_have_a_single_row_addressed(store):
    with pytest.raises(StoreMisuseError, match="has no primary key"):
        store.fetch_one("notes", {"body": "anything"})


def test_a_table_without_a_key_can_still_be_scanned(store):
    """Refusing the keyed operations must not make the table unreadable."""
    store.upsert("notes", {"body": "a note"}, pk=(), on_conflict="raise")

    assert [row["body"] for row in store.scan("notes")] == ["a note"]


# -- identifier validation ----------------------------------------------------


def test_calling_the_store_wrongly_is_not_a_storage_refusal(store):
    """The two error types must stay disjoint, because only one is fit to show.

    The service layer translates `StorageError` into a message that reaches an
    MCP client verbatim. A misuse error's text names tables and columns, so if it
    were a `StorageError` a typo in this package would be repeated to whoever
    made the request as though it were advice about their input.
    """
    with pytest.raises(StoreMisuseError) as caught:
        store.scan("things", {"colour": "red"})

    assert not isinstance(caught.value, StorageError)


def test_an_unknown_table_is_refused_by_name(store):
    with pytest.raises(StoreMisuseError, match="No table named 'widgets'"):
        store.scan("widgets")


def test_an_unknown_column_is_refused_by_name(store):
    with pytest.raises(StoreMisuseError, match="no column named 'colour'"):
        store.scan("things", {"colour": "red"})


def test_an_unknown_order_column_is_refused_before_it_reaches_sql(store):
    with pytest.raises(StoreMisuseError, match="no column named 'weight'"):
        store.select_page("things", order_by=(OrderBy("weight"),))


def test_the_known_schema_is_read_from_the_file_not_from_the_ddl_just_run(tmp_path):
    """Reopening a file must validate against the columns that file really has.

    Reading the schema back is what makes this true for a catalogue this process
    did not create — the case that matters, since the file outlives the process.
    """
    path = tmp_path / "store.sqlite"
    first = SqliteDurableStore(path, _SCHEMA)
    first.upsert("things", {"id": "t1", "label": "Kettle"}, pk=("id",), on_conflict="raise")
    first.close()

    # A second opener that knows nothing of the tables beyond the same DDL.
    reopened = SqliteDurableStore(path, _SCHEMA)
    try:
        assert reopened.fetch_one("things", {"id": "t1"})["label"] == "Kettle"
        with pytest.raises(StoreMisuseError, match="no column named 'colour'"):
            reopened.scan("things", {"colour": "red"})
    finally:
        reopened.close()


# -- transactions --------------------------------------------------------------
#
# Several catalogue rules span rows and are applied as a clear-then-set pair. A
# pair that can be observed half-applied is a pair that can leave the catalogue in
# the state the rule forbids, so what these pin is not "writes are fast" but
# "there is no moment at which only one half happened".


def test_writes_grouped_in_a_transaction_are_all_present_afterwards(store):
    with store.transaction():
        _thing(store, "t1", "First")
        _thing(store, "t2", "Second")

    assert {row["id"] for row in store.scan("things")} == {"t1", "t2"}


def test_a_transaction_that_raises_keeps_none_of_its_writes(store):
    _thing(store, "t0", "Already there")

    with pytest.raises(RuntimeError, match="halfway"):
        with store.transaction():
            _thing(store, "t1", "First")
            raise RuntimeError("something went wrong halfway")

    # The write before the failure is gone; the write from before the block is not.
    assert {row["id"] for row in store.scan("things")} == {"t0"}


def test_a_write_inside_a_transaction_is_readable_inside_it(store):
    """A service operation has to be able to read back what it just wrote.

    Clear-then-set is written as a read, a decision and a write, so a transaction
    that hid its own writes from its own reads would make the pattern it exists
    to support impossible to express.
    """
    with store.transaction():
        _thing(store, "t1", "First")
        assert store.fetch_one("things", {"id": "t1"}) is not None
        assert len(store.scan("things")) == 1


def test_a_nested_transaction_lives_or_dies_with_the_outer_one(store):
    with pytest.raises(RuntimeError, match="outer"):
        with store.transaction():
            with store.transaction():
                _thing(store, "inner", "Written inside the nested block")
            _thing(store, "outer", "Written after it")
            raise RuntimeError("the outer block failed")

    # The nested block completing did not commit anything on its own.
    assert store.scan("things") == []


def test_a_nested_transaction_that_completes_commits_with_the_outer_one(store):
    with store.transaction():
        with store.transaction():
            _thing(store, "inner", "Written inside the nested block")
        _thing(store, "outer", "Written after it")

    assert {row["id"] for row in store.scan("things")} == {"inner", "outer"}


def test_a_refused_write_inside_a_transaction_does_not_discard_the_rest(store):
    """One statement failing is not the group failing.

    A caller that catches a refusal and carries on is making a decision; rolling
    the group back underneath it would silently undo writes it still believes in.
    Only leaving the block by exception abandons the group.
    """
    with store.transaction():
        _thing(store, "t1", "First")
        with pytest.raises(StorageError):
            _thing(store, "t1", "The same id again")
        _thing(store, "t2", "Second")

    assert {row["id"] for row in store.scan("things")} == {"t1", "t2"}


def test_a_transaction_survives_the_process_that_opened_it(tmp_path):
    """Committing means reaching the file, not merely leaving the block."""
    path = tmp_path / "store.sqlite"
    first = SqliteDurableStore(path, _SCHEMA)
    with first.transaction():
        _thing(first, "t1", "First")
        _thing(first, "t2", "Second")
    first.close()

    reopened = SqliteDurableStore(path, _SCHEMA)
    try:
        assert {row["id"] for row in reopened.scan("things")} == {"t1", "t2"}
    finally:
        reopened.close()


def test_a_rolled_back_transaction_never_reached_the_file(tmp_path):
    path = tmp_path / "store.sqlite"
    first = SqliteDurableStore(path, _SCHEMA)
    with pytest.raises(RuntimeError):
        with first.transaction():
            _thing(first, "t1", "First")
            raise RuntimeError("abandoned")
    first.close()

    reopened = SqliteDurableStore(path, _SCHEMA)
    try:
        assert reopened.scan("things") == []
    finally:
        reopened.close()


# -- ordering additions --------------------------------------------------------


def test_rows_with_no_value_sort_after_the_ones_that_have_one(store):
    _placement(store, "t1", "a", 2)
    _placement(store, "t2", "b", None)
    _placement(store, "t3", "c", 1)

    rows, _ = store.select_page(
        "placements",
        order_by=(OrderBy("position", nulls_last=True), OrderBy("shelf")),
    )

    assert [row["shelf"] for row in rows] == ["c", "a", "b"]


def test_ordering_can_run_the_other_way(store):
    _placement(store, "t1", "a", 1)
    _placement(store, "t2", "b", 3)
    _placement(store, "t3", "c", 2)

    rows, _ = store.select_page("placements", order_by=(OrderBy("position", descending=True),))

    assert [row["shelf"] for row in rows] == ["b", "c", "a"]


def test_unset_values_still_sort_last_when_the_order_is_reversed(store):
    """The null test is not itself reversed, or the flags would fight each other."""
    _placement(store, "t1", "a", 1)
    _placement(store, "t2", "b", None)
    _placement(store, "t3", "c", 2)

    rows, _ = store.select_page("placements", order_by=(OrderBy("position", nulls_last=True, descending=True),))

    assert [row["shelf"] for row in rows] == ["c", "a", "b"]
