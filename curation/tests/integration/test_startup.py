"""What the process does before it starts answering.

`reconcile()` has its own tests, but a repair the entry point never calls is the
same defect as no repair — and it looks identical from the repair's unit tests.
That gap is not hypothetical: this chunk's constraint-10 normaliser was fully
tested and entirely unwired, and only removing the call and re-running the suite
showed it. So the call is asserted here, through `main()` itself.
"""

import curation.__main__ as entry_point
from curation.config import (
    DEFAULT_MAT_BOTTOM_WEIGHT,
    DEFAULT_MAT_WIDTH_INCHES,
    DEFAULT_RESOLUTION_FLOOR_INCHES,
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
                mat_width_inches=DEFAULT_MAT_WIDTH_INCHES,
                mat_bottom_weight=DEFAULT_MAT_BOTTOM_WEIGHT,
                resolution_floor_inches=DEFAULT_RESOLUTION_FLOOR_INCHES,
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


def test_startup_logs_the_resolved_root_and_this_planes_own_panel(tmp_path, monkeypatch, caplog):
    """A misconfiguration should be one journal line away rather than a mystery.

    The operational spec requires each plane to log its resolved `ART_ROOT` and
    its own panel geometry at startup. Asserted through `main()` because a log
    line nothing emits reads exactly like one nobody looked for — and the derived
    pixel density is what the mat and the resolution floor are computed from, so
    a wrong panel is silent until the art comes out the wrong size.
    """
    art_root = tmp_path / "art"
    art_root.mkdir()
    monkeypatch.setattr(
        Settings,
        "from_env",
        classmethod(
            lambda cls: cls(
                art_root=art_root,
                catalogue_path=art_root / "catalogue.sqlite",
                manifest_path=art_root / MANIFEST_FILENAME,
                heartbeat_path=art_root / HEARTBEAT_FILENAME,
                host="127.0.0.1",
                port=0,
                rotation_interval_seconds=931,
                rotation_shuffle=False,
                # A panel no default could produce, so a line built from the
                # constants rather than the resolved settings would show.
                tv_panel_width_px=1920,
                tv_panel_height_px=1080,
                tv_panel_diagonal_inches=55.0,
                # Likewise the mat and the floor, for the same reason.
                mat_width_inches=3.0,
                mat_bottom_weight=2.0,
                resolution_floor_inches=7.5,
            )
        ),
    )
    monkeypatch.setattr(entry_point.uvicorn, "run", lambda app, **kwargs: None)

    with caplog.at_level("INFO"):
        entry_point.main()

    logged = caplog.text
    assert str(art_root) in logged
    assert "1920x1080px/55.0" in logged
    # 1920x1080 measures 2202.9 pixels corner to corner; over 55 inches that is
    # 40.1 per inch. Derived, so this also pins that the derivation ran.
    assert "40.1 px per inch" in logged
    assert "rotation=931s" in logged
    assert "shuffle=False" in logged
    # The derived artwork box as well as its inputs. A wrong mat or floor is
    # otherwise visible only as works being labelled oddly in the grid, which
    # reads as a catalogue problem rather than a configuration one. 3" of mat at
    # 40.05 px per inch is 120 px, taken twice horizontally and 1+2.0 times
    # vertically: 1920-240 by 1080-360.
    assert "artwork_box=1680x720px" in logged
    assert 'mat=3.00" (bottom x2.00)' in logged
    assert 'floor=7.5"' in logged
    # The e-paper panel belongs to the display plane, and this one must hold no
    # fact about it.
    assert "1448" not in logged and "1072" not in logged
