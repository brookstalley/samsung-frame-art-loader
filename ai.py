import os
import base64
from io import BytesIO
from openai import OpenAI
from PIL import Image
import config
import json
from colour import Color

mat_prompt = """I'm a curator at the museum that owns this artwork and we have rights to reproduce in all mediums. This artwork will be displayed on a 16:9 display, scaled so that there will be bars on either the sides or top and bottom. Think of these bars like the mat on a framed artwork. Suggest a mat color that will highlight the artwork. Think in LAB colorspace to align with human perception. Use best practices and color theory to produce an elegant color choice. Avoid greys if possible, and avoid having the mat seem brighter than the artwork since this will be on a LCD display. If in doubt, go darker. 

For your response, ONLY provide JSON with the RGB and LAB color values and a very short reason for this color choice. Do not explain aspect ratios or anything else. Just the preview image and the JSON.

JSON must be in the format:
{
  "mat_color": {
      "RGB": {"red": "123", "green" : "89", "blue": "98"},
      "RGB_HEX" : "#7B5962",
      "LAB": {"l": "96.34", "a": "103.27", "b": "67.31"}
  },
  "reason": "a very short reason for why this color was chosen"
}"""

mat_prompt2 = """I'm a curator at the museum that owns this artwork. This artwork will be displayed on a 16:9 display, scaled so that there will be bars on either the sides or top and bottom.  Pick a mat color that will look great. Here are some guidelines:

- Think carefully about the content of the artwork, the color palette, mood, and the overall aesthetic
- If you recognize the artwork or artist, consider their style and preferences
- Think in LAB colorspace to align with human perception
- Consider best practices for mat color choices
- Avoid greys unless the artwork is black and white or greyscale
- Avoid colors or brightnesses that may blend in with the artwork
- Only use saturated colors if most of the artwork is neutral and there is a small highlight to echo. 
- Remember that the final display will be 16:9, so the art's aspect ratio will determine the size of the mat
- When the mat is larger, the mat must be darker than the artwork

For your response, ONLY provide JSON with the RGB and LAB color values and the reasoning for this color choice.

JSON must be in the format:
{
  "mat_color": {
      "RGB": {"red": "123", "green" : "89", "blue": "98"},
      "RGB_HEX" : "#6B3952",
      "LAB": {"l": "96.34", "a": "103.27", "b": "67.31"}
  },
  "reason": "This abstract artwork by Mark Rothko is considered to have great emotional weight. The artwork's average LAB lightness is 51 and the portrait aspect ratio means the side bars will be quite large, so the mat must be darker to highlight the artwork. This desaturated purple mat complements the artwork's dominant green and brown colors, while mirroring the brighter purple accents in a more muted tone. "
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
