"""Making a held original wall-ready, and deciding when there is anything to do.

What is asserted here is the policy above the mat engine and the compositor,
which are tested beside this: when a model is worth paying for, what counts as a
current canvas, and what a curator's own colour does to one.

The staleness rules get the most attention because they are the ones a green
suite is least able to notice going wrong — a rendition that is silently served
stale looks exactly like one that is correct, on every surface, until someone
walks past the television.
"""

from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest
from PIL import Image

from curation.acquisition.mat import MatChoice, MatEngine
from curation.acquisition.preparation import (
    PreparationOutcome,
    PreparationService,
    PreparationSettings,
)
from curation.persistence.records import (
    AcquisitionMethod,
    FetchStatus,
    MatMethod,
    RenditionKind,
    RightsStatus,
    SourceClass,
)
from curation.services.display_fit import DisplayFit
from curation.services.errors import ServiceError


@pytest.fixture
def prep(services) -> PreparationService:
    return services.preparation


@pytest.fixture
def prep_settings(settings) -> PreparationSettings:
    return PreparationSettings(
        art_root=settings.art_root,
        ready_path=settings.ready_path,
        panel_width=settings.tv_panel_width_px,
        panel_height=settings.tv_panel_height_px,
        box=settings.tv_artwork_box,
    )


def _spending_engine(hex_rgb: str, cost: Decimal) -> MatEngine:
    """A mat engine that answers as a paid model would, without a network.

    Substituting the *choice* rather than the transport, because what is under
    test here is what the service does with a cost — not how a cost is parsed,
    which `test_mat_engine.py` drives through the real client.
    """

    class _Paid(MatEngine):
        def choose(self, image_path):  # noqa: ARG002 - the path is irrelevant to a canned answer
            return MatChoice(
                hex_rgb=hex_rgb,
                method=MatMethod.VISION_MODEL,
                reason="A canned answer.",
                model_id="qwen/qwen3.7-flash",
                cost_usd=cost,
            )

    return _Paid(None, image_max_edge=256)


def _work_with_original(service, settings, *, width=2400, height=1800, colour=(30, 60, 120), content_hash="hash-one"):
    """A catalogued work whose original is real bytes on disk.

    Real, because everything downstream decodes them: a stand-in would make every
    assertion here depend on Pillow never being asked to open the file.
    """
    work = service.add_artwork(title="Nighthawks")
    source = service.add_source(
        artwork_id=work.id,
        url="https://gallery.example.com/a.jpg",
        provider="gallery_site",
        source_class=SourceClass.CONTEMPORARY_WEB,
        acquisition_method=AcquisitionMethod.DIRECT_HTTP,
        rights_status=RightsStatus.UNKNOWN,
        is_primary=True,
    )
    originals = settings.art_root / "raw"
    originals.mkdir(parents=True, exist_ok=True)
    path = originals / f"{work.id}.jpg"
    Image.new("RGB", (width, height), colour).save(path, format="JPEG", quality=90)
    service.record_original(
        artwork_id=work.id,
        source_id=source.id,
        path=str(path.relative_to(settings.art_root)),
        width=width,
        height=height,
        byte_size=path.stat().st_size,
        content_hash=content_hash,
        fetch_status=FetchStatus.OK,
    )
    return work, path


class TestPreparingAWorkForTheFirstTime:
    def test_it_gets_a_mat_a_canvas_and_a_rendition_row(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert service.current_mat_color(work.id) is not None
        rendered = settings.art_root / result.relative_path
        assert rendered.is_file()
        with Image.open(rendered) as canvas:
            assert canvas.size == (settings.tv_panel_width_px, settings.tv_panel_height_px)

    def test_the_rendition_records_the_panel_it_was_composed_for(self, prep, service, settings):
        """Geometry in columns, not in the filename. The 2024 tree's `_w648_h480`
        suffix is why a recovered catalogue pointed at a panel that no longer
        existed."""
        work, _ = _work_with_original(service, settings)

        prep.prepare(work.id)

        [view] = service.list_renditions(work.id)
        assert view.rendition.kind is RenditionKind.TV_DISPLAY
        assert view.rendition.target_width == settings.tv_panel_width_px
        assert view.rendition.target_height == settings.tv_panel_height_px
        assert "3840" not in Path(view.rendition.relative_path).name

    def test_the_rendition_is_born_current(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)

        prep.prepare(work.id)

        [view] = service.list_renditions(work.id)
        assert view.stale is False

    def test_a_deployment_with_no_key_records_the_mechanical_method(self, prep, service, settings):
        """The suite wires no model client, which is the keyless deployment
        exactly. The colour is real and it says where it came from."""
        work, _ = _work_with_original(service, settings)

        result = prep.prepare(work.id)

        assert result.mat_method == MatMethod.DOMINANT_COLOR_FALLBACK.value
        assert service.current_mat_color(work.id).method is MatMethod.DOMINANT_COLOR_FALLBACK

    def test_the_fit_and_the_size_on_the_wall_come_back(self, prep, service, settings):
        work, _ = _work_with_original(service, settings, width=4000, height=3000)

        result = prep.prepare(work.id)

        assert result.fit is DisplayFit.NATIVE
        assert result.rendered_long_edge_inches > 0


class TestPreparingAgain:
    def test_a_current_canvas_is_left_alone(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        first = prep.prepare(work.id)

        second = prep.prepare(work.id)

        assert second.outcome is PreparationOutcome.UNCHANGED
        assert second.relative_path == first.relative_path

    def test_re_preparing_never_re_chooses_the_mat(self, prep, service, settings):
        """**The reason a re-render is free.** Re-asking a model for a colour the
        work already has would both spend money and quietly replace a decision —
        including a curator's own, which is the worst version of it."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#6b6b6b", method=MatMethod.MANUAL)

        prep.prepare(work.id, force=True)

        current = service.current_mat_color(work.id)
        assert current.hex_rgb == "#6b6b6b"
        assert current.method is MatMethod.MANUAL

    def test_force_re_renders_a_canvas_that_is_already_current(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)

        forced = prep.prepare(work.id, force=True)

        assert forced.outcome is PreparationOutcome.PREPARED

    def test_only_one_rendition_row_accumulates_per_panel(self, prep, service, settings):
        """A row per render would make "which canvas is current" a question with
        several answers."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        prep.prepare(work.id, force=True)
        prep.prepare(work.id, force=True)

        assert len(service.list_renditions(work.id)) == 1


class TestStaleness:
    def test_a_new_original_makes_the_canvas_stale_and_it_is_re_rendered(self, prep, service, settings):
        """Constraint 4, end to end: a rendition is stale when its recorded parent
        hash differs from the original the work holds now."""
        work, path = _work_with_original(service, settings)
        prep.prepare(work.id)
        source = service.list_sources(work.id)[0]
        # A re-acquisition: different bytes, different hash, same work.
        Image.new("RGB", (2400, 1800), (200, 40, 40)).save(path, format="JPEG", quality=90)
        service.record_original(
            artwork_id=work.id,
            source_id=source.id,
            path=str(path.relative_to(settings.art_root)),
            width=2400,
            height=1800,
            byte_size=path.stat().st_size,
            content_hash="hash-two",
            fetch_status=FetchStatus.OK,
        )
        assert service.list_renditions(work.id)[0].stale is True

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert service.list_renditions(work.id)[0].stale is False

    def test_a_canvas_missing_from_disk_is_re_rendered_though_the_row_looks_current(self, prep, service, settings):
        """**The condition the hash cannot see.** A restored catalogue, or a
        cleared `ready/`, leaves rows that are current by every test the
        catalogue applies and files that are not there. Trusting the row alone
        would report a work ready for a wall it cannot reach."""
        work, _ = _work_with_original(service, settings)
        first = prep.prepare(work.id)
        (settings.art_root / first.relative_path).unlink()
        assert service.list_renditions(work.id)[0].stale is False

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        assert (settings.art_root / result.relative_path).is_file()

    def test_a_canvas_composed_for_another_panel_is_re_rendered(self, service, settings, prep_settings):
        """Not stale by the hash test — the original did not change — and not
        showable either. The panel is a deployment value, and the catalogue
        outlives the television."""
        from dataclasses import replace

        work, _ = _work_with_original(service, settings)
        engine = MatEngine(None, image_max_edge=256)
        PreparationService(service, engine, prep_settings).prepare(work.id)

        # A coherent second deployment, not just a smaller number: the box is
        # derived from *this* panel, because the two are wired together and the
        # guard in `PreparationSettings` refuses a pair that came from different
        # ones. Deriving it here is what makes this a panel change rather than a
        # misconfiguration.
        smaller_panel = replace(
            prep_settings,
            panel_width=1920,
            panel_height=1080,
            box=replace(prep_settings.box, width=1658, height=798, pixels_per_inch=52.4),
        )
        result = PreparationService(service, engine, smaller_panel).prepare(work.id)

        assert result.outcome is PreparationOutcome.PREPARED
        with Image.open(settings.art_root / result.relative_path) as canvas:
            assert canvas.size == (1920, 1080)


class TestChoosingTheMatAgain:
    def test_it_supersedes_without_discarding_the_previous_choice(self, prep, service, settings):
        """Mat quality is this product's subjective bar, so "the new model picked
        a worse colour" has to be both answerable and reversible."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#123456", method=MatMethod.MANUAL)

        prep.choose_mat(work.id)

        history = service.mat_color_history(work.id)
        assert len(history) >= 2
        assert sum(1 for colour in history if colour.is_current) == 1
        assert any(colour.hex_rgb == "#123456" and not colour.is_current for colour in history)

    def test_the_canvas_is_re_rendered_in_the_new_colour(self, prep, service, settings):
        """**Without this the work keeps showing the superseded mat** while the
        catalogue reports the new one: the existing canvas is current by the only
        test the catalogue applies, because the original has not changed."""
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#ff0000", method=MatMethod.MANUAL)
        prep.prepare(work.id, force=True)
        red_canvas = (settings.art_root / prep.prepare(work.id).relative_path).read_bytes()

        prep.choose_mat(work.id)

        assert (settings.art_root / f"ready/{work.id}.jpg").read_bytes() != red_canvas

    def test_the_fallback_reason_reaches_the_caller(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)

        result = prep.choose_mat(work.id)

        assert result.mat_fallback_detail is not None
        assert result.cost_usd == Decimal(0)


class TestACuratorsOwnColour:
    def test_it_is_recorded_as_manual_and_painted(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)

        result = prep.set_mat(work.id, "#27285b")

        assert result.mat_hex == "#27285b"
        assert service.current_mat_color(work.id).method is MatMethod.MANUAL
        with Image.open(settings.art_root / result.relative_path) as canvas:
            pixel = canvas.convert("RGB").load()[0, 0]
        assert all(abs(channel - expected) <= 12 for channel, expected in zip(pixel, (39, 40, 91), strict=True))

    def test_an_unreadable_colour_is_refused_before_anything_is_written(self, prep, service, settings):
        work, _ = _work_with_original(service, settings)
        prep.prepare(work.id)
        before = service.current_mat_color(work.id).hex_rgb

        with pytest.raises(ServiceError):
            prep.set_mat(work.id, "octarine")

        assert service.current_mat_color(work.id).hex_rgb == before


class TestWhatItRefuses:
    def test_a_work_with_no_original_is_refused_with_the_remedy(self, prep, service):
        work = service.add_artwork(title="Nighthawks")

        with pytest.raises(ServiceError, match="acquire it first"):
            prep.prepare(work.id)

    def test_an_original_missing_from_disk_names_itself_rather_than_failing_inside_pillow(self, prep, service, settings):
        """This is what a restored catalogue looks like before re-acquisition
        refills the tree, and "no such file" from deep inside a decoder would
        send whoever reads it to entirely the wrong place."""
        work, path = _work_with_original(service, settings)
        path.unlink()

        with pytest.raises(ServiceError, match="Re-acquire it"):
            prep.prepare(work.id)

    def test_a_rendition_directory_outside_the_art_root_is_refused_at_wiring_time(self, settings, tmp_path):
        """Every catalogue path is relative to `ART_ROOT`, so a canvas written
        anywhere else has no representable path — and caught here it names both
        directories at startup rather than throwing after a render is done.

        Both paths are built here rather than taken from the `settings` fixture:
        that fixture's `art_root` *is* `tmp_path`, so any path under `tmp_path`
        is inside the root and would not trip the guard at all."""
        with pytest.raises(ServiceError, match="must sit inside ART_ROOT"):
            PreparationSettings(
                art_root=tmp_path / "art",
                ready_path=tmp_path / "elsewhere" / "ready",
                panel_width=3840,
                panel_height=2160,
                box=settings.tv_artwork_box,
            )

    @pytest.mark.parametrize(
        ("panel_width", "panel_height"),
        [(3000, 2160), (3840, 1200), (0, 2160), (3840, -1)],
    )
    def test_a_box_that_does_not_fit_its_panel_is_refused_at_wiring_time(self, settings, tmp_path, panel_width, panel_height):
        """**The failure this prevents has no downstream reporter.** A box wider
        than its panel yields a negative mat, which pastes the artwork off the
        canvas: the file is written, the rendition row is written, the manifest
        carries it, and the first sign of the crop is the wall. The two fields are
        derived from one another in a resolved configuration, so a mismatch means
        they came from different deployments."""
        with pytest.raises(ServiceError):
            PreparationSettings(
                art_root=tmp_path / "art",
                ready_path=tmp_path / "art" / "ready",
                panel_width=panel_width,
                panel_height=panel_height,
                box=settings.tv_artwork_box,
            )

    def test_the_shipped_panel_and_its_derived_box_agree(self, settings, tmp_path):
        """The other half: the guard must accept the pair a real deployment
        produces, or it would refuse every deployment rather than the wrong one."""
        accepted = PreparationSettings(
            art_root=tmp_path / "art",
            ready_path=tmp_path / "art" / "ready",
            panel_width=settings.tv_panel_width_px,
            panel_height=settings.tv_panel_height_px,
            box=settings.tv_artwork_box,
        )

        assert accepted.box.width <= accepted.panel_width

    def test_a_rendition_directory_inside_the_art_root_is_accepted(self, settings, tmp_path):
        """The other half, so the guard above is known to discriminate rather
        than to refuse everything."""
        accepted = PreparationSettings(
            art_root=tmp_path / "art",
            ready_path=tmp_path / "art" / "ready",
            panel_width=3840,
            panel_height=2160,
            box=settings.tv_artwork_box,
        )

        assert accepted.ready_path.name == "ready"


class TestWhatItCosts:
    """**Two Critic reviewers found this independently, and it was documented
    backwards.** `regenerate` was published as spending nothing, while the first
    preparation of every acquired work chooses a mat — because a work cannot be
    rendered without one and `acquire()` does not prepare. The claim was false on
    exactly the call a curator makes first.
    """

    def test_the_first_preparation_of_a_work_reports_what_choosing_its_mat_cost(self, service, settings, prep_settings):
        work, _ = _work_with_original(service, settings)
        engine = _spending_engine("#27285b", Decimal("0.00006626"))

        result = PreparationService(service, engine, prep_settings).prepare(work.id)

        assert result.cost_usd == Decimal("0.00006626")

    def test_a_second_preparation_costs_nothing_and_says_so(self, service, settings, prep_settings):
        """The other half. A field only ever populated on the paying path would be
        indistinguishable from one the caller forgot to read."""
        work, _ = _work_with_original(service, settings)
        engine = _spending_engine("#27285b", Decimal("0.00006626"))
        prep = PreparationService(service, engine, prep_settings)
        prep.prepare(work.id)

        again = prep.prepare(work.id, force=True)

        assert again.cost_usd == Decimal(0)
        assert again.outcome is PreparationOutcome.PREPARED

    def test_an_unchanged_result_still_carries_a_first_choice_it_paid_for(self, service, settings, prep_settings):
        """The branch that made the old code wrong in two places rather than one:
        a mat is chosen *before* the already-current check, so a work whose canvas
        survived a lost mat row pays on a call that then reports `unchanged`."""
        work, _ = _work_with_original(service, settings)
        engine = _spending_engine("#27285b", Decimal("0.00006626"))
        prep = PreparationService(service, engine, prep_settings)
        prep.prepare(work.id)
        # The canvas stays; the mat row goes, as a restored catalogue can leave it.
        for colour in service.mat_color_history(work.id):
            service._store.update_mat_color(replace(colour, is_current=False))

        result = prep.prepare(work.id)

        assert result.outcome is PreparationOutcome.UNCHANGED
        assert result.cost_usd == Decimal("0.00006626")

    def test_a_fallback_on_the_first_preparation_reaches_the_caller(self, prep, service, settings):
        """The suite's engine has no client, so every first preparation falls
        back — and the reason has to travel, because `regenerate` is where most
        works actually get their mat."""
        work, _ = _work_with_original(service, settings)

        result = prep.prepare(work.id)

        assert result.mat_fallback_detail is not None


class TestAnUndecodableOriginal:
    """**The divergence `services/imaging.py` was written to prevent, reproduced.**
    The mat engine translated Pillow's failures and the compositor did not, so an
    undecodable original raised a bare `UnidentifiedImageError` from whichever
    path reached it first — and the path that reaches it first is the common one,
    because a work with a mat skips the engine entirely.
    """

    def _corrupt(self, service, settings):
        work, path = _work_with_original(service, settings)
        path.write_bytes(b"certainly not a JPEG")
        return work

    def test_a_work_with_a_mat_already_recorded_is_refused_by_name(self, prep, service, settings):
        """This is the case that escaped: `prepare` finds a mat, skips the engine,
        and hands the file straight to the compositor."""
        work = self._corrupt(service, settings)
        service.record_mat_color(artwork_id=work.id, hex_rgb="#27285b", method=MatMethod.MANUAL)

        with pytest.raises(ServiceError, match="could not be read"):
            prep.prepare(work.id)

    def test_setting_a_colour_on_one_is_refused_by_name(self, prep, service, settings):
        """`set_mat` records the colour then renders, so it never touches the mat
        engine either."""
        work = self._corrupt(service, settings)

        with pytest.raises(ServiceError, match="could not be read"):
            prep.set_mat(work.id, "#27285b")

    def test_a_work_with_no_mat_yet_is_refused_the_same_way(self, prep, service, settings):
        """The path that already worked, kept honest: both routes now give the
        same named refusal rather than two different exceptions."""
        work = self._corrupt(service, settings)

        with pytest.raises(ServiceError, match="could not be read"):
            prep.prepare(work.id)
