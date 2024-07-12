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
    def __init__(self, width, height, greyscale_bits, artist_name, artist_lifespan, artwork_title, creation_date):
        self.width = width
        self.height = height
        self.greyscale_bits = greyscale_bits
        self.artist_name = artist_name
        self.artist_lifespan = artist_lifespan
        self.artwork_title = artwork_title
        self.creation_date = creation_date

    def create_label(self) -> Image:
        # Create a new image with the specified dimensions and greyscale color mode
        image = Image.new("L", (self.width, self.height), 255)  # 'L' mode is for greyscale
        draw = ImageDraw.Draw(image)

        # Dynamically calculate font sizes based on image dimensions
        title_font_size = self.width // 30
        subtitle_font_size = self.width // 45
        text_font_size = self.width // 50

        # Define fonts
        title_font = ImageFont.truetype("arial.ttf", title_font_size)
        subtitle_font = ImageFont.truetype("arial.ttf", subtitle_font_size)
        text_font = ImageFont.truetype("arial.ttf", text_font_size)

        # Define positions
        margin = self.width // 30
        current_height = margin

        # Draw the text
        draw.text((margin, current_height), self.artwork_title, font=title_font, fill=0)
        current_height += title_font.getsize(self.artwork_title)[1] + margin // 2

        draw.text((margin, current_height), f"By {self.artist_name} ({self.artist_lifespan})", font=subtitle_font, fill=0)
        current_height += subtitle_font.getsize(f"By {self.artist_name} ({self.artist_lifespan})")[1] + margin // 2

        draw.text((margin, current_height), f"Created in {self.creation_date}", font=text_font, fill=0)

        # return the image
        return image
