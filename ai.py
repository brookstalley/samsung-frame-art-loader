import os
import base64
from io import BytesIO
from openai import OpenAI
from PIL import Image
import config
import json
from colour import Color

mat_prompt = """I'm a curator at the museum that owns this artwork and we have rights to reproduce in all mediums. This artwork will be displayed on a 16:9 display, scaled so that there will be bars on either the sides or top and bottom. Think of these bars like the mat on a framed artwork. Suggest a mat color that will highlight the artwork. Think in LAB colorspace to align with human perception. Use best practices and color theory to produce an elegant color choice. Avoid greys if possible, and avoid having the mat seem brighter than the artwork since this will be on a LCD display. If in doubt, go darker. 

To help us visualize what it will look like in the museum, redraw this exact artwork, expanding to a 16:9 aspect ratio with the mat color you chose. Do not crop or scale the original, just pad the top or sides as needed. 

For your response, ONLY show the image and then provide JSON with the RGB and LAB color values and a very short reason for this color choice. Do not explain aspect ratios or anything else. Just the preview image and the JSON.

JSON must be in the format:
{
  "mat_color": {
      "RGB": {"red": "123", "green" : "89", "blue": "98"},
      "RGB_HEX" : "#7B5962",
      "LAB": {"l": "96.34", "a": "103.27", "b": "67.31"}
  },
  "reason": "a very short reason for why this color was chosen"
}"""

mat_prompt2 = """This artwork will be displayed on a 16:9 display, scaled so that there will be bars on either the sides or top and bottom. 

Think of these bars like the mat on a framed artwork. Suggest a mat color that will highlight the artwork. Use best practices and color theory to produce an elegant color choice that will not overpower the artwork on a LCD display.

Avoid making the mat brighter or more saturated than the artwork since this will be on a LCD display. If in doubt, go darker and less saturated. But avoid greys if there is a more interesting choice.

For your response, ONLY provide JSON with the color values and a very short reason for this color choice. Do not explain aspect ratios or anything else. Just the preview image and the JSON.

JSON must be in the format:
{
  "mat_color": {
      "RGB": {"red": "123", "green" : "89", "blue": "98"},
      "RGB_HEX" : "#7B5962",
  },
  "reason": "a very short reason for why this color was chosen"
}"""


def ai_mat_color(image: Image) -> Color:
    # get base64 encoded image from the PIL.Image
    my_image = image.copy()
    max_size = (1024, 1024)
    # ensure the image is no bigger than max, but do not modify the image that was passed in
    my_image.thumbnail(max_size, Image.Resampling.LANCZOS)

    buffered = BytesIO()
    my_image.save(buffered, format="PNG")
    encoded_image = base64.b64encode(buffered.getvalue()).decode("utf-8")
    # Creaet the GPT-4o request
    prompt = f"Pick a mat color for this image. Respond only in JSON"
    client = OpenAI(api_key=config.OPENAI_KEY)
    good_result = False
    tries = 0
    while not good_result and tries < 5:
        print(f"Getting mat color from AI")
        response = client.chat.completions.create(
            model="gpt-4o",
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": "You are a helpful assistant designed to output JSON."},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": mat_prompt2},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{encoded_image}"}},
                    ],
                },
            ],
            max_tokens=2000,
        )
        response_str = response.choices[0].message.content
        try:
            response = json.loads(response_str)
            rgb_hex = response["mat_color"]["RGB_HEX"]
            reason = response["reason"]
            good_result = True
        except json.JSONDecodeError:
            print(f"Bad response from AI: {response_str}")
            print(f"Trying again")
            tries += 1
        except KeyError:
            print(f"Bad response from AI: {response_str}")
            print(f"Trying again")
            tries += 1
    if good_result:
        # print(f"AI response: {response}")
        return Color(rgb_hex), reason
    else:
        return None
