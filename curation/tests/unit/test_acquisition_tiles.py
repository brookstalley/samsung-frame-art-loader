"""Getting from the URL a Source carries to the URL tiles are served from.

The defect these cover shipped because the two halves of that seam were tested
against different URL shapes and no test crossed between them: the fetch path was
exercised with an image-service URL nothing in the product ever records, while the
provider recorded object links nothing ever resolved. Every test here is about the
join, not about either side.
"""

import pytest

from curation.acquisition.tiles import (
    RESOLUTION_REQUIRED,
    TileTargetUnavailable,
    resolve_tile_target,
)
from curation.persistence.records import AcquisitionMethod, RightsStatus, Source, SourceClass


def a_source(*, provider: str, url: str) -> Source:
    return Source(
        id="s1",
        artwork_id="w1",
        url=url,
        provider=provider,
        source_class=SourceClass.INSTITUTIONAL,
        acquisition_method=AcquisitionMethod.DEZOOMIFY,
        rights_status=RightsStatus.PUBLIC_DOMAIN,
        is_primary=True,
    )


class TestResolvingATileTarget:
    def test_a_registered_provider_is_asked_and_its_answer_used(self):
        source = a_source(provider="artic", url="https://api.artic.edu/api/v1/artworks/91194")

        target = resolve_tile_target(source, resolvers={"artic": lambda _: "https://www.artic.edu/iiif/2/abc"})

        assert target == "https://www.artic.edu/iiif/2/abc"

    def test_the_recorded_url_is_what_the_resolver_is_asked_about(self):
        """The resolver gets the source's URL, not the artwork or the source id."""
        asked: list[str] = []
        source = a_source(provider="artic", url="https://www.artic.edu/artworks/91194/golden-bird")

        resolve_tile_target(source, resolvers={"artic": lambda url: asked.append(url) or "https://x.test/i"})

        assert asked == ["https://www.artic.edu/artworks/91194/golden-bird"]

    def test_a_provider_that_needs_no_resolver_keeps_its_url(self):
        """Google Arts & Culture pages are readable by the tile fetcher as they are."""
        url = "https://artsandculture.google.com/asset/full-homage-to-the-square/abc"
        source = a_source(provider="google_arts_culture", url=url)

        assert resolve_tile_target(source, resolvers={}) == url

    def test_a_provider_that_needs_one_and_has_none_refuses(self):
        """The bug's shape: an identity URL must never reach the fetcher unresolved."""
        source = a_source(provider="artic", url="https://api.artic.edu/api/v1/artworks/91194")

        with pytest.raises(TileTargetUnavailable) as refusal:
            resolve_tile_target(source, resolvers={})

        # Named as this deployment's wiring, because the failure recorded against a
        # source is read by someone deciding whether to go look at the museum.
        assert "configuration fault here" in str(refusal.value)

    def test_the_refusal_names_the_provider_that_could_not_be_resolved(self):
        source = a_source(provider="artic", url="https://api.artic.edu/api/v1/artworks/91194")

        with pytest.raises(TileTargetUnavailable, match="artic"):
            resolve_tile_target(source, resolvers={})

    def test_a_resolvers_failure_is_not_swallowed(self):
        """A provider that could not be asked must not fall through to the raw URL."""

        def unreachable(_: str) -> str:
            raise RuntimeError("the collection is down")

        source = a_source(provider="artic", url="https://api.artic.edu/api/v1/artworks/91194")

        with pytest.raises(RuntimeError, match="the collection is down"):
            resolve_tile_target(source, resolvers={"artic": unreachable})

    def test_artic_is_declared_as_needing_resolution(self):
        """The declaration is the guard; without it the refusal above cannot fire."""
        assert "artic" in RESOLUTION_REQUIRED

    def test_google_arts_culture_is_deliberately_not_declared(self):
        """Its pages are fetchable, so requiring a resolver would break what works."""
        assert "google_arts_culture" not in RESOLUTION_REQUIRED


class TestTheContainerWiresResolutionFromTheConfiguredProvider:
    """The wiring itself, which is where a provider-keyed map can silently miss.

    `resolve_tile_target` looks the resolver up by `source.provider`; the container
    keys the map by `image_search.provider`. Both halves can be individually
    correct while the join is broken, and nothing below this level would notice —
    every museum fetch would simply refuse. So this drives a real container rather
    than re-deriving the expression it evaluates.
    """

    def _container(self, store, discovery_store, wall, thumbnail_settings, settings, engine, image_search):
        from curation.services.container import Services
        from curation.services.previews import PreviewSettings

        return Services.bind(
            catalogue=store,
            discovery=discovery_store,
            wall=wall,
            thumbnails=thumbnail_settings,
            artwork_box=settings.tv_artwork_box,
            engine=engine,
            discovery_settings=settings.discovery_settings,
            image_search=image_search,
            # Phase 2's two halves are wired together or not at all.
            previews=(
                None if image_search is None else PreviewSettings(art_root=settings.art_root, directory=settings.previews_path)
            ),
            # Deliberately NOT passing tile_targets: the default derivation is
            # what is under test, and passing one would test the override.
        )

    def _artic_work(self, services):
        work = services.catalogue.add_artwork(title="Golden Bird")
        services.catalogue.add_source(
            artwork_id=work.id,
            url="https://api.artic.edu/api/v1/artworks/91194",
            provider="artic",
            source_class=SourceClass.INSTITUTIONAL,
            acquisition_method=AcquisitionMethod.DEZOOMIFY,
            rights_status=RightsStatus.PUBLIC_DOMAIN,
            is_primary=True,
        )
        return work

    def test_a_configured_provider_is_consulted_on_a_real_acquisition(
        self, store, discovery_store, wall, thumbnail_settings, settings, engine
    ):
        from fakes import FakeImageSearch

        museum = FakeImageSearch()
        services = self._container(store, discovery_store, wall, thumbnail_settings, settings, engine, museum)
        work = self._artic_work(services)

        # The fetch itself fails — there is no real binary or museum here — but
        # what matters is that resolution was reached and asked the provider.
        services.acquisition.acquire(work.id)

        assert museum.resolved == ["https://api.artic.edu/api/v1/artworks/91194"]

    def test_with_no_provider_configured_an_artic_fetch_refuses_rather_than_passing_it_on(
        self, store, discovery_store, wall, thumbnail_settings, settings, engine
    ):
        """The keyless deployment, which is what every seeded install starts as."""
        services = self._container(store, discovery_store, wall, thumbnail_settings, settings, engine, None)
        work = self._artic_work(services)

        with pytest.raises(TileTargetUnavailable):
            services.acquisition.acquire(work.id)
