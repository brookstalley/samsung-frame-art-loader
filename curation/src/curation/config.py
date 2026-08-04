"""Deployment configuration for the curation plane.

Every value here differs between the dev Mac and the Pi, so none of them may
be a literal in source. A fresh checkout runs by copying `.env.example` to
`.env` and filling it in — never by editing a module.

Resolution is a function rather than module-level constants, unlike the 2024
plane's `config.py`, and the difference is deliberate: importing this module
must not require an environment, or the test suite and every tool that merely
wants to read a docstring would need one. Fail-fast is preserved by resolving
at process start, which is where a missing value should stop things.
"""

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Final

from dotenv import load_dotenv

from curation.manifest.builder import MANIFEST_FILENAME
from curation.manifest.heartbeat import HEARTBEAT_FILENAME
from curation.services.display_fit import ArtworkBox
from curation.services.runner import DiscoverySettings

#: The catalogue's filename under `ART_ROOT`. Not configurable: both planes
#: and the backup path need to agree on where the catalogue is, and a setting
#: is just a way for them to stop agreeing.
CATALOGUE_FILENAME: Final[str] = "catalogue.sqlite"

#: Where thumbnails are cached under `ART_ROOT`. Derived and device-independent:
#: regenerated on whatever machine needs them, never copied between machines.
THUMBNAILS_DIRNAME: Final[str] = "thumbs"

#: Where candidate previews are cached under `ART_ROOT`. **A third class**, and
#: kept apart from `thumbs/` because of it: a thumbnail is derived from a work
#: the catalogue holds, while a preview belongs to a work nobody has accepted and
#: may never. Previews are disposable the moment their candidate reaches a
#: terminal verdict, and a sweep that could not tell the two apart would delete a
#: held work's thumbnails.
PREVIEWS_DIRNAME: Final[str] = "previews"

#: Where acquired master images are written under `ART_ROOT`. Upstream and
#: expensive: this is the half of the tree rsync carries and nothing regenerates,
#: so it is never confused with the derived directories beside it.
ORIGINALS_DIRNAME: Final[str] = "raw"

#: Where composed television canvases are written under `ART_ROOT`. Derived and
#: **specific to the television**: a canvas here is one panel's pixel dimensions
#: with a mat drawn to that panel's physical size, so it is regenerated on the
#: machine that will show it rather than carried to another. The geometry is not
#: encoded in the filename — the 2024 tree's `_w648_h480` suffix is why a
#: recovered catalogue pointed at a panel that no longer existed; a `Rendition`
#: row carries the target size, and that row is what makes staleness detectable.
READY_DIRNAME: Final[str] = "ready"

#: Where a tiled fetch stores tiles as it walks the grid. **Working space, not
#: storage**: it exists so a fetch that came back partial can be retried without
#: re-downloading what already arrived, and it is reclaimed per work as soon as
#: that work holds a complete image. Retained after a partial fetch, which is the
#: one case the tiles are worth what they cost.
TILE_CACHE_DIRNAME: Final[str] = "tile-cache"

#: How the loader names itself to the sites it fetches from.
#:
#: **Truthful by default, which is a change from the 2024 pipeline.** That code
#: sent a hardcoded Chrome-on-Windows string — a claim to be software it is not,
#: made to servers whose operators use it to decide how to treat traffic. The
#: same reasoning already governs `ARTIC_USER_AGENT`, whose absence switches
#: phase 2 off rather than let this product misrepresent whoever runs it: a
#: default is acceptable here only because this one misrepresents nobody.
#: Deployments that want a contact address in it should set their own.
DEFAULT_ACQUISITION_USER_AGENT: Final[str] = (
    "samsung-frame-art-loader (+https://github.com/brookstalley/samsung-frame-art-loader)"
)

#: The binary that walks a tile grid. A name rather than a path: it is resolved
#: off `PATH` at call time, which is why `deploy/` has to give the units a `PATH`
#: that contains it.
DEFAULT_TILE_BINARY: Final[str] = "dezoomify-rs"

#: The largest tiled image to assemble, per side. Carried forward from the 2024
#: pipeline, which ran the wall at this ceiling for two years — a 4K canvas needs
#: far less, and the headroom is what lets a future panel or a crop use the same
#: master rather than re-acquiring it.
DEFAULT_TILE_MAX_PIXELS: Final[int] = 8192

#: How long one tiled fetch may run before it is abandoned. Generous because it
#: bounds a walk over hundreds of tiles against a throttled museum server, and the
#: throttle is deliberate — the alternative to waiting is hammering an institution
#: that asked us not to. It exists at all because the binary prompts interactively
#: in more than one situation, and a service with no ceiling would wait forever.
DEFAULT_TILE_TIMEOUT_SECONDS: Final[int] = 1800

#: The largest single image a `direct_http` source may serve. Enforced while
#: streaming rather than trusted from a header, because the ceiling exists to
#: protect the disk and a header is the source's claim about itself.
DEFAULT_MAX_IMAGE_BYTES: Final[int] = 512 * 1024 * 1024

#: Free space that must remain after an acquisition, below which one is refused.
#:
#: **This guards the catalogue, not the fetch.** `catalogue.sqlite` sits on the
#: same device as the image tree, and a full disk during a write is the classic
#: SQLite corruption story on the consumer flash `operational-spec.md` § Risks
#: names as the top operational risk — so the floor is sized to leave the
#: irreplaceable asset room to work, not to predict how large any one work is.
#: Two gigabytes is comfortably more than the largest single work in flight
#: (tiles plus assembled master) and small enough not to refuse work on a card
#: with ordinary headroom.
DEFAULT_MIN_FREE_BYTES: Final[int] = 2 * 1024 * 1024 * 1024

DEFAULT_HOST: Final[str] = "127.0.0.1"
DEFAULT_PORT: Final[int] = 8770

#: What the wall does for a theme that has expressed no pace of its own. Carried
#: forward from the 2024 plane, which ran the wall at three minutes on shuffle —
#: this is the behaviour on the wall today, and changing it silently at cutover
#: would be a regression nobody asked for.
DEFAULT_ROTATION_INTERVAL_SECONDS: Final[int] = 180
DEFAULT_ROTATION_SHUFFLE: Final[bool] = True

#: How often the plane reclaims the previews of decided works.
#:
#: Hourly because the quantity being bounded is driven by a person: previews
#: accumulate per image instance found, and instances are found by runs the
#: curator starts. An hour is far shorter than the interval between a household's
#: discovery sessions, so the directory is empty of decided works' previews
#: whenever anyone looks — and the sweep is a walk over a household's rows plus a
#: handful of unlinks, so running it more often than it has work to do costs
#: nothing worth measuring.
#:
#: It matters because `operational-spec.md` § Risks opens with the SD card, and
#: this directory is the only one under `ART_ROOT` that nothing else reclaims.
DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS: Final[int] = 3600

#: The reference deployment is a 42" Frame at 4K, but nothing may hardcode a
#: panel: the mat is specified in physical units and the resolution floor is a
#: minimum size on the wall, so both are wrong on a different television. These
#: are defaults for the reference panel, overridable per deployment.
DEFAULT_TV_PANEL_WIDTH_PX: Final[int] = 3840
DEFAULT_TV_PANEL_HEIGHT_PX: Final[int] = 2160
DEFAULT_TV_PANEL_DIAGONAL_INCHES: Final[float] = 42.0

#: The mat's width on the sides and top, in inches on the wall. Physical units
#: rather than pixels or a ratio, so it means the same thing on any panel.
DEFAULT_MAT_WIDTH_INCHES: Final[float] = 2.5

#: How much deeper the bottom margin is than the top. A true-centred image reads
#: as sitting low, so conservators weight the bottom — the convention this
#: product's mat is specified against.
DEFAULT_MAT_BOTTOM_WEIGHT: Final[float] = 1.15

#: The smallest a work may render along its long edge, in inches on the wall,
#: before it is labelled as below the floor. Below-floor works are shown and
#: remain selectable; the floor is a warning, never a filter.
DEFAULT_RESOLUTION_FLOOR_INCHES: Final[float] = 12.0

#: How many proposed works a discovery run may produce before it stops and asks.
#: The gate is on the **work count**, not on the price: real runs cost well under
#: a dollar, so a money threshold gates on the axis that does not discriminate,
#: while the judgement the gate exists to invite is scope — "you asked for Dalí
#: and I found 200 works — really?". A typical run lands near twenty, so this
#: never fires on an ordinary one and does fire on a run that read the intent far
#: more broadly than intended.
DEFAULT_DISCOVERY_APPROVAL_THRESHOLD: Final[int] = 25

#: How many web searches phase 1 may make. Flat, because phase 1's entire job is
#: to *produce* the work count that phase 2's allowance derives from — there is
#: nothing to derive from yet.
DEFAULT_PHASE1_SEARCH_ALLOWANCE: Final[int] = 10

#: How many web searches phase 2 may make for each work phase 1 proposed.
DEFAULT_PHASE2_SEARCHES_PER_WORK: Final[int] = 2

#: What one web search costs, in USD. Search bills as provider credits alongside
#: tokens rather than to a separate account, so one ceiling covers both.
#:
#: **This is a price for one back-end, not for searching in general**, and it has
#: to agree with `DEFAULT_DISCOVERY_SEARCH_ENGINE`. Parallel bills $0.001;
#: Exa and Perplexity bill $0.005 for the same request. Changing the engine
#: without changing this leaves every pre-run estimate wrong by five times in
#: whichever direction, on the one figure a curator uses to decide whether to
#: authorise a run.
DEFAULT_SEARCH_COST_USD: Final[str] = "0.001"

#: What the discovery model costs per million tokens, in USD.
DEFAULT_INPUT_COST_USD_PER_MTOK: Final[str] = "0.14"
DEFAULT_OUTPUT_COST_USD_PER_MTOK: Final[str] = "0.28"

#: What one phase-1 run may consume, as a bound rather than a typical figure.
#:
#: **Re-based 2026-08-02 against a measured run**, from 490,000 / 30,000. A real
#: run billed 3,453 input and 1,608 output tokens, because the web plugin injects
#: *excerpts* rather than whole pages — the old input figure was a cost analysis's
#: basis for a *whole* run being spent on phase 1 alone, and it made the estimate
#: shown to a curator about twenty times the actual.
#:
#: Bounds, not the measurement: an estimate a run may freely exceed is not one.
#: Input is roughly twice the measured consumption at the configured ten search
#: results, which is headroom for a long intent and long excerpts. Output is the
#: reservation itself (`DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS`) — a true physical
#: bound, since it is the ceiling the provider prices and refuses against.
#:
#: **They are near-equal even though real consumption is input-heavy**, and that
#: is a consequence worth knowing rather than an oversight: the old basis put
#: output at 6% of tokens, which made output price nearly irrelevant to model
#: choice. It is not irrelevant now, and a model billing $2.50/M output is priced
#: accordingly. `nonfunctional-requirements.md` § Cost Constraints carries the
#: reordered table; the chosen model is cheapest on either basis.
#:
#: Re-basing was safe to do here and not before **because phase 2 was measured at
#: the same time and consumes no tokens at all**: it queries museum APIs, which
#: are free, and establishes identity by local comparison. Before that was known,
#: correcting phase 1 alone would have traded a visible overstatement for an
#: invisible understatement of the run as a whole.
DEFAULT_PHASE1_INPUT_TOKENS: Final[int] = 8_000
DEFAULT_PHASE1_OUTPUT_TOKENS: Final[int] = 8_000

#: Which model phase 1 asks. A **floating** alias rather than a dated snapshot, so
#: a snapshot retirement cannot break the only paid path in a household product.
#: The dated pin is cheaper by about a third, which against a $20 ceiling does not
#: decide anything.
DEFAULT_DISCOVERY_MODEL: Final[str] = "deepseek/deepseek-v4-flash"

#: The output reservation, in tokens. **A correctness value, not a tuning knob.**
#: The provider prices the maximum output a request could produce and refuses the
#: call when that reservation exceeds the credit remaining — so leaving it unset
#: means the model's own ceiling is reserved, and a nearly empty key then refuses
#: everything at full credit. Large enough for a long work list, small enough that
#: the reservation is a rounding error against a monthly limit.
DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS: Final[int] = 8_000

#: How many pages one web search may return. **Breadth is free**: the fee is
#: charged per search request and was measured identical at one, three, five and
#: ten results, so a lower number saves nothing and sees less.
DEFAULT_DISCOVERY_SEARCH_RESULTS: Final[int] = 10

#: Which web-search back-end phase 1 pins. **Chosen on cost, because quality did
#: not discriminate** — the reverse of what the cost analysis predicted. Across
#: sixteen "resolve a named work to the museum that holds it" cases and a
#: recency-bound intent, Exa, Parallel and Perplexity each found the holding
#: institution every time and returned the same share of in-period citations.
#: Parallel bills $0.001 per request against $0.005 for the other two, which made
#: the measured run four times cheaper for identical results.
#:
#: Pinned rather than left empty because the provider's default follows the
#: *model*, so an unset engine makes the search back-end a side effect of
#: `DISCOVERY_MODEL` and a model change silently changes how the product
#: searches.
DEFAULT_DISCOVERY_SEARCH_ENGINE: Final[str] = "parallel"

#: Which model chooses mat colours. A **floating** alias for the same reason
#: `DEFAULT_DISCOVERY_MODEL` is one: a dated snapshot can be retired out from
#: under a household product.
#:
#: **Chosen 2026-08-03 on cost, having first cleared the bar.** Across ten real
#: corpus images it was the only candidate to return a usable answer every time,
#: it is the cheapest of those that did at ~$0.000063 a call, and it never
#: proposed a mat lighter than the artwork — the one failure that glares on an
#: emissive panel, and the one both cheaper candidates committed.
#: `openrouter-api-findings.md` carries the measurements.
DEFAULT_MAT_MODEL: Final[str] = "qwen/qwen3.7-flash"

#: The mat call's output reservation, in tokens. **A correctness value, not a
#: tuning knob**, and far larger than a typical answer on purpose.
#:
#: The provider prices the maximum output a request could produce, and a
#: reservation that does not clear the model's *reasoning* budget produces a
#: billed call that returns empty content with `finish_reason='length'` — money
#: spent for nothing, and a work quietly matted by the mechanical fallback.
#: Measured: a reasoning model given 700 tokens answered nothing five times out of
#: five, and answered correctly five times out of five at 3,000.
#:
#: **Raised from 2,000 after a corpus run, and the reason is that the overrun is
#: intermittent.** The chosen model reasons in about 160 tokens on most works, and
#: on one Miró it exceeded 2,000 — then came in under it when the identical call
#: was repeated. So the failure is not a property of a work that could be
#: predicted from it, and sizing the reservation to typical consumption buys a
#: tail of silently-mechanical mats.
#:
#: **Headroom is close to free**, which is what makes this the easy call: the
#: provider bills the tokens actually emitted, not the reservation. The same work
#: cost $0.000064 at 2,000 and $0.000077 at 8,000. The reservation is priced only
#: when it is *refused* — a 402 against remaining credit — which is a different
#: failure with a different remedy.
DEFAULT_MAT_MAX_OUTPUT_TOKENS: Final[int] = 8_000

#: The longest edge, in pixels, of the copy of the artwork the mat model sees.
#: Images bill inside `prompt_tokens`, so this is the one dial on what a mat call
#: costs. 768 is enough for a model to read a palette and a composition, and a
#: master at gallery resolution would otherwise be sent whole.
DEFAULT_MAT_IMAGE_MAX_EDGE: Final[int] = 768

#: Settings fields that must never reach a log line, declared once here rather
#: than remembered at each site that logs. `Settings.redacted()` walks this set
#: and so does the guard over it, so declaring a secret is what gets it both
#: redacted and checked — a guard that only knows the secrets someone remembered
#: to add to it is the shape that silently stops covering the newest one.
_SECRET_FIELDS: Final[frozenset[str]] = frozenset({"openrouter_api_key"})


class ConfigError(RuntimeError):
    """A required deployment value is missing or unusable."""


@dataclass(frozen=True, slots=True)
class Settings:
    """The resolved deployment values the curation plane runs on."""

    art_root: Path
    catalogue_path: Path
    manifest_path: Path
    heartbeat_path: Path
    host: str
    port: int
    rotation_interval_seconds: int
    rotation_shuffle: bool
    #: How often the plane reclaims the previews of works the curator has
    #: decided. Zero disables sweeping, which is a coherent choice for a
    #: deployment with disk to spare — previews are harmless, only numerous.
    preview_sweep_interval_seconds: int
    #: The **television's** panel, never the e-paper one. Curation composes the
    #: mat and judges whether a source is large enough for the wall, so it needs
    #: the TV's physical size; it must hold no fact about the label panel, which
    #: belongs to the plane that owns it.
    tv_panel_width_px: int
    tv_panel_height_px: int
    tv_panel_diagonal_inches: float
    #: The mat's geometry, in inches on the wall, and the floor judged against it.
    mat_width_inches: float
    mat_bottom_weight: float
    resolution_floor_inches: float
    #: What acquisition may fetch, how, and what it refuses to risk. The free
    #: space floor is the one that is not about images at all — see its default.
    acquisition_user_agent: str
    tile_binary: str
    tile_max_pixels: int
    tile_timeout_seconds: int
    max_image_bytes: int
    min_free_bytes: int
    #: What discovery is allowed to do, and what a provider charges for doing it.
    #: Prices move — one recorded model price drifted 28% in twelve days — and the
    #: allowances are policy a household sets, so none of these may be a literal
    #: in source.
    approval_threshold: int
    phase1_search_allowance: int
    phase2_searches_per_work: int
    search_cost_usd: Decimal
    input_cost_usd_per_mtok: Decimal
    output_cost_usd_per_mtok: Decimal
    phase1_input_tokens: int
    phase1_output_tokens: int
    #: How phase 1 reaches its provider. Separate from the allowances above
    #: because these configure the *engine*, while those configure what the
    #: service layer may authorise — and only one of the two is a policy a
    #: household sets.
    discovery_model: str
    discovery_max_output_tokens: int
    discovery_search_results: int
    #: Which web-search back-end phase 1 pins. Never `None` in a resolved
    #: configuration: leaving it to the provider's default makes the back-end a
    #: side effect of `discovery_model`, because that default resolves to the
    #: model provider's native search where one exists and to Exa where none does.
    #: `DEFAULT_DISCOVERY_SEARCH_ENGINE` carries which one and why.
    discovery_search_engine: str = DEFAULT_DISCOVERY_SEARCH_ENGINE
    #: How the mat engine reaches its provider. Its own model rather than
    #: `discovery_model`, because the two ask for different things: discovery
    #: wants a text model that searches, and this one has to see a picture. A
    #: single setting would make either choice a constraint on the other.
    mat_model: str = DEFAULT_MAT_MODEL
    mat_max_output_tokens: int = DEFAULT_MAT_MAX_OUTPUT_TOKENS
    mat_image_max_edge: int = DEFAULT_MAT_IMAGE_MAX_EDGE
    #: The key everything paid runs through. Optional: a deployment without one
    #: serves the whole catalogue and refuses only to *start* a discovery run,
    #: which is a far better failure than refusing to boot.
    openrouter_api_key: str | None = None
    #: How this deployment identifies itself to the museum APIs phase 2 asks.
    #: **Optional, and its absence is what switches phase 2 off**: the Art
    #: Institute's API is open but asks callers to name themselves and give a
    #: contact address, and sending someone else's identifier — or a default
    #: pretending to be one — would be this product misrepresenting whoever runs
    #: it to a third party. So there is no default, and a deployment that has not
    #: set one resolves no images rather than resolving them anonymously.
    artic_user_agent: str | None = None

    @property
    def discovery_settings(self) -> DiscoverySettings:
        """The discovery allowances and prices, as the service layer wants them.

        Composed here for the same reason `tv_artwork_box` is: every input is a
        deployment value, and the service that reads them should take one object
        it can be handed in a test rather than eight it has to be given.
        """
        return DiscoverySettings(
            approval_threshold=self.approval_threshold,
            phase1_search_allowance=self.phase1_search_allowance,
            phase2_searches_per_work=self.phase2_searches_per_work,
            search_cost_usd=self.search_cost_usd,
            input_cost_usd_per_mtok=self.input_cost_usd_per_mtok,
            output_cost_usd_per_mtok=self.output_cost_usd_per_mtok,
            phase1_input_tokens=self.phase1_input_tokens,
            phase1_output_tokens=self.phase1_output_tokens,
        )

    @property
    def thumbnails_path(self) -> Path:
        """Where the browser surface's thumbnails are cached.

        Derived and device-independent, so it is regenerated rather than
        transported. Deliberately **not** `tv-thumbs/`, which holds images
        downloaded from the television keyed by its own content ids — per-device
        television state, the class this catalogue exists to keep out.
        """
        return self.art_root / THUMBNAILS_DIRNAME

    @property
    def originals_path(self) -> Path:
        """Where acquired master images live.

        Upstream rather than derived: nothing regenerates these, so this is the
        directory a backup would have to carry if the image tree were backed up
        at all — and the recorded decision is that it is not, because
        re-acquisition refills it from the catalogue.
        """
        return self.art_root / ORIGINALS_DIRNAME

    @property
    def ready_path(self) -> Path:
        """Where composed television canvases live.

        Derived and regenerable, so a lost `ready/` costs a re-render rather than
        a re-acquisition — which is why the backup carries neither this nor the
        originals beside it. Specific to the television in a way `thumbs/` is
        not: the mat is drawn to this panel's physical size.
        """
        return self.art_root / READY_DIRNAME

    @property
    def tile_cache_path(self) -> Path:
        """Working space for tiled fetches, reclaimed per work as each completes."""
        return self.art_root / TILE_CACHE_DIRNAME

    @property
    def previews_path(self) -> Path:
        """Where phase 2 caches the previews a review card shows.

        Inside `ART_ROOT` because every catalogue path is relative to it, and in
        its own directory because these files are disposable in a way nothing
        else under that root is — deletable as soon as their candidate work is
        accepted or rejected, and never a loss when they go.
        """
        return self.art_root / PREVIEWS_DIRNAME

    @property
    def tv_pixels_per_inch(self) -> float:
        """Canvas pixels to an inch on the wall, from the panel's own geometry.

        Derived rather than configured: a diagonal and a pixel count already fix
        it, and a third setting that could disagree with the other two is a way
        for a deployment to be quietly wrong about how big anything is.
        """
        diagonal_px = (self.tv_panel_width_px**2 + self.tv_panel_height_px**2) ** 0.5
        return diagonal_px / self.tv_panel_diagonal_inches

    @property
    def tv_artwork_box(self) -> ArtworkBox:
        """The region of the television canvas an artwork is rendered into.

        Composed here because every input is a deployment value: the panel, the
        mat in inches, and the floor. The bottom margin is deeper than the top,
        so the vertical mat is not twice the horizontal one — a work judged
        against a four-equal-sides approximation would be reported as larger on
        the wall than it will actually appear.

        **The mat is rounded to whole pixels before anything is subtracted, and
        the bottom margin is derived from that rounded top.** A mat is drawn in
        pixels, so this is the arithmetic the compositor will do; carrying
        fractions through and rounding at the end gives a box a pixel or two
        different from the one that ends up on the panel. On the reference 42"
        4K Frame it reproduces `nonfunctional-requirements.md`'s own worked
        example exactly — 262 px of mat, a 3316 x 1597 box — which is the
        strongest available evidence that the default bottom weighting matches
        what that example was drawn from.
        """
        top_mat_px = round(self.mat_width_inches * self.tv_pixels_per_inch)
        bottom_mat_px = round(top_mat_px * self.mat_bottom_weight)
        return ArtworkBox(
            width=max(1, self.tv_panel_width_px - 2 * top_mat_px),
            height=max(1, self.tv_panel_height_px - top_mat_px - bottom_mat_px),
            pixels_per_inch=self.tv_pixels_per_inch,
            floor_inches=self.resolution_floor_inches,
        )

    @classmethod
    def from_env(cls) -> Settings:
        """Resolve from the environment, failing on anything missing.

        `ART_ROOT` has no default on purpose. A plausible-looking one would
        write the catalogue somewhere unintended and look like it had worked.
        """
        load_dotenv(override=True)
        art_root = Path(_require("ART_ROOT"))
        return cls(
            art_root=art_root,
            catalogue_path=art_root / CATALOGUE_FILENAME,
            manifest_path=art_root / MANIFEST_FILENAME,
            heartbeat_path=art_root / HEARTBEAT_FILENAME,
            # Loopback by default: the plane is reached over an overlay network
            # rather than by being exposed on the LAN, and a default that binds
            # every interface is a decision no one made.
            host=os.environ.get("CURATION_HOST") or DEFAULT_HOST,
            port=_port("CURATION_PORT", DEFAULT_PORT),
            rotation_interval_seconds=_positive_int("ROTATION_INTERVAL_SECONDS", DEFAULT_ROTATION_INTERVAL_SECONDS),
            rotation_shuffle=_flag("ROTATION_SHUFFLE", DEFAULT_ROTATION_SHUFFLE),
            # `_counted` rather than `_positive_int`: zero means "do not sweep",
            # which is a deployment's to choose, where a rotation interval of
            # zero is simply broken.
            preview_sweep_interval_seconds=_counted("PREVIEW_SWEEP_INTERVAL_SECONDS", DEFAULT_PREVIEW_SWEEP_INTERVAL_SECONDS),
            tv_panel_width_px=_positive_int("TV_PANEL_WIDTH_PX", DEFAULT_TV_PANEL_WIDTH_PX),
            tv_panel_height_px=_positive_int("TV_PANEL_HEIGHT_PX", DEFAULT_TV_PANEL_HEIGHT_PX),
            tv_panel_diagonal_inches=_positive_float("TV_PANEL_DIAGONAL_INCHES", DEFAULT_TV_PANEL_DIAGONAL_INCHES),
            mat_width_inches=_positive_float("MAT_WIDTH_INCHES", DEFAULT_MAT_WIDTH_INCHES),
            mat_bottom_weight=_positive_float("MAT_BOTTOM_WEIGHT", DEFAULT_MAT_BOTTOM_WEIGHT),
            resolution_floor_inches=_positive_float("RESOLUTION_FLOOR_INCHES", DEFAULT_RESOLUTION_FLOOR_INCHES),
            acquisition_user_agent=os.environ.get("ACQUISITION_USER_AGENT") or DEFAULT_ACQUISITION_USER_AGENT,
            # Resolved off `PATH` by name, and configurable because it is the one
            # dependency this plane does not install: a deployment that built it
            # from source or keeps it outside `PATH` sets the path here rather
            # than editing a module.
            tile_binary=os.environ.get("DEZOOMIFY_PATH") or DEFAULT_TILE_BINARY,
            tile_max_pixels=_positive_int("TILE_MAX_PIXELS", DEFAULT_TILE_MAX_PIXELS),
            tile_timeout_seconds=_positive_int("TILE_TIMEOUT_SECONDS", DEFAULT_TILE_TIMEOUT_SECONDS),
            max_image_bytes=_positive_int("MAX_IMAGE_BYTES", DEFAULT_MAX_IMAGE_BYTES),
            # Positive rather than counted: a floor of zero is not a cautious
            # deployment's choice, it is the guard switched off — and the thing it
            # guards is the one file in this product that cannot be re-derived.
            min_free_bytes=_positive_int("MIN_FREE_BYTES", DEFAULT_MIN_FREE_BYTES),
            # Zero is allowed throughout rather than refused: a threshold of zero
            # gates every run, and an allowance of zero forbids searching. Both
            # are coherent settings for a cautious deployment, and refusing them
            # would be this module inventing a policy nobody wrote.
            approval_threshold=_counted("DISCOVERY_APPROVAL_THRESHOLD", DEFAULT_DISCOVERY_APPROVAL_THRESHOLD),
            phase1_search_allowance=_counted("DISCOVERY_PHASE1_SEARCH_ALLOWANCE", DEFAULT_PHASE1_SEARCH_ALLOWANCE),
            phase2_searches_per_work=_counted("DISCOVERY_PHASE2_SEARCHES_PER_WORK", DEFAULT_PHASE2_SEARCHES_PER_WORK),
            search_cost_usd=_priced("DISCOVERY_SEARCH_COST_USD", DEFAULT_SEARCH_COST_USD),
            input_cost_usd_per_mtok=_priced("DISCOVERY_INPUT_COST_USD_PER_MTOK", DEFAULT_INPUT_COST_USD_PER_MTOK),
            output_cost_usd_per_mtok=_priced("DISCOVERY_OUTPUT_COST_USD_PER_MTOK", DEFAULT_OUTPUT_COST_USD_PER_MTOK),
            phase1_input_tokens=_counted("DISCOVERY_PHASE1_INPUT_TOKENS", DEFAULT_PHASE1_INPUT_TOKENS),
            phase1_output_tokens=_counted("DISCOVERY_PHASE1_OUTPUT_TOKENS", DEFAULT_PHASE1_OUTPUT_TOKENS),
            discovery_model=os.environ.get("DISCOVERY_MODEL") or DEFAULT_DISCOVERY_MODEL,
            # Positive rather than merely counted: zero is not a coherent output
            # reservation, and a request reserving nothing is refused by the
            # provider rather than run cheaply.
            discovery_max_output_tokens=_positive_int("DISCOVERY_MAX_OUTPUT_TOKENS", DEFAULT_DISCOVERY_MAX_OUTPUT_TOKENS),
            discovery_search_results=_counted("DISCOVERY_SEARCH_RESULTS", DEFAULT_DISCOVERY_SEARCH_RESULTS),
            discovery_search_engine=os.environ.get("DISCOVERY_SEARCH_ENGINE") or DEFAULT_DISCOVERY_SEARCH_ENGINE,
            mat_model=os.environ.get("MAT_MODEL") or DEFAULT_MAT_MODEL,
            # Positive for the same reason the discovery reservation is: a
            # request reserving nothing is refused by the provider, not run free.
            mat_max_output_tokens=_positive_int("MAT_MAX_OUTPUT_TOKENS", DEFAULT_MAT_MAX_OUTPUT_TOKENS),
            mat_image_max_edge=_positive_int("MAT_IMAGE_MAX_EDGE", DEFAULT_MAT_IMAGE_MAX_EDGE),
            openrouter_api_key=os.environ.get("OPENROUTER_API_KEY") or None,
            artic_user_agent=os.environ.get("ARTIC_USER_AGENT") or None,
        )

    def redacted(self) -> dict[str, object]:
        """Every resolved value, with secrets reported as present rather than shown.

        The repository is public and the journal gets read over someone's
        shoulder during a failure — which is exactly when logging is turned up.
        Presence is still reported, because "is the key even set" is the first
        question a misconfiguration raises and answering it costs nothing.
        """
        return {
            name: ("<set>" if getattr(self, name) else "<unset>") if name in _SECRET_FIELDS else getattr(self, name)
            for name in self.__dataclass_fields__
        }


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise ConfigError(f"{name} is not set. Copy .env.example to .env and set {name}.")
    return value


def _port(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}. Check .env.") from exc
    if not 1 <= port <= 65535:
        raise ConfigError(f"{name} must be between 1 and 65535, got {port}. Check .env.")
    return port


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}. Check .env.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero, got {value}. Check .env.")
    return value


def _positive_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a number, got {raw!r}. Check .env.") from exc
    if value <= 0:
        raise ConfigError(f"{name} must be greater than zero, got {value}. Check .env.")
    return value


def _counted(name: str, default: int) -> int:
    """Read a whole number that may be zero.

    Distinct from `_positive_int`, which refuses zero because a rotation interval
    or a panel dimension of zero is a broken deployment. Zero is a real answer
    for a count of things a run is *allowed* to do: no searches, or a gate on
    every run.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be a whole number, got {raw!r}. Check .env.") from exc
    if value < 0:
        raise ConfigError(f"{name} counts things and cannot be negative, got {value}. Check .env.")
    return value


def _priced(name: str, default: str) -> Decimal:
    """Read a price as `Decimal`, never through `float`.

    The default is a string for the same reason: `Decimal(0.005)` carries the
    binary approximation of a tenth of a cent into every figure derived from it,
    and the figures here are what a curator authorises spending against.
    """
    raw = os.environ.get(name) or default
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise ConfigError(f"{name} must be a decimal number of US dollars, got {raw!r}. Check .env.") from exc
    if value < 0:
        raise ConfigError(f"{name} is a price and cannot be negative, got {value}. Check .env.")
    return value


def _flag(name: str, default: bool) -> bool:
    """Read a boolean, refusing anything that is not unmistakably one.

    Python's `bool("false")` is True, so a lenient reader turns a deliberate
    "off" into "on" and reports nothing. Every accepted spelling is listed.
    """
    raw = os.environ.get(name)
    if not raw:
        return default
    text = raw.strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"{name} must be true or false, got {raw!r}. Check .env.")
