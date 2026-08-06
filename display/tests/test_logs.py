"""The log shape, and the one line in it that is a security control.

`configure` had no test and one caller, which for the token clamp meant
`max`→`min`, a renamed constant or a reordering would all pass the suite — and
the failure mode is the television's pairing token sitting in a journal excerpt
somebody pastes into an issue, in a public repository, which is the thing this
project's very first chunk existed to undo.
"""

import json
import logging

import pytest

from display import logs


@pytest.fixture(autouse=True)
def _restore_root_logging():
    """Put the root logger back, because `configure` deliberately mutates it.

    Without this, one test's handler formats every later test's captured output
    and the failure reads as a fault in whatever ran next.
    """
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    fork_level = logging.getLogger("samsungtvws").level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)
    logging.getLogger("samsungtvws").setLevel(fork_level)


class TestTheTokenCannotReachTheJournal:
    def test_the_television_client_is_floored_at_info_even_in_debug(self):
        """The control itself.

        The fork's `_check_for_token` writes the token at DEBUG, and `configure`
        attaches this plane's handler to the *root* logger — so turning verbosity
        up anywhere would carry it out. The moment somebody debugs a connection
        problem is exactly the moment they would.
        """
        logs.configure(logging.DEBUG)

        assert logging.getLogger("samsungtvws").level == logging.INFO

    def test_the_floor_does_not_drag_the_client_up_past_a_quieter_run(self):
        """`max`, not a bare assignment: a deployment running at WARNING should not
        find one library chattering at INFO underneath it."""
        logs.configure(logging.WARNING)

        assert logging.getLogger("samsungtvws").level == logging.WARNING

    def test_a_token_logged_at_debug_by_that_logger_is_not_emitted(self, capsys):
        """Asserted through the handler rather than through the level number, so a
        refactor that keeps the number and loses the effect still fails."""
        logs.configure(logging.DEBUG)

        logging.getLogger("samsungtvws.connection").debug("Got token %s", "a-real-pairing-token")

        assert "a-real-pairing-token" not in capsys.readouterr().err


class TestTheLineShape:
    def test_one_line_is_one_json_object_carrying_what_the_call_site_attached(self, capsys):
        logs.configure()

        logging.getLogger("display.test").info("showing %s", "a work", extra={"event": "rotation.selected", "n": 3})

        line = json.loads(capsys.readouterr().err.strip())
        assert line["message"] == "showing a work"
        assert line["event"] == "rotation.selected"
        assert line["n"] == 3
        assert line["level"] == "INFO"

    def test_a_bound_work_id_rides_every_line_inside_the_block(self, capsys):
        logs.configure()

        with logs.work_context("w-42"):
            logging.getLogger("display.test").info("inside")
        logging.getLogger("display.test").info("outside")

        inside, outside = (json.loads(line) for line in capsys.readouterr().err.strip().splitlines())
        assert inside["work_id"] == "w-42"
        assert "work_id" not in outside

    def test_a_nested_block_leaves_the_outer_id_in_place(self, capsys):
        logs.configure()

        with logs.work_context("outer"):
            with logs.work_context("inner"):
                pass
            logging.getLogger("display.test").info("after")

        assert json.loads(capsys.readouterr().err.strip())["work_id"] == "outer"

    def test_a_value_that_will_not_serialise_is_rendered_rather_than_dropped(self, capsys):
        """A line that vanished because one field was an odd type is the worst
        outcome available to a logger."""
        logs.configure()

        logging.getLogger("display.test").info("odd", extra={"thing": object()})

        assert "thing" in json.loads(capsys.readouterr().err.strip())

    def test_configuring_twice_does_not_duplicate_every_line(self, capsys):
        logs.configure()
        logs.configure()

        logging.getLogger("display.test").info("once")

        assert len(capsys.readouterr().err.strip().splitlines()) == 1

    def test_it_removes_only_its_own_handler(self, capsys):
        """Evicting every root handler is the tidier-looking implementation and a
        badly behaved one: the first casualty is a test harness's capture."""
        someone_else = logging.StreamHandler()
        logging.getLogger().addHandler(someone_else)

        logs.configure()

        assert someone_else in logging.getLogger().handlers
