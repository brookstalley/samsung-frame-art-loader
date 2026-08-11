"""Choosing a mat colour, and recording which producer chose it.

The failures asserted here are **measured**, not imagined: probing six candidate
vision models with real corpus images produced empty content billed in full,
content truncated mid-string, and a hex triplet with no leading `#`
(`.prawduct/artifacts/openrouter-api-findings.md`). Each is a test below, because
the chosen model advertises `response_format` without `structured_outputs` — the
schema is a request, so every one of these is an ordinary Tuesday rather than an
incident.

Driven through `httpx.MockTransport` so the code under test is the real client
building a real request; only the socket is replaced. A hand-rolled fake client
would let the image-encoding half — which is where the request shape differs from
every other call this product makes — go unexercised.
"""

import base64
import json
from decimal import Decimal
from io import BytesIO

import httpx
import pytest
from PIL import Image

from curation.acquisition.color import parse_hex, rgb_to_lab
from curation.acquisition.mat import MAT_PROMPT, MatEngine, dominant_color
from curation.discovery.openrouter import OpenRouterClient
from curation.persistence.records import MatMethod
from curation.services.errors import ServiceError


def _answered(content: str, *, finish_reason: str = "stop", cost: float = 0.00006626, model: str = "qwen/qwen3.7-flash"):
    """The measured vision response shape: identical to the text path but for the
    request, which is the finding that let the existing client be reused.

    Costs are plain JSON numbers here, as they are on the wire — the client is
    what turns them into `Decimal`, at the tokeniser, and a fixture that handed it
    one already converted would skip the conversion being relied on.
    """
    return {
        "model": model,
        "choices": [{"finish_reason": finish_reason, "message": {"content": content}}],
        "usage": {
            "prompt_tokens": 412,
            "completion_tokens": 168,
            "cost": cost,
            "cost_details": {"upstream_inference_cost": cost},
        },
    }


def _transport(payload, *, recorder: list | None = None, status: int = 200):
    def handle(request: httpx.Request) -> httpx.Response:
        if recorder is not None:
            recorder.append(json.loads(request.content))
        return httpx.Response(status, json=payload)

    return httpx.MockTransport(handle)


def _client(payload, *, recorder: list | None = None, status: int = 200, model: str = "qwen/qwen3.7-flash") -> OpenRouterClient:
    return OpenRouterClient(
        "test-key",
        model=model,
        max_output_tokens=2000,
        client=httpx.Client(transport=_transport(payload, recorder=recorder, status=status)),
    )


@pytest.fixture
def artwork(tmp_path):
    """A real JPEG, because the engine decodes and re-encodes what it is given."""
    path = tmp_path / "work.jpg"
    image = Image.new("RGB", (900, 600), (30, 60, 120))
    # A second block, so the dominant-colour fallback has a majority to find
    # rather than one flat colour that any implementation would return.
    image.paste(Image.new("RGB", (200, 150), (200, 40, 40)), (10, 10))
    image.save(path, format="JPEG", quality=90)
    return path


GOOD_ANSWER = json.dumps(
    {
        "hex_rgb": "#27285b",
        "lab_l": 18.4,
        "lab_a": 12.1,
        "lab_b": -28.7,
        "reason": "A deep indigo drawn from the work's own blues, darker than the picture so it does not glare.",
    }
)


class TestTheModelAnswers:
    def test_the_choice_is_recorded_as_the_model_s(self, artwork):
        engine = MatEngine(_client(_answered(GOOD_ANSWER)), image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.hex_rgb == "#27285b"
        assert choice.method is MatMethod.VISION_MODEL
        assert choice.model_id == "qwen/qwen3.7-flash"
        assert choice.fallback_detail is None

    def test_a_pale_model_answer_is_recorded_as_the_model_gave_it(self, artwork):
        """**The clamp binds the mechanical derivation and not this path**, and
        that exemption is a decision rather than an oversight, so it needs a test
        that fails if someone extends the ceiling across both.

        The colour here is L\\* 89 — far above the ceiling a derived colour is held
        to, and chosen for that. Darkening it would put a colour in the catalogue
        that no one selected, under a `method` saying a model chose it, which is the
        invisible substitution `MatColor.method` exists to end. Whether the model's
        answers deserve a bar of their own is open; it is not open that the answer
        may be edited on the way to being recorded without saying so."""
        pale = json.dumps(
            {
                "hex_rgb": "#e8e2d0",
                "lab_l": 89.4,
                "lab_a": -0.6,
                "lab_b": 8.2,
                "reason": "A warm off-white.",
            }
        )
        engine = MatEngine(_client(_answered(pale)), image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.hex_rgb == "#e8e2d0"
        assert choice.method is MatMethod.VISION_MODEL

    def test_the_model_s_own_lab_is_kept_rather_than_recomputed(self, artwork):
        """They can disagree, and the disagreement is the evidence: a hex that
        does not match the LAB beside it is a model that converted badly, not a
        model with unusual taste. Recomputing would erase that."""
        engine = MatEngine(_client(_answered(GOOD_ANSWER)), image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.lab_l == 18.4
        assert choice.lab_a == 12.1
        assert choice.lab_b == -28.7
        # And it is genuinely the model's, not the hex converted: the real LAB of
        # #27285b is nowhere near an a* of 12.1.
        assert rgb_to_lab(parse_hex("#27285b")).a != pytest.approx(12.1, abs=1.0)

    def test_the_reason_the_model_gave_is_carried(self, artwork):
        engine = MatEngine(_client(_answered(GOOD_ANSWER)), image_max_edge=768)

        assert "indigo" in engine.choose(artwork).reason

    def test_what_the_call_cost_is_reported(self, artwork):
        """A curator authorising a re-choice is entitled to know what it spends,
        and the provider's own figure is the only complete one."""
        engine = MatEngine(_client(_answered(GOOD_ANSWER)), image_max_edge=768)

        assert engine.choose(artwork).cost_usd == Decimal("0.00006626")

    def test_a_bare_hex_triplet_is_accepted_rather_than_sent_to_the_fallback(self, artwork):
        """Measured: a probed model returned `3F6F7A` with no leading `#`. It is
        unambiguously the colour it looks like, and refusing it would discard a
        perfectly good choice and pay for a mechanical one."""
        answer = json.dumps({"hex_rgb": "3F6F7A", "lab_l": 43, "lab_a": -12, "lab_b": -7, "reason": "Teal."})
        engine = MatEngine(_client(_answered(answer)), image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.hex_rgb == "#3f6f7a"
        assert choice.method is MatMethod.VISION_MODEL

    def test_an_upper_case_answer_is_stored_lower_case(self, artwork):
        """`record_mat_color` compares hex strings to decide whether a choice is
        new, so `#27285B` arriving where `#27285b` is in force would write a
        history row recording that nothing changed."""
        answer = json.dumps({"hex_rgb": "#27285B", "lab_l": 18, "lab_a": 12, "lab_b": -28, "reason": "Indigo."})
        engine = MatEngine(_client(_answered(answer)), image_max_edge=768)

        assert engine.choose(artwork).hex_rgb == "#27285b"


class TestTheRequestTheModelSees:
    def test_the_image_travels_as_a_data_uri_content_part(self, artwork):
        """The one place a vision request differs from every other call this
        product makes, and the reason the response reader needed no change."""
        sent: list = []
        engine = MatEngine(_client(_answered(GOOD_ANSWER), recorder=sent), image_max_edge=768)

        engine.choose(artwork)

        content = sent[0]["messages"][0]["content"]
        assert [part["type"] for part in content] == ["text", "image_url"]
        assert content[0]["text"] == MAT_PROMPT
        assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")

    def test_the_image_is_downscaled_to_the_configured_edge(self, artwork):
        """The encoded size *is* the input token count, so this is the only dial
        on what a mat call costs. A 900-pixel source must not travel whole."""
        sent: list = []
        engine = MatEngine(_client(_answered(GOOD_ANSWER), recorder=sent), image_max_edge=256)

        engine.choose(artwork)

        encoded = sent[0]["messages"][0]["content"][1]["image_url"]["url"].split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded))) as sent_image:
            assert max(sent_image.size) == 256

    def test_a_portrait_work_stored_sideways_is_sent_upright(self, tmp_path):
        """A model shown a work lying on its side reasons about a different
        picture than the one the wall will show."""
        path = tmp_path / "rotated.jpg"
        image = Image.new("RGB", (400, 200), (90, 30, 30))
        exif = image.getexif()
        exif[0x0112] = 6  # rotate 90 CW on display
        image.save(path, format="JPEG", exif=exif)
        sent: list = []
        engine = MatEngine(_client(_answered(GOOD_ANSWER), recorder=sent), image_max_edge=512)

        engine.choose(path)

        encoded = sent[0]["messages"][0]["content"][1]["image_url"]["url"].split(",", 1)[1]
        with Image.open(BytesIO(base64.b64decode(encoded))) as sent_image:
            assert sent_image.height > sent_image.width

    def test_the_schema_is_sent_even_though_it_is_not_enforced(self, artwork):
        """The chosen model advertises `response_format` without
        `structured_outputs` and honoured the schema on every probed call. Both
        halves matter: sending it is worth it, depending on it is not."""
        sent: list = []
        engine = MatEngine(_client(_answered(GOOD_ANSWER), recorder=sent), image_max_edge=768)

        engine.choose(artwork)

        assert sent[0]["response_format"]["json_schema"]["strict"] is True
        assert "hex_rgb" in sent[0]["response_format"]["json_schema"]["schema"]["properties"]


class TestTheFallback:
    @pytest.mark.parametrize(
        ("content", "finish_reason"),
        [
            pytest.param("", "length", id="empty and cut off at the reservation"),
            pytest.param("", "stop", id="empty with nothing to say"),
            pytest.param('{"hex_rgb": "#27285b", "reason": "Truncated mid-str', "length", id="truncated mid-string"),
            pytest.param("Sure! I'd suggest a deep indigo.", "stop", id="prose instead of JSON"),
            pytest.param('{"hex_rgb": "indigo"}', "stop", id="a colour name rather than a triplet"),
            pytest.param('["#27285b"]', "stop", id="JSON that is not an object"),
            pytest.param("{}", "stop", id="an object with no colour in it"),
        ],
    )
    def test_an_unusable_answer_produces_a_recorded_mechanical_mat(self, artwork, content, finish_reason):
        engine = MatEngine(_client(_answered(content, finish_reason=finish_reason)), image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.method is MatMethod.DOMINANT_COLOR_FALLBACK
        assert parse_hex(choice.hex_rgb)
        assert choice.fallback_detail

    def test_a_cut_off_answer_names_the_setting_that_fixes_it(self, artwork):
        """The one failure whose cause is on this side of the wire. Reported as
        "the model failed" it would send whoever reads it to change models, which
        fixes nothing — the reservation did not clear the reasoning budget."""
        engine = MatEngine(_client(_answered("", finish_reason="length")), image_max_edge=768)

        assert "MAT_MAX_OUTPUT_TOKENS" in engine.choose(artwork).fallback_detail

    def test_a_billed_but_unusable_answer_still_reports_its_cost(self, artwork):
        """Measured: a reservation too small for reasoning returns nothing and is
        billed in full. A fallback reporting zero would under-report real spend."""
        engine = MatEngine(_client(_answered("", finish_reason="length", cost=0.00031475)), image_max_edge=768)

        assert engine.choose(artwork).cost_usd == Decimal("0.00031475")

    def test_a_provider_refusal_falls_back_rather_than_raising(self, artwork):
        """403 is an exhausted key and 402 an unaffordable reservation. Neither is
        retried and neither leaves the work unrenderable: it gets a mechanical mat
        with the refusal recorded."""
        engine = MatEngine(_client({"error": {"message": "Key limit exceeded"}}, status=403), image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.method is MatMethod.DOMINANT_COLOR_FALLBACK
        assert "could not be reached" in choice.fallback_detail

    def test_a_deployment_with_no_key_still_gets_a_mat(self, artwork):
        """Serving the whole catalogue without paying for anything is a supported
        deployment. Works there must still render, so the mat is mechanical and
        says so rather than absent."""
        engine = MatEngine(None, image_max_edge=768)

        choice = engine.choose(artwork)

        assert choice.method is MatMethod.DOMINANT_COLOR_FALLBACK
        assert "no OpenRouter key" in choice.fallback_detail
        assert choice.cost_usd == Decimal(0)

    def test_the_fallback_never_attributes_the_colour_to_a_model(self, artwork):
        """The confusion `method` exists to end: a mechanical colour credited to a
        model that never saw the work."""
        engine = MatEngine(_client(_answered("not json")), image_max_edge=768)

        assert engine.choose(artwork).model_id is None

    def test_unreadable_bytes_refuse_once_rather_than_falling_back(self, tmp_path):
        """**The one failure the fallback cannot absorb**, and it must not try.
        Both producers read the same file, so bytes that will not decode for the
        model will not quantise for a dominant colour either — and will not
        compose onto a canvas afterwards. A fallback here would raise the same
        exception a few lines later, from a site whose message names the dominant
        colour and sends the reader somewhere unrelated."""
        path = tmp_path / "not-an-image.jpg"
        path.write_bytes(b"certainly not a JPEG")
        engine = MatEngine(_client(_answered(GOOD_ANSWER)), image_max_edge=768)

        with pytest.raises(ServiceError, match="could not be read"):
            engine.choose(path)

    def test_unreadable_bytes_refuse_the_same_way_with_no_key_configured(self, tmp_path):
        """The keyless path reaches the fallback directly, so it needs its own
        check that an undecodable file is still one clear refusal rather than a
        raw Pillow error escaping from the quantiser."""
        path = tmp_path / "not-an-image.jpg"
        path.write_bytes(b"certainly not a JPEG")

        with pytest.raises(ServiceError, match="could not be read"):
            MatEngine(None, image_max_edge=768).choose(path)

    def test_the_fallback_colour_is_darker_than_the_dominant_colour_it_came_from(self, artwork):
        """The carried-over 2024 behaviour, and the reason it exists: a mat at the
        artwork's own lightness glares on an emissive panel."""
        engine = MatEngine(None, image_max_edge=768)

        choice = engine.choose(artwork)

        dominant_lightness = rgb_to_lab(dominant_color(artwork)).l
        assert rgb_to_lab(parse_hex(choice.hex_rgb)).l < dominant_lightness


class TestTheDominantColour:
    def test_a_flat_image_reports_its_own_colour(self, tmp_path):
        path = tmp_path / "flat.png"
        Image.new("RGB", (100, 100), (37, 99, 235)).save(path)

        assert dominant_color(path) == (37, 99, 235)

    def test_the_majority_colour_wins_rather_than_the_average(self, tmp_path):
        """An average of a mostly-blue picture with a red corner is purple, which
        is a colour that appears nowhere in the work."""
        path = tmp_path / "mostly.png"
        image = Image.new("RGB", (100, 100), (0, 0, 200))
        image.paste(Image.new("RGB", (20, 20), (200, 0, 0)), (0, 0))
        image.save(path)

        red, green, blue = dominant_color(path)

        assert blue > 150
        assert red < 60

    def test_a_greyscale_scan_is_read_without_raising(self, tmp_path):
        """Greyscale and CMYK both appear in museum downloads."""
        path = tmp_path / "grey.png"
        Image.new("L", (60, 60), 90).save(path)

        assert len(dominant_color(path)) == 3
