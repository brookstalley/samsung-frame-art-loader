"""Fixtures for the display plane: an art root, a store, a clock that does not tick.

The daemon is driven one `tick()` at a time rather than started and stopped,
because a loop exercised through its own timer is a test that fails on a busy
machine and tells you nothing when it does. Time is a parameter here, so a
three-minute rotation interval is asserted in microseconds.
"""

import json
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fakes import FakeTv

from display.config import Settings
from display.daemon import Clock, Daemon
from display.manifest import Watcher
from display.state import DisplayState


class FakeClock:
    """Wall time and elapsed time that only move when a test moves them."""

    def __init__(self, at: datetime | None = None) -> None:
        self._now = at or datetime(2026, 6, 21, 12, 0, tzinfo=UTC)
        self._elapsed = 1000.0

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._elapsed += seconds

    def move_to(self, at: datetime) -> None:
        """Jump wall time without moving elapsed time.

        The two are independent on purpose — that is the whole reason the daemon
        reads them separately — so a test can put the sun where it wants it
        without also firing every interval that was pending.
        """
        self._now = at

    def as_clock(self) -> Clock:
        return Clock(now=lambda: self._now, monotonic=lambda: self._elapsed)


@pytest.fixture
def art_root(tmp_path: Path) -> Path:
    root = tmp_path / "art"
    (root / "ready").mkdir(parents=True)
    return root


@pytest.fixture
def settings(art_root: Path) -> Settings:
    """A deployment whose every interval is a round number a test can reason about."""
    return Settings(
        art_root=art_root,
        tv_address="10.0.0.1",
        tv_port=8002,
        tv_token_file=art_root / "token_file",
        tv_client_name="tvpi-test",
        epd_panel_width_px=1448,
        epd_panel_height_px=1072,
        # The reference wall: a 6-inch panel read from 7 feet. Stated even though
        # the fixture below configures no panel, because a `Settings` that omitted
        # them would let a test reach a code path no real deployment with a label
        # can be in — the two are what a label surface is derived from.
        epd_panel_diagonal_inches=6.0,
        epd_viewing_distance_inches=84.0,
        # None, which is the shipped shape: the border derives from the type
        # rather than being chosen beside it. Tests wanting a specific one build
        # their own `Geometry`.
        epd_margin_px=None,
        epd_rotate_degrees=180,
        # Empty, so the daemon fixtures below get the deployment most devices are:
        # a television and no panel. The tests that want one attach a double.
        epd_device="",
        latitude=45.68,
        longitude=-111.04,
        location_name="Bozeman",
        location_region="USA",
        tv_min_brightness=-4,
        tv_max_brightness=10,
        poll_interval_seconds=1.0,
        brightness_interval_seconds=300.0,
        upload_timeout_seconds=60.0,
        upload_retry_seconds=300.0,
        # Zero, so a confirmation is one read and no test waits on a real sleep.
        # The window's *duration* is exercised where it is the subject, by a test
        # that moves the clock itself.
        select_confirm_seconds=0.0,
        tv_connect_timeout_seconds=30.0,
        tv_retry_min_seconds=5.0,
        tv_retry_max_seconds=300.0,
        rotation_interval_fallback_seconds=180,
        rotation_shuffle_fallback=False,
    )


@pytest.fixture
def state(settings: Settings, clock: "FakeClock") -> Iterator[DisplayState]:
    # The store shares the daemon's clock, because the daemon measures a retry
    # wait against a timestamp the store wrote. Two clocks there is not a test
    # detail — it is a wait computed from the difference between today and a
    # fixture's chosen afternoon.
    with DisplayState(settings.state_path, now=lambda: clock.as_clock().now()) as store:
        yield store


@pytest.fixture
def tv() -> FakeTv:
    return FakeTv()


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def daemon(settings: Settings, tv: FakeTv, state: DisplayState, clock: FakeClock) -> Daemon:
    watcher = Watcher(
        settings.manifest_path,
        rotation_interval_fallback=settings.rotation_interval_fallback_seconds,
        shuffle_fallback=settings.rotation_shuffle_fallback,
    )
    return Daemon(settings=settings, tv=tv, state=state, watcher=watcher, clock=clock.as_clock())


@pytest.fixture
def publish(art_root: Path) -> Callable[..., dict]:
    """Write a manifest the way curation does, and the renders it names.

    Renders are created by default because their *absence* is a distinct
    behaviour with its own tests — a fixture that silently omitted them would
    make every other test exercise the skip path by accident.
    """

    def _publish(
        work_ids: list[str],
        *,
        sequence: int = 0,
        pinned_work_id: str | None = None,
        major: int = 1,
        interval_seconds: int = 180,
        shuffle: bool = False,
        renders: bool = True,
        theme_id: str = "theme-1",
        labels: dict[str, dict] | None = None,
    ) -> dict:
        document = {
            "schema": {"major": major, "minor": 0},
            "generated_at": datetime.now(UTC).isoformat(),
            "theme": {"id": theme_id, "name": "A theme"},
            "rotation": {"interval_seconds": interval_seconds, "shuffle": shuffle},
            "directive": {"sequence": sequence, "pinned_work_id": pinned_work_id},
            "entries": [
                {
                    "work_id": work_id,
                    "render_path": f"ready/{work_id}.jpg",
                    # A plausible default so callers that do not care get real
                    # label text rather than an empty block — an empty label is a
                    # distinct behaviour with its own tests, and a fixture that
                    # produced one by default would make every other test
                    # exercise that path by accident.
                    "label": (labels or {}).get(work_id, {"title": f"Work {work_id}"}),
                }
                for work_id in work_ids
            ],
        }
        if renders:
            for work_id in work_ids:
                # **Written once, not on every publish.** Curation rewrites the
                # manifest on every catalogue edit and does not touch the renders,
                # so a fixture that rewrote them would move every file's mtime and
                # make each `sync` look like forty re-renders — which the daemon
                # now correctly treats as forty re-uploads.
                render = art_root / "ready" / f"{work_id}.jpg"
                if not render.exists():
                    render.write_bytes(b"not really a jpeg")
        write_manifest(art_root, document)
        return document

    return _publish


def write_manifest(art_root: Path, document: object) -> None:
    """Publish atomically, exactly as the curation plane does.

    Temp file in the same directory then `os.replace`, so a reader never sees a
    partial document — and so the mtime the watcher keys on moves on every write.
    """
    target = art_root / "theme-manifest.json"
    temporary = target.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(document), encoding="utf-8")
    temporary.replace(target)
