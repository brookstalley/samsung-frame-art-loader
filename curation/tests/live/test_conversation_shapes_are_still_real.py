"""What a real multi-turn exchange still looks like. **Spends real money.**

The durable form of the 2026-08-12 probe, in the style of
`test_openrouter_shapes_are_still_real.py` and under the same `live_api` marker.
It is not a correctness test — the captures under
`tests/fixtures/openrouter_conversation/` cover that, and they are what the fakes
are built from. It is what fails when OpenRouter, or the routed model, stops
matching what this chunk was built against.

Four turns with an image on the second, because that is the exact arrangement the
probe measured and the one whose findings the conversation depends on:

- the whole history travels and the provider keeps none of it;
- an image left in the history is re-sent, re-billed and genuinely re-read;
- every turn carries its own `usage.cost`, which is the `conversation_tokens`
  row one-for-one;
- reasoning must be switched off, or an open-ended turn returns empty content
  and is billed in full.

```sh
cd curation && uv run pytest -m live_api -n0     # SPENDS REAL MONEY
```
"""

import base64
import io
import os
from decimal import Decimal

import pytest
from PIL import Image

from curation.config import DEFAULT_CONVERSATION_MAX_OUTPUT_TOKENS, DEFAULT_CONVERSATION_MODEL
from curation.discovery.conversation import REASONING_OFF, REPLY_SCHEMA
from curation.discovery.openrouter import ImageAttachment, Message, OpenRouterClient

pytestmark = pytest.mark.live_api


@pytest.fixture
def client() -> OpenRouterClient:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        pytest.skip("OPENROUTER_API_KEY is not set; this probe needs a real key and spends real money.")
    return OpenRouterClient(
        key,
        model=os.environ.get("CONVERSATION_MODEL") or DEFAULT_CONVERSATION_MODEL,
        max_output_tokens=DEFAULT_CONVERSATION_MAX_OUTPUT_TOKENS,
    )


@pytest.fixture
def picture() -> ImageAttachment:
    """A small synthetic image, so the probe depends on no operator's masters.

    Pillow is a hard dependency of this plane — the mat engine encodes with it —
    so it is imported rather than `importorskip`ed. A skip here would put this
    directory among the ones CI has to `--ignore`, and `tests/live` is the one
    directory whose whole point is that CI collects and runs it.
    """
    frame = Image.new("RGB", (256, 256), (32, 64, 128))
    buffer = io.BytesIO()
    frame.save(buffer, format="JPEG", quality=85)
    return ImageAttachment(base64_data=base64.b64encode(buffer.getvalue()).decode("ascii"), media_type="image/jpeg")


def test_a_four_turn_thread_still_answers_and_still_prices_every_turn(client, picture):
    """The whole arrangement, in one thread, asserting what each turn cost."""
    thread = [Message(role="user", text="You are helping choose art for a calm wall. Reply in one short sentence.")]
    costs = []

    first = client.complete_thread(messages=thread, reasoning=REASONING_OFF)
    assert first.content.strip(), f"an open-ended turn returned nothing ({first.finish_reason})"
    costs.append(first.cost_usd)
    thread.append(Message(role="assistant", text=first.content))

    thread.append(
        Message(
            role="user",
            text="Here is a picture I am considering. In one short sentence, say whether it suits that.",
            image=picture,
        )
    )
    second = client.complete_thread(messages=thread, reasoning=REASONING_OFF)
    assert second.content.strip()
    costs.append(second.cost_usd)
    thread.append(Message(role="assistant", text=second.content))

    thread.append(Message(role="user", text="In one short sentence, name one artist in that vein."))
    third = client.complete_thread(messages=thread, reasoning=REASONING_OFF)
    costs.append(third.cost_usd)
    thread.append(Message(role="assistant", text=third.content))

    # Two turns after the image was sent. The control for this in the probe was a
    # thread with no image, which answered "you have not yet provided the work".
    thread.append(Message(role="user", text="What colour dominates the picture I showed you earlier?"))
    fourth = client.complete_thread(messages=thread, reasoning=REASONING_OFF)
    costs.append(fourth.cost_usd)

    assert all(cost > Decimal(0) for cost in costs), f"a turn came back unpriced: {costs}"
    # The image is still in the history and still being paid for, which is the
    # finding a cost model would otherwise get wrong in both directions.
    assert fourth.input_tokens > first.input_tokens
    assert "blue" in fourth.content.lower(), f"the model no longer re-reads a resent image: {fourth.content!r}"


def test_the_schema_the_conversation_asks_for_is_still_honoured(client):
    """The envelope every turn is parsed from, against the live provider."""
    import json

    completion = client.complete_thread(
        messages=[Message(role="user", text="Suggest one artist for a calm, contemplative wall.")],
        schema=REPLY_SCHEMA,
        schema_name="conversation_reply",
        reasoning=REASONING_OFF,
    )

    parsed = json.loads(completion.content)
    assert isinstance(parsed["reply"], str) and parsed["reply"].strip()
    assert isinstance(parsed["suggested"], list)


def test_reasoning_left_on_still_burns_the_whole_reservation(client):
    """The finding that cost the most to learn, kept as a live check.

    Recorded rather than asserted as a pass/fail on the *content*: what this
    pins is that the product is right to send `reasoning: {"enabled": false}`. If
    this ever starts returning content with reasoning on, the setting is no
    longer load-bearing and the note in `config.py` should say so.
    """
    completion = client.complete_thread(
        messages=[Message(role="user", text="Suggest a direction for a calm, contemplative wall.")]
    )

    if completion.content.strip():
        pytest.fail(
            "reasoning left on now returns content on this route. The 2026-08-12 measurement was ten empty, "
            f"fully-billed turns; this one answered {completion.content!r} at {completion.cost_usd}. "
            "Re-measure before relaxing REASONING_OFF."
        )
    assert completion.finish_reason == "length"
    assert completion.cost_usd > Decimal(0), "an empty reasoning-burned turn is still billed"
