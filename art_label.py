#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
art_label.py: A class to represent an art label

Copyright:
Copyright (c) 2024 Brooks Talley


"""

import logging
from PIL import Image, ImageDraw, ImageFont

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


class ArtLabel:
    def __init__(
        self, width, height, greyscale_bits, artist_name, artist_lifespan, artwork_title, creation_date, medium, description
    ):
        self.width = width
        self.height = height
        self.greyscale_bits = greyscale_bits
        self.artist_name = artist_name
        self.medium = medium
        self.description = description
        self.artist_lifespan = artist_lifespan
        self.artwork_title = artwork_title
        self.creation_date = creation_date

    def get_height_for_text(self, font, text):
        bbox = font.getbbox(text)
        height = bbox[3] - bbox[1]
        return height

    def create_label(self) -> Image:
        # Create a new image with the specified dimensions and greyscale color mode
        image = Image.new("L", (self.width, self.height), 255)  # 'L' mode is for greyscale
        draw = ImageDraw.Draw(image)

        # Dynamically calculate font sizes based on image dimensions
        title_font_size = self.width // 30
        subtitle_font_size = self.width // 45
        text_font_size = self.width // 50

        # Define fonts
        title_font = ImageFont.truetype("fonts/LiberationSans-Bold.ttf", title_font_size)
        subtitle_font = ImageFont.truetype("fonts/LiberationSans-Regular.ttf", subtitle_font_size)
        text_font = ImageFont.truetype("fonts/LiberationSans-Regular.ttf", text_font_size)
        medium_font = ImageFont.truetype("fonts/LiberationSans-Italic.ttf", text_font_size)

        # Define positions
        margin = self.width // 30
        current_height = margin
        line_height_margin = 10
        line_spacing = 1.5

        # Draw the text
        draw.text((margin, current_height), self.artwork_title, font=title_font, fill=0)
        current_height += line_spacing * self.get_height_for_text(title_font, self.artwork_title) + margin // 2

        artist_line = f"{self.artist_name}"
        if self.artist_lifespan:
            artist_line += f" ({self.artist_lifespan})"
        draw.text((margin, current_height), artist_line, font=subtitle_font, fill=0)
        current_height += line_spacing * self.get_height_for_text(subtitle_font, artist_line) + margin // 2

        if self.creation_date and self.creation_date != "":
            draw.text((margin, current_height), f"Created {self.creation_date}", font=subtitle_font, fill=0)
            current_height += (
                line_spacing + self.get_height_for_text(subtitle_font, f"Created {self.creation_date}") + margin // 2
            )

        if self.medium and self.medium != "":
            draw.text((margin, current_height), f"Medium: {self.medium}", font=text_font, fill=0)
            current_height += line_spacing * self.get_height_for_text(text_font, f"Medium: {self.medium}") + margin // 2

        if self.description and self.description != "":
            draw.text((margin, current_height), f"{self.description}", font=text_font, fill=0)
            current_height += self.get_height_for_text(text_font, self.description) + margin // 2 + line_height_margin

        # return the image
        return image
