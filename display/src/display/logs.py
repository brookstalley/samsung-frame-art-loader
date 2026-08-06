"""The display plane's log shape, and the work id every line about a work carries.

**This plane's failure is silent by construction, and more completely so than its
sibling's**: it runs unattended on a Pi under systemd, its only output is a
picture on a wall, and a stalled daemon looks exactly like a working one showing
a static image. Nobody is watching a terminal. The journal is the whole signal.

**One line is one JSON object**, so `journalctl -u display | jq 'select(.work_id
== "...")'` returns everything that happened to one work and nothing else.
Reconstructing that from prose means grepping for a substring and hoping the
message was not reworded. Nothing is exported anywhere — there is no collector
and no metrics store, and an exporter with no collector is machinery pretending
to be observability.

**`work_id` is bound, not passed.** It rides a context variable and is stamped
onto every record by a filter, so a module logging deep inside an upload or a
selection carries the correlation key without knowing it exists. Threading the id
through every call site that might log is a discipline, and one forgotten call
site defeats a discipline — the lines that go missing that way are the ones
logged from inside a failure, which are the ones worth having.

Deliberately a sibling of the curation plane's module of the same name rather
than a shared one: the two planes share no code by ratified norm, and this file
is the cheapest possible thing to keep in two places.
"""

import json
import logging
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any, Final

#: The work currently being acted on, if any. A context variable rather than a
#: thread local because the daemon is asyncio: the reconciliation loop and the
#: television client run as tasks on one thread, and a thread local would leak
#: one work's id onto another's lines.
_WORK_ID: ContextVar[str | None] = ContextVar("display_work_id", default=None)

#: What every line carries, ordered the way a person scans one: when, how bad,
#: where from, what happened.
_ALWAYS: Final[tuple[str, ...]] = ("time", "level", "logger", "message")

#: `LogRecord`'s own attributes. Anything a call site passes through `extra=`
#: lands on the record beside these, and telling the two apart needs the built-in
#: set. Built from a real record, so a Python release that adds an attribute
#: cannot turn it into a field appearing in every line.
_BUILT_IN: Final[frozenset[str]] = frozenset(
    vars(logging.LogRecord(name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None))
) | {"message", "asctime", "taskName"}


@contextmanager
def work_context(work_id: str) -> Iterator[None]:
    """Bind a work id to everything logged inside this block.

    Restores whatever was bound before rather than clearing, so a nested block
    leaves the outer id in place on the way out instead of silently dropping
    correlation for the rest of it.
    """
    token = _WORK_ID.set(work_id)
    try:
        yield
    finally:
        _WORK_ID.reset(token)


def current_work_id() -> str | None:
    """The work being acted on here, if this is inside one."""
    return _WORK_ID.get()


class WorkCorrelationFilter(logging.Filter):
    """Stamp the bound work id onto every record that passes through.

    A filter rather than a formatter concern: the id belongs to the record, so
    anything that later formats or routes it can see it. Never rejects a record —
    a log filter that dropped lines would make the absence of a signal mean two
    different things, and absence is already this plane's signal for a dead loop.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        work_id = _WORK_ID.get()
        if work_id is not None:
            record.work_id = work_id
        return True


class JsonFormatter(logging.Formatter):
    """One log record as one JSON object, with whatever the call site attached.

    Fields passed through `extra=` are carried verbatim, so adding structure to a
    line is a keyword argument rather than a change here. Values that will not
    serialise are rendered with `str` rather than dropped: a line that vanished
    because one field was an odd type is the worst outcome available to a logger.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "time": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        work_id = getattr(record, "work_id", None)
        if work_id is not None:
            payload["work_id"] = work_id
        payload.update({name: value for name, value in vars(record).items() if name not in _BUILT_IN and name != "work_id"})
        if record.exc_info:
            # The trace goes to the journal and never anywhere else. One field
            # rather than trailing lines, so a multi-line traceback cannot break
            # the one-line-one-object rule the whole shape rests on.
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


#: Marks the handler this module installed, so a second call replaces its own
#: rather than evicting handlers it knows nothing about.
_INSTALLED: Final[str] = "_display_log_handler"


def configure(level: int = logging.INFO) -> None:
    """Install the plane's log shape on the root logger.

    Called once, from the entry point. Calling it twice replaces the handler from
    the first call rather than adding a second, so lines cannot start arriving in
    duplicate.

    **Only this module's own handler is removed.** Evicting every root handler
    would be the tidier-looking implementation and a badly behaved one: it
    silently disables anything else attached to the root logger, and the first
    casualty is a test harness's capture — which fails as "no lines were logged"
    rather than as "your logging setup removed my handler".
    """
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(WorkCorrelationFilter())
    setattr(handler, _INSTALLED, True)

    root = logging.getLogger()
    for existing in list(root.handlers):
        if getattr(existing, _INSTALLED, False):
            root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)
