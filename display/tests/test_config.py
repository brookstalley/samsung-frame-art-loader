"""Deployment values: what stops the process, and what quietly defaults.

The distinction is the whole point of this module. A value nobody typed gets a
default when there is a right answer and a refusal when there is not; a value
somebody typed *and got wrong* always refuses, because substituting a default
there hides the typo behind behaviour that looks deliberate.
"""

from pathlib import Path

import pytest

from display.config import ConfigError, load


def an_environment(art_root: Path, **overrides: str) -> dict[str, str]:
    environment = {
        "ART_ROOT": str(art_root),
        "TV_ADDRESS": "10.0.0.1",
        "LATITUDE": "45.68",
        "LONGITUDE": "-111.04",
        "LOCATION_NAME": "Bozeman",
    }
    environment.update(overrides)
    return environment


class TestWhatMustBeSet:
    @pytest.mark.parametrize("missing", ["ART_ROOT", "TV_ADDRESS", "LATITUDE", "LONGITUDE", "LOCATION_NAME"])
    def test_a_missing_deployment_value_stops_the_process(self, art_root: Path, missing: str):
        environment = an_environment(art_root)
        del environment[missing]

        with pytest.raises(ConfigError, match=missing):
            load(environment)

    def test_an_art_root_that_is_not_a_directory_is_refused(self, tmp_path: Path):
        """A typo is invisible in `.env` and shows up as a manifest that never
        arrives — which looks exactly like a curation plane that has not published
        one yet. The daemon would wait politely forever."""
        with pytest.raises(ConfigError, match="not an existing directory"):
            load(an_environment(tmp_path / "a-typo"))

    def test_a_number_that_is_not_one_is_refused_rather_than_defaulted(self, art_root: Path):
        with pytest.raises(ConfigError, match="TV_PORT"):
            load(an_environment(art_root, TV_PORT="eight-thousand"))


class TestWhatDefaults:
    def test_the_reference_deployment_needs_five_values(self, art_root: Path):
        settings = load(an_environment(art_root))

        assert settings.tv_port == 8002
        assert settings.epd_panel_width_px == 1448
        assert settings.epd_panel_height_px == 1072
        assert settings.poll_interval_seconds == 1.0
        assert settings.tv_client_name == "tvpi"
        assert settings.tv_token_file == art_root / "token_file"

    def test_the_panel_is_configurable_because_nothing_may_hardcode_one(self, art_root: Path):
        """This deployment is a 1448×1072 IT8951; the product must run on any."""
        settings = load(an_environment(art_root, EPD_PANEL_WIDTH_PX="800", EPD_PANEL_HEIGHT_PX="600"))

        assert (settings.epd_panel_width_px, settings.epd_panel_height_px) == (800, 600)

    def test_the_three_values_that_decide_whether_this_device_has_a_panel(self, art_root: Path):
        """**The names a misspelling makes invisible.**

        These three are the whole of what `.env` says about the label surface, and
        every other test in this plane builds a `Settings` directly — so a misspelt
        key or a wrong default here would leave `epd_device` empty on a Pi that has
        a panel, `label_surface` would return None, and the heartbeat would report
        a device with no panel. That is the exact distinction this plane was built
        to draw, collapsed by a typo nothing else would catch.
        """
        settings = load(
            an_environment(
                art_root,
                EPD_DEVICE="waveshare_epd.it8951",
                EPD_MARGIN_PX="64",
                EPD_ROTATE_DEGREES="0",
            )
        )

        assert settings.epd_device == "waveshare_epd.it8951"
        assert settings.epd_margin_px == 64
        assert settings.epd_rotate_degrees == 0

    def test_a_deployment_that_says_nothing_about_a_panel_has_none(self, art_root: Path):
        """The other half, and the supported deployment rather than the degraded one.

        The rotation still takes the reference deployment's default, because it
        describes how a panel is used rather than whether there is one.

        **The margin no longer does, and that is the change rather than an
        oversight.** It used to ship 40 px on the same reasoning, but a border
        trades directly against how many lines survive the drop rule, so it cannot
        be picked independently of the type floor that decides how many lines
        there are — and that floor is now derived per device from the viewing
        distance. So the margin derives with it, and this value is an override
        nobody has exercised rather than a default everybody inherits.
        """
        settings = load(an_environment(art_root))

        assert settings.epd_device == ""
        assert settings.epd_margin_px is None
        assert settings.epd_rotate_degrees == 180

    def test_the_viewing_conditions_have_no_defaults_and_must_not_acquire_any(self, art_root: Path):
        """**The one pair in this module that may never be guessed.**

        Every other unset value here takes the reference wall's number, which is
        right: a wrong poll interval is visible, a wrong brightness is visible. A
        wrong *viewing distance* is not visible at all — it produces type nobody
        can read from where they stand, while the daemon starts, the panel draws
        and every test passes. That is not hypothetical; it is what shipped, at
        half the size a letter has to reach to be resolvable, through a hardware
        probe and a cutover. A default here would restore it.
        """
        stated = load(an_environment(art_root, EPD_PANEL_DIAGONAL_INCHES="6", EPD_VIEWING_DISTANCE_INCHES="84"))
        assert (stated.epd_panel_diagonal_inches, stated.epd_viewing_distance_inches) == (6.0, 84.0)

        unstated = load(an_environment(art_root))
        assert unstated.epd_panel_diagonal_inches is None
        assert unstated.epd_viewing_distance_inches is None

    def test_a_viewing_measurement_that_is_not_a_number_is_refused_rather_than_dropped(self, art_root: Path):
        """Absent and mistyped stay different things: `None` is a deployment that
        did not measure, and silently making a typo into one would hand it the
        same outcome as a deliberate choice."""
        with pytest.raises(ConfigError, match="EPD_VIEWING_DISTANCE_INCHES"):
            load(an_environment(art_root, EPD_VIEWING_DISTANCE_INCHES="seven feet"))

    def test_the_two_paths_under_the_art_root_are_not_configurable(self, art_root: Path):
        """A setting is just a way for the writer and the reader to stop agreeing
        about where the channel between them is."""
        settings = load(an_environment(art_root))

        assert settings.manifest_path == art_root / "theme-manifest.json"
        assert settings.state_path == art_root / "display-state.sqlite"

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [("false", False), ("FALSE", False), ("0", False), ("no", False), ("off", False), ("true", True), ("yes", True)],
    )
    def test_the_shuffle_fallback_reads_the_spellings_people_write(self, art_root: Path, raw: str, expected: bool):
        assert load(an_environment(art_root, ROTATION_SHUFFLE=raw)).rotation_shuffle_fallback is expected


class TestTheStartupLine:
    def test_it_names_the_art_root_and_this_plane_s_own_panel(self, art_root: Path):
        """One journal line rather than a mystery, per the configuration spec.

        A wrong art root otherwise shows up as a manifest that never arrives, and a
        wrong panel as a label rendering off an edge nobody is looking at closely.
        """
        lines = load(an_environment(art_root)).startup_lines()

        assert lines["art_root"] == str(art_root)
        assert lines["epd_panel_px"] == "1448x1072"

    def test_it_names_the_viewing_conditions_the_type_was_sized_from(self, art_root: Path):
        """**The line that would have caught the defect this pair exists for.**

        A wrong viewing distance is invisible everywhere else — the daemon starts,
        the panel draws, every suite passes, and the only symptom is type nobody
        can read from where they stand. This puts both facts one `journalctl` away
        from the person who typed them, so it is worth an assertion rather than
        resting on a field a refactor can blank with nothing objecting.
        """
        lines = load(an_environment(art_root, EPD_PANEL_DIAGONAL_INCHES="6", EPD_VIEWING_DISTANCE_INCHES="84")).startup_lines()

        assert "6.0" in str(lines["epd_viewing"])
        assert "84.0" in str(lines["epd_viewing"])

    def test_unstated_viewing_conditions_are_reported_as_what_they_cost(self, art_root: Path):
        """The other branch, and it says the consequence rather than "unset" —
        a reader who has not met this pair cannot tell from "unset" whether their
        label is missing on purpose."""
        line = str(load(an_environment(art_root)).startup_lines()["epd_viewing"])

        assert "not stated" in line
        assert "draws none" in line, f"the line does not say what the absence costs: {line}"

    def test_it_holds_no_fact_about_the_television_s_physical_size(self, art_root: Path):
        """Curation composes the mat into the render, so this plane never needs the
        TV's size — and holding a copy is how the two panels' geometry came to be
        confused in the first place."""
        settings = load(an_environment(art_root, TV_PANEL_DIAGONAL_INCHES="50", TV_PANEL_WIDTH_PX="3840"))

        assert not hasattr(settings, "tv_panel_diagonal_inches")
        assert not any("3840" in str(value) or "50" == str(value) for value in settings.startup_lines().values())

    def test_the_token_is_reported_as_a_path_and_never_as_its_contents(self, art_root: Path, tmp_path: Path):
        """The repository is public and log excerpts are what gets pasted into an
        issue. The pairing token is a secret; where it lives is not."""
        token = tmp_path / "token_file"
        token.write_text("a-real-pairing-token")

        lines = load(an_environment(art_root, TV_TOKEN_FILE=str(token))).startup_lines()

        assert lines["tv_token_file"] == str(token)
        assert "a-real-pairing-token" not in " ".join(str(value) for value in lines.values())
