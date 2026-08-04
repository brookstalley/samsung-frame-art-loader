"""Re-verify the vision facts the mat client is written against, live.

`openrouter-api-findings.md` states its own policy: prices and endpoint shapes
both move, so prose is not the durable form of a finding — a test is. These are
the vision-specific facts that file records, each asserted against the real API,
and each naming the client behaviour that breaks if it stops holding.

    cd curation && uv run pytest -m live_api

Deselected by default because it spends real money. The whole file costs about
half a cent at the shipped model's measured rate.
"""

import os
from pathlib import Path

import pytest
from PIL import Image

from curation.acquisition.color import parse_hex, rgb_to_lab
from curation.acquisition.mat import MAT_PROMPT, MAT_SCHEMA, MatEngine
from curation.config import DEFAULT_MAT_IMAGE_MAX_EDGE, DEFAULT_MAT_MAX_OUTPUT_TOKENS, DEFAULT_MAT_MODEL
from curation.discovery.openrouter import ImageAttachment, OpenRouterClient
from curation.persistence.records import MatMethod

pytestmark = pytest.mark.live_api


@pytest.fixture(scope="module")
def key() -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY is not set; these tests call the real API.")
    return api_key


@pytest.fixture(scope="module")
def artwork(tmp_path_factory) -> Path:
    """A synthetic work rather than a fetched one.

    The point here is the *API contract*, not mat quality — quality is the
    operator's corpus look through `tools/mat_corpus.py`. A generated image keeps
    this file free of a museum's availability, which would otherwise make a
    provider-shape test fail whenever ARTIC was slow.
    """
    path = tmp_path_factory.mktemp("mat") / "work.jpg"
    image = Image.new("RGB", (1200, 900), (28, 58, 94))
    image.paste(Image.new("RGB", (400, 300), (196, 142, 58)), (80, 80))
    image.paste(Image.new("RGB", (300, 200), (140, 40, 40)), (700, 500))
    image.save(path, format="JPEG", quality=92)
    return path


def _client(key: str, *, max_output_tokens: int = DEFAULT_MAT_MAX_OUTPUT_TOKENS) -> OpenRouterClient:
    return OpenRouterClient(key, model=DEFAULT_MAT_MODEL, max_output_tokens=max_output_tokens)


def test_an_image_travels_as_a_data_uri_and_the_response_shape_is_unchanged(key, artwork):
    """The finding that let the existing client be reused for vision at all: only
    the request differs. If the response grew a different shape for image calls,
    `_read_completion` would mis-parse every mat call while parsing every
    discovery call correctly."""
    import base64
    from io import BytesIO

    with Image.open(artwork) as image:
        frame = image.convert("RGB")
        frame.thumbnail((DEFAULT_MAT_IMAGE_MAX_EDGE, DEFAULT_MAT_IMAGE_MAX_EDGE), Image.Resampling.LANCZOS)
        buffer = BytesIO()
        frame.save(buffer, format="JPEG", quality=85)
    attachment = ImageAttachment(base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"), media_type="image/jpeg")

    completion = _client(key).complete(prompt=MAT_PROMPT, schema=MAT_SCHEMA, image=attachment)

    assert completion.content
    assert completion.model_id
    assert completion.input_tokens > 0
    assert completion.output_tokens > 0
    # Billed, and the figure is the provider's own. A cost of zero would mean the
    # `usage: {"include": true}` flag stopped being honoured, and every mat would
    # silently report having been free.
    assert completion.cost_usd > 0
    # No search ran, so the whole charge is inference and there are no citations.
    assert completion.citations == ()


def test_the_shipped_model_still_answers_the_schema_with_a_usable_colour(key, artwork):
    """The model advertises `response_format` but **not** `structured_outputs`, so
    the schema is a request rather than a contract. This is the check that the
    request is still being honoured — if it stops, mats do not break, they
    silently become mechanical, which is a far quieter failure."""
    choice = MatEngine(_client(key), image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE).choose(artwork)

    assert choice.method is MatMethod.VISION_MODEL, choice.fallback_detail
    assert parse_hex(choice.hex_rgb)
    assert choice.reason
    assert choice.model_id == DEFAULT_MAT_MODEL
    assert choice.cost_usd > 0


def test_the_shipped_reservation_clears_the_models_reasoning_budget(key, artwork):
    """**The failure that costs money and returns nothing**, and the reason
    `DEFAULT_MAT_MAX_OUTPUT_TOKENS` is a correctness value. A reservation too
    small for reasoning yields empty content with `finish_reason='length'`, billed
    in full — measured at 700 tokens, and hit intermittently at 2,000 during a
    corpus run, which is what raised the shipped figure. A model whose reasoning
    grew past the current reservation would push every mat to the fallback."""
    choice = MatEngine(_client(key), image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE).choose(artwork)

    assert (
        choice.fallback_detail is None
    ), f"the shipped reservation of {DEFAULT_MAT_MAX_OUTPUT_TOKENS} tokens no longer suffices: {choice.fallback_detail}"


def test_a_reservation_too_small_is_still_diagnosed_rather_than_blamed_on_the_model(key, artwork):
    """The other half, driven on purpose: an under-sized reservation must produce
    the message that names the setting. Reported as "the model failed" it would
    send whoever reads it to change models, which fixes nothing.

    Costs one deliberately-wasted call, which is the price of knowing the
    diagnosis still fires — it is the only signal distinguishing a client
    misconfiguration from a provider outage.
    """
    engine = MatEngine(_client(key, max_output_tokens=16), image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE)

    choice = engine.choose(artwork)

    assert choice.method is MatMethod.DOMINANT_COLOR_FALLBACK
    assert "MAT_MAX_OUTPUT_TOKENS" in choice.fallback_detail


def test_the_model_still_chooses_a_mat_darker_than_mid_grey(key, artwork):
    """The one quality property that is mechanical rather than subjective, and the
    one that decided the model: two rejected candidates proposed a near-white mat
    over a Rothko and a Mondrian, which is the failure that glares on an emissive
    panel.

    Asserted on a deliberately dark synthetic work, where there is no defensible
    reading that calls for a pale mat. On real art the bar is looser — a full
    corpus run put one work of thirty-three just over it — so this is a floor
    under the model's behaviour, not a restatement of the corpus look.
    """
    choice = MatEngine(_client(key), image_max_edge=DEFAULT_MAT_IMAGE_MAX_EDGE).choose(artwork)

    assert rgb_to_lab(parse_hex(choice.hex_rgb)).l < 50, f"{choice.hex_rgb} is lighter than mid-grey: {choice.reason}"
