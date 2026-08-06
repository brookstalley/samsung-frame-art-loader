"""What a store raises, owned by neither of the domains it serves.

`durable.py` states that it "holds no artwork, artist or theme concept", and it
records a correction made for exactly that reason: its refusal wording was
de-domained once two adapters sat over it. Its import line then went on reading
`from curation.persistence.catalogue import StorageError, StoreMisuseError`, so
the generic tier reached *through* the module declaring `CatalogueStore` to get
its error type.

*(Corrected 2026-08-06, the same day this module was written: the sentence above
ended "and the discovery adapter did the same", which was not true.
`sqlite_discovery.py` imported neither error type, then or now. The four
importers were `durable.py`, `adapter.py`, `sqlite.py` and `services/store.py` —
the generic tier and the catalogue side. Overstating the problem a new module
solves is a poor argument for it, and this file exists to fix an over-claim.)*

Nothing was broken and nothing was mis-ordered at import — it was a layering
statement the code contradicted in one line. This is that line's other end.

**`catalogue.py` re-exports both**, so the four importers and anything outside
this package keep working unchanged. That is not a transitional shim to be tidied
away later: `CatalogueStore`'s own methods raise these, and a caller holding a
catalogue store should not have to know which module the exception class was
declared in to catch it.
"""


class StorageError(RuntimeError):
    """The store could not do what was asked, in terms fit to show whoever asked.

    Usually a refused write — a duplicate id, a missing artist — and also a read
    of a row the store cannot represent, such as one missing a timestamp its
    record requires. Both are conditions the caller did nothing wrong to cause and
    can be told about plainly, which is the line this type draws; a call that is
    itself malformed is a `StoreMisuseError` instead.

    `reason` is the refusal on its own — "it is already in the catalogue." — kept
    separate from the message so a layer that knows what was being stored can say
    so without re-deriving why the store said no.
    """

    def __init__(self, message: str, *, reason: str | None = None) -> None:
        super().__init__(message)
        self.reason = reason if reason is not None else message


class StoreMisuseError(RuntimeError):
    """A call the store could not make sense of — an unknown table, column or key.

    Deliberately **not** a `StorageError`. That type means the store refused a
    write a caller could reasonably have attempted, and its message is written to
    be shown to whoever asked. This one means the calling code is wrong, and its
    message names internal identifiers — so it must never be translated into
    something a curator or a model reads as advice about their request.
    """
