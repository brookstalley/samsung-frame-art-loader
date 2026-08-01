"""What the process does before it starts answering.

`reconcile()` has its own tests, but a repair the entry point never calls is the
same defect as no repair — and it looks identical from the repair's unit tests.
That gap is not hypothetical: this chunk's constraint-10 normaliser was fully
tested and entirely unwired, and only removing the call and re-running the suite
showed it. So the call is asserted here, through `main()` itself.
"""

import curation.__main__ as entry_point
from curation.config import (
    DEFAULT_ROTATION_INTERVAL_SECONDS,
    DEFAULT_ROTATION_SHUFFLE,
    DEFAULT_TV_PANEL_DIAGONAL_INCHES,
    DEFAULT_TV_PANEL_HEIGHT_PX,
    DEFAULT_TV_PANEL_WIDTH_PX,
    Settings,
)
from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import Theme
from curation.persistence.sqlite import SqliteCatalogue
from curation.services.catalogue import CatalogueService
from curation.services.display import DisplayService, WallSettings


def test_the_plane_repairs_the_catalogue_before_it_serves(tmp_path, monkeypatch):
    """A surface must not answer from a catalogue still in a state its rules forbid.

    The order matters as much as the call: a repair that ran after `uvicorn.run`
    would run at shutdown, which is to say never.
    """
    art_root = tmp_path / "art"
    art_root.mkdir()
    path = art_root / "catalogue.sqlite"

    # A catalogue as the revision before the exactly-one-active rule wrote one:
    # themes exist and none of them is active.
    seeding = SqliteCatalogue(open_catalogue_file(path))
    seeding.add_theme(Theme(id="t1", name="Late night", created_at=_a_moment()))
    seeding.add_theme(Theme(id="t2", name="Daylight", created_at=_a_moment()))
    seeding.close()

    monkeypatch.setattr(
        Settings,
        "from_env",
        classmethod(
            lambda cls: cls(
                art_root=art_root,
                catalogue_path=path,
                manifest_path=art_root / MANIFEST_FILENAME,
                heartbeat_path=art_root / HEARTBEAT_FILENAME,
                host="127.0.0.1",
                port=0,
                rotation_interval_seconds=DEFAULT_ROTATION_INTERVAL_SECONDS,
                rotation_shuffle=DEFAULT_ROTATION_SHUFFLE,
                tv_panel_width_px=DEFAULT_TV_PANEL_WIDTH_PX,
                tv_panel_height_px=DEFAULT_TV_PANEL_HEIGHT_PX,
                tv_panel_diagonal_inches=DEFAULT_TV_PANEL_DIAGONAL_INCHES,
            )
        ),
    )

    served: list[str] = []

    def capture(app, **kwargs) -> None:  # noqa: ANN001, ANN003 - uvicorn's own signature
        # Read through a second connection to the same file, so this observes what
        # a request arriving at this moment would observe.
        observer = SqliteCatalogue(open_catalogue_file(path))
        try:
            active = DisplayService(
                observer,
                CatalogueService(observer),
                WallSettings(
                    manifest_path=art_root / MANIFEST_FILENAME,
                    heartbeat_path=art_root / HEARTBEAT_FILENAME,
                    rotation_interval_seconds=180,
                    shuffle=True,
                ),
            ).active_theme()
            served.append("none" if active is None else active.name)
        finally:
            observer.close()

    monkeypatch.setattr(entry_point.uvicorn, "run", capture)

    entry_point.main()

    assert served == ["Late night"], "the catalogue was still unrepaired when the server started"


def _a_moment():
    from datetime import UTC, datetime

    return datetime(2026, 7, 20, 9, 30, tzinfo=UTC)
