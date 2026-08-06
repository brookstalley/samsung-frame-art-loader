"""What the process does before it starts answering.

`reconcile()` has its own tests, but a repair the entry point never calls is the
same defect as no repair — and it looks identical from the repair's unit tests.
That gap is not hypothetical: this chunk's constraint-10 normaliser was fully
tested and entirely unwired, and only removing the call and re-running the suite
showed it. So the call is asserted here, through `main()` itself.
"""

from dataclasses import replace
from decimal import Decimal

import curation.__main__ as entry_point
from curation.config import (
    DEFAULT_ACQUISITION_USER_AGENT,
    DEFAULT_DISCOVERY_APPROVAL_THRESHOLD,
    DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS,
    DEFAULT_DISCOVERY_MODEL,
    DEFAULT_DISCOVERY_SEARCH_RESULTS,
    DEFAULT_INPUT_COST_USD_PER_MTOK,
    DEFAULT_MAT_BOTTOM_WEIGHT,
    DEFAULT_MAT_WIDTH_INCHES,
    DEFAULT_MAX_IMAGE_BYTES,
    DEFAULT_MIN_FREE_BYTES,
    DEFAULT_OFFERED_WORKS_PER_RUN,
    DEFAULT_OUTPUT_COST_USD_PER_MTOK,
    DEFAULT_PHASE1_INPUT_TOKENS,
    DEFAULT_PHASE1_OUTPUT_TOKENS,
    DEFAULT_PHASE1_SEARCH_ALLOWANCE,
    DEFAULT_PHASE2_SEARCHES_PER_WORK,
    DEFAULT_PREVIEW_MAX_BYTES,
    DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS,
    DEFAULT_RESOLUTION_FLOOR_INCHES,
    DEFAULT_ROTATION_INTERVAL_SECONDS,
    DEFAULT_ROTATION_SHUFFLE,
    DEFAULT_SEARCH_COST_USD,
    DEFAULT_TILE_BINARY,
    DEFAULT_TILE_MAX_PIXELS,
    DEFAULT_TILE_TIMEOUT_SECONDS,
    DEFAULT_TV_PANEL_DIAGONAL_INCHES,
    DEFAULT_TV_PANEL_HEIGHT_PX,
    DEFAULT_TV_PANEL_WIDTH_PX,
    Settings,
)
from curation.discovery.phase_one import OpenRouterEngine
from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.persistence.file import open_catalogue_file
from curation.persistence.records import Theme
from curation.persistence.sqlite import SqliteCatalogue
from curation.services.catalogue import CatalogueService
from curation.services.display import DisplayService, WallSettings

#: A key shaped like the real thing, so a naive redaction that only hides values
#: it recognises as secret-looking cannot pass by accident.
SECRET = "sk-or-v1-0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"


def _defaults(art_root, **overrides) -> Settings:
    """The shipped defaults over a scratch tree, with anything a test cares about
    overridden by name.

    Constructed rather than resolved: `from_env` loads a real `.env`, found from
    the config module's own directory upward, so a test that went through it
    would run against the developer's own machine — and would then pass or fail
    depending on whether *they* happen to hold a key. The 2026-08-05 precedence
    fix does not close that: a key nobody exported is exactly the case the file
    still fills.
    """
    return replace(
        Settings(
            art_root=art_root,
            catalogue_path=art_root / "catalogue.sqlite",
            manifest_path=art_root / MANIFEST_FILENAME,
            heartbeat_path=art_root / HEARTBEAT_FILENAME,
            host="127.0.0.1",
            port=0,
            acquisition_user_agent=DEFAULT_ACQUISITION_USER_AGENT,
            tile_binary=DEFAULT_TILE_BINARY,
            tile_max_pixels=DEFAULT_TILE_MAX_PIXELS,
            tile_timeout_seconds=DEFAULT_TILE_TIMEOUT_SECONDS,
            max_image_bytes=DEFAULT_MAX_IMAGE_BYTES,
            min_free_bytes=DEFAULT_MIN_FREE_BYTES,
            preview_max_bytes=DEFAULT_PREVIEW_MAX_BYTES,
            rotation_interval_seconds=DEFAULT_ROTATION_INTERVAL_SECONDS,
            rotation_shuffle=DEFAULT_ROTATION_SHUFFLE,
            preview_sweep_interval_seconds=DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS,
            tv_panel_width_px=DEFAULT_TV_PANEL_WIDTH_PX,
            tv_panel_height_px=DEFAULT_TV_PANEL_HEIGHT_PX,
            tv_panel_diagonal_inches=DEFAULT_TV_PANEL_DIAGONAL_INCHES,
            mat_width_inches=DEFAULT_MAT_WIDTH_INCHES,
            mat_bottom_weight=DEFAULT_MAT_BOTTOM_WEIGHT,
            resolution_floor_inches=DEFAULT_RESOLUTION_FLOOR_INCHES,
            approval_threshold=DEFAULT_DISCOVERY_APPROVAL_THRESHOLD,
            phase1_search_allowance=DEFAULT_PHASE1_SEARCH_ALLOWANCE,
            phase2_searches_per_work=DEFAULT_PHASE2_SEARCHES_PER_WORK,
            offered_works_per_run=DEFAULT_OFFERED_WORKS_PER_RUN,
            search_cost_usd=Decimal(DEFAULT_SEARCH_COST_USD),
            input_cost_usd_per_mtok=Decimal(DEFAULT_INPUT_COST_USD_PER_MTOK),
            output_cost_usd_per_mtok=Decimal(DEFAULT_OUTPUT_COST_USD_PER_MTOK),
            phase1_input_tokens=DEFAULT_PHASE1_INPUT_TOKENS,
            phase1_output_tokens=DEFAULT_PHASE1_OUTPUT_TOKENS,
            discovery_model=DEFAULT_DISCOVERY_MODEL,
            discovery_max_output_tokens=DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS,
            discovery_search_results=DEFAULT_DISCOVERY_SEARCH_RESULTS,
        ),
        **overrides,
    )


def _stub_settings(monkeypatch, art_root, **overrides) -> None:
    """Make `from_env` yield those defaults, so `main()` runs against them."""
    monkeypatch.setattr(Settings, "from_env", classmethod(lambda cls: _defaults(art_root, **overrides)))


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

    _stub_settings(monkeypatch, art_root)

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
    _stub_settings(
        monkeypatch,
        art_root,
        rotation_interval_seconds=931,
        rotation_shuffle=False,
        # A panel no default could produce, so a line built from the constants
        # rather than the resolved settings would show.
        tv_panel_width_px=1920,
        tv_panel_height_px=1080,
        tv_panel_diagonal_inches=55.0,
        # Likewise the mat and the floor, for the same reason.
        mat_width_inches=3.0,
        mat_bottom_weight=2.0,
        resolution_floor_inches=7.5,
        # And likewise every discovery value: the estimate below is arithmetic
        # over all of them, so a line built from the constants rather than the
        # resolved settings cannot reproduce it.
        approval_threshold=7,
        phase1_search_allowance=3,
        phase2_searches_per_work=4,
        offered_works_per_run=9,
        search_cost_usd=Decimal("0.002"),
        input_cost_usd_per_mtok=Decimal("3.00"),
        output_cost_usd_per_mtok=Decimal("5.00"),
        phase1_input_tokens=200_000,
        phase1_output_tokens=20_000,
        discovery_model="probe/model-under-test",
        discovery_max_output_tokens=1234,
        discovery_search_results=6,
        # A key shaped like a real one. The plane is about to log its
        # configuration, and this is the value that must not appear.
        openrouter_api_key=SECRET,
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
    # What discovery may spend, and the estimate derived from it. A curator is
    # asked to authorise against that figure, so the numbers behind it are worth
    # a journal line — they are also the ones most likely to go stale, because
    # provider prices move underneath a deployment that never changes.
    assert "gate=7 works" in logged
    assert "phase1_searches=3" in logged
    assert "phase2_searches_per_work=4" in logged
    # The supplement's bound, and the one field here whose "off" is otherwise
    # invisible: a run offering nothing because this is zero looks exactly like one
    # whose collection held nothing. The zero case renders as a word instead, and is
    # asserted by `test_a_supplement_switched_off_says_disabled_rather_than_zero`.
    assert "offered_works_per_run=9" in logged
    # 200,000 input at $3/M is $0.60 and 20,000 output at $5/M is $0.10; three
    # searches at $0.002 add $0.006. Computed here rather than copied, so the
    # assertion fails if the composition changes rather than tracking it.
    assert "phase1_estimate=$0.706" in logged
    # Which model spends the money, and how much output it reserves. The
    # reservation is a correctness value — the provider prices it before
    # accepting a call — so a deployment running an unintended one should be a
    # journal read rather than an unexplained refusal at full credit.
    assert "model=probe/model-under-test" in logged
    assert "max_output_tokens=1234" in logged
    assert "search_results=6" in logged


def test_a_supplement_switched_off_says_disabled_rather_than_zero(tmp_path, monkeypatch, caplog):
    """The other arm of the field above, which is the whole reason it is a word.

    `offered_works_per_run=0` is a number an operator reads past. The setting's
    entire problem is that switching it off is invisible downstream — a run offers
    nothing and the journal cannot distinguish that from an empty collection or
    from every candidate being declined — so the startup line is the one place the
    deployment states it, and it has to state it in a form that stops the eye.
    """
    art_root = tmp_path / "art"
    art_root.mkdir()
    _stub_settings(monkeypatch, art_root, offered_works_per_run=0)
    monkeypatch.setattr(entry_point.uvicorn, "run", lambda app, **kwargs: None)

    with caplog.at_level("INFO"):
        entry_point.main()

    assert "offered_works_per_run=disabled" in caplog.text
    assert "offered_works_per_run=0" not in caplog.text, "the number is what nobody reads"


def test_startup_never_writes_the_api_key_to_the_journal(tmp_path, monkeypatch, caplog):
    """The plane holds a secret now, and the journal is where secrets leak.

    The repository is public and logging is turned *up* during a failure, which
    is exactly when someone is reading over a shoulder. Presence is still
    reported — "is the key even set" is the first question a discovery
    misconfiguration raises — but the value never is.

    This asserts the whole startup path rather than the redaction helper alone,
    because a helper that redacts correctly protects nothing if a line
    somewhere else logs the settings object whole.
    """
    art_root = tmp_path / "art"
    art_root.mkdir()
    _stub_settings(monkeypatch, art_root, openrouter_api_key=SECRET)
    monkeypatch.setattr(entry_point.uvicorn, "run", lambda app, **kwargs: None)

    with caplog.at_level("INFO"):
        entry_point.main()

    assert caplog.text.strip(), "a vacuous pass: nothing was logged at all"
    assert SECRET not in caplog.text
    assert "0123456789abcdef" not in caplog.text, "nor any fragment of it"
    assert "openrouter_key=<set>" in caplog.text, "presence is reported, which is the useful half"


def test_a_deployment_with_no_key_says_so_rather_than_looking_configured(tmp_path, monkeypatch, caplog):
    """`<unset>` and `<set>` must be distinguishable, or the line answers nothing."""
    art_root = tmp_path / "art"
    art_root.mkdir()
    _stub_settings(monkeypatch, art_root, openrouter_api_key=None)
    monkeypatch.setattr(entry_point.uvicorn, "run", lambda app, **kwargs: None)

    with caplog.at_level("INFO"):
        entry_point.main()

    assert "openrouter_key=<unset>" in caplog.text


# -- which engine a deployment gets ---------------------------------------------


def test_a_key_buys_a_real_engine(tmp_path):
    """The one wiring that turns discovery on. Asserted through the entry point's
    own resolver rather than by reading configuration, because an engine built
    correctly somewhere nothing calls is the defect this file exists for."""
    art_root = tmp_path / "art"
    settings = replace(_defaults(art_root), openrouter_api_key=SECRET)

    engine = entry_point._engine(settings)

    assert isinstance(engine, OpenRouterEngine)
    assert engine.unavailable_reason is None, "a deployment holding a key can start a run"


def test_no_key_refuses_to_discover_rather_than_faking_it(tmp_path):
    """Deliberately not a stand-in. A convincing double reachable from a real
    deployment writes invented works into a real catalogue, and the curator's
    evidence that discovery worked becomes the product fabricating it."""
    settings = replace(_defaults(tmp_path / "art"), openrouter_api_key=None)

    engine = entry_point._engine(settings)

    assert not isinstance(engine, OpenRouterEngine)
    reason = engine.unavailable_reason
    assert reason is not None
    assert "OPENROUTER_API_KEY" in reason, "the refusal names the one thing that fixes it"
    assert "art_discovery" in reason, "and what still works meanwhile"


def test_the_configured_model_reaches_the_engine(tmp_path):
    """A value read from configuration and then not passed on is the wiring bug
    this file exists to catch — the deployment's model must be the one that runs."""
    settings = replace(_defaults(tmp_path / "art"), openrouter_api_key=SECRET, discovery_model="probe/model-under-test")

    assert entry_point._engine(settings).model == "probe/model-under-test"


# -- one JSON object per line, including uvicorn's own -------------------------


def test_uvicorn_is_given_no_logging_config_of_its_own(tmp_path, monkeypatch):
    """Otherwise the journal carries plain text beside this plane's JSON.

    uvicorn's default config attaches text handlers to `uvicorn` and
    `uvicorn.access` with `propagate: False`, so the startup banner, every access
    line and every unhandled ASGI traceback would leave the process unparseable
    — and `journalctl | jq 'select(.run_id == …)'`, the documented way to
    reconstruct a run, aborts on the first non-JSON line. On a product whose
    defining failure mode is silence, that is the diagnostic path failing quietly.

    Asserted at the call rather than by scraping output because the damage is
    done by uvicorn's config install, which happens inside `run` — there is no
    later moment at which a test could observe the handlers this prevents.
    """
    art_root = tmp_path / "art"
    art_root.mkdir()
    _stub_settings(monkeypatch, art_root)
    passed: dict = {}

    def capture(app, **kwargs) -> None:  # noqa: ANN001, ANN003 - uvicorn's own signature
        passed.update(kwargs)

    monkeypatch.setattr(entry_point.uvicorn, "run", capture)

    entry_point.main()

    assert "log_config" in passed, "uvicorn was left to install its own text handlers"
    assert passed["log_config"] is None


def test_the_configured_sweep_interval_reaches_the_application(tmp_path, monkeypatch):
    """Sweeping is off unless a caller asks, and this entry point is the caller.

    `create_app` defaults the interval to zero so a test harness cannot acquire a
    file-deleting thread by accident. The consequence is that a deployment sweeps
    only because `main` passes its setting through — one line, whose deletion
    leaves every sweep test green and the plane never reclaiming anything.
    """
    art_root = tmp_path / "art"
    art_root.mkdir()
    _stub_settings(monkeypatch, art_root, preview_sweep_interval_seconds=900)
    built: dict = {}

    def capture(services, **kwargs):  # noqa: ANN001, ANN003 - the real signature
        built.update(kwargs)
        return object()

    monkeypatch.setattr(entry_point, "create_app", capture)
    monkeypatch.setattr(entry_point.uvicorn, "run", lambda app, **kwargs: None)

    entry_point.main()

    assert built["preview_sweep_interval_seconds"] == 900


def test_uvicorns_own_default_is_what_makes_that_argument_necessary():
    """Read from uvicorn itself, so the reason cannot outlive the behaviour.

    The argument above is only worth passing while uvicorn's default actually
    installs text handlers that do **not** propagate — non-propagating is the
    load-bearing half, because a propagating logger would reach this plane's JSON
    handler and no argument would be needed. If upstream ever changes this, the
    justification evaporates and this fails, which is the point: a workaround
    whose cause has gone is a line nobody can later explain.

    Deliberately not asserted by applying the config: `dictConfig` mutates
    process-wide logging state, and a test that installed uvicorn's handlers
    would leave every later test in this session logging through them.
    """
    from uvicorn.config import LOGGING_CONFIG

    loggers = LOGGING_CONFIG["loggers"]

    assert loggers["uvicorn"]["handlers"], "uvicorn no longer installs handlers of its own"
    assert loggers["uvicorn"]["propagate"] is False, "uvicorn's loggers now propagate; log_config=None is moot"
    assert loggers["uvicorn.access"]["propagate"] is False
    formatters = LOGGING_CONFIG["formatters"]
    assert all(
        "json" not in str(spec).lower() for spec in formatters.values()
    ), "uvicorn's default formatters are now JSON, which would make this plane's override unnecessary"
