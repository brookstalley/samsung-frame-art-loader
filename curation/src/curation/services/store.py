"""Calling the durable store from a service.

The store speaks in constraint violations; nothing above the service layer should
have to know that the catalogue happens to be SQL. One helper rather than a `try`
around every write keeps that translation in a single place — and keeps it
identical across the services that share the file, which is the point of having
it here rather than as a private method on one of them.
"""

from collections.abc import Callable

from curation.persistence.errors import StorageError
from curation.services.errors import ServiceError


def store_write[**P](operation: Callable[P, None], *args: P.args, **kwargs: P.kwargs) -> None:
    """Run a store write, reporting a refusal in the service's own terms.

    The arguments are passed through rather than closed over so that a write
    inside a loop cannot capture the wrong iteration's record.
    """
    try:
        operation(*args, **kwargs)
    except StorageError as exc:
        raise ServiceError(str(exc)) from exc
