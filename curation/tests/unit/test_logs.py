"""The log shape, and the run id that rides every line emitted inside a run.

Correlation is the whole reason this exists: one curator action fans out across
minutes and many external calls, and reconstructing which lines belonged to it is
impossible if the key is only on the lines somebody remembered to put it on. So
what is tested is not that a formatter can render a field, but that a module
which knows nothing about runs still emits the id when it logs inside one.
"""

import json
import logging

import pytest

from curation import logs


@pytest.fixture
def emitted():
    """Lines this test produced, rendered by the shipped formatter as they are logged.

    Wired the way `configure` wires it — formatter and correlation filter on a
    handler — rather than rendered afterwards from captured records. The
    difference is the whole point: the run id is read from the context *at the
    moment of emission*, so a test that stamped records later would be asking
    which run was current when the assertion ran, and would report every line as
    uncorrelated.
    """
    lines: list[dict] = []

    class Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(json.loads(self.format(record)))

    handler = Capture()
    handler.setFormatter(logs.JsonFormatter())
    handler.addFilter(logs.RunCorrelationFilter())

    root = logging.getLogger()
    restore = root.level
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    try:
        yield lines
    finally:
        root.removeHandler(handler)
        root.setLevel(restore)


def test_a_line_is_one_json_object_carrying_when_how_bad_where_and_what(emitted):
    logging.getLogger("curation.example").info("the wall changed")

    line = emitted[0]
    assert line["level"] == "INFO"
    assert line["logger"] == "curation.example"
    assert line["message"] == "the wall changed"
    assert line["time"].startswith("20")
    assert line["time"].endswith("+00:00"), "timestamps are UTC, so two planes' journals can be read together"


def test_a_line_logged_inside_a_run_carries_that_runs_id(emitted):
    """The correlation key, on a logger that knows nothing about runs."""
    with logs.run_context("run-42"):
        logging.getLogger("curation.somewhere.deep").warning("a source came back empty")

    assert emitted[0]["run_id"] == "run-42"


def test_a_line_logged_outside_a_run_carries_no_run_id(emitted):
    """Absent rather than null: a key that is always there teaches a reader to
    ignore it, and `null` would read as a run whose id nobody recorded."""
    logging.getLogger("curation.startup").info("catalogue opened")

    assert "run_id" not in emitted[0]


def test_the_binding_is_undone_on_the_way_out_even_when_the_body_raises(emitted):
    """A run that failed must not leave its id stamped on everything after it."""
    with pytest.raises(ZeroDivisionError), logs.run_context("run-7"):
        raise ZeroDivisionError
    logging.getLogger("curation.after").info("unrelated work")

    assert logs.current_run_id() is None
    assert "run_id" not in emitted[0]


def test_a_nested_binding_restores_the_outer_one_rather_than_clearing_it(emitted):
    """A re-search inside the run that spawned it must not drop correlation for
    the rest of the outer run."""
    with logs.run_context("outer"):
        with logs.run_context("inner"):
            logging.getLogger("curation.inner").info("re-searching")
        logging.getLogger("curation.outer").info("carrying on")

    assert [line["run_id"] for line in emitted] == ["inner", "outer"]


def test_fields_a_call_site_attaches_are_carried_through(emitted):
    """Structure is a keyword argument, not an edit to the formatter."""
    logging.getLogger("curation.example").info("phase 1 finished", extra={"works_proposed": 20, "event": "run.ready"})

    line = emitted[0]
    assert line["works_proposed"] == 20
    assert line["event"] == "run.ready"


def test_a_value_that_will_not_serialise_is_rendered_rather_than_losing_the_line(emitted):
    """A line that vanished because one field had an odd type is the worst
    outcome available to a logger."""

    class Opaque:
        def __str__(self) -> str:
            return "an opaque thing"

    logging.getLogger("curation.example").info("something happened", extra={"subject": Opaque()})

    assert emitted[0]["subject"] == "an opaque thing"


def _unreachable_source() -> None:
    raise ValueError("the source was unreachable")


def test_a_traceback_is_one_field_rather_than_trailing_lines(emitted):
    """Multi-line output would break the one-line-one-object rule the shape rests on."""
    try:
        _unreachable_source()
    except ValueError:
        logging.getLogger("curation.example").exception("phase 1 raised")

    line = emitted[0]
    assert "ValueError: the source was unreachable" in line["exception"]
    assert "\n" not in line["message"]


def test_configuring_twice_does_not_double_every_line():
    """The entry point calls this once; a second call must replace, not stack."""
    root = logging.getLogger()
    before = list(root.handlers)
    try:
        logs.configure()
        logs.configure()
        installed = [handler for handler in root.handlers if getattr(handler, logs._INSTALLED, False)]
        assert len(installed) == 1
    finally:
        root.handlers = before


def test_configuring_leaves_handlers_it_did_not_install_alone():
    """Evicting every root handler silently disables anything else attached —
    a test harness's capture first, which fails as "nothing was logged" rather
    than as "your logging setup removed my handler"."""
    root = logging.getLogger()
    before = list(root.handlers)
    someone_elses = logging.NullHandler()
    try:
        root.addHandler(someone_elses)
        logs.configure()
        assert someone_elses in root.handlers
    finally:
        root.handlers = before
