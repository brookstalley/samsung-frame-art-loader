#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
art_label.py: A class to represent an art label

Copyright:
Copyright (c) 2024 Brooks Talley


"""

from art import ArtFile
import logging
from PIL import Image, ImageDraw, ImageFont
import re
import cairo
import gi

gi.require_version("Pango", "1.0")
gi.require_version("PangoCairo", "1.0")
from gi.repository import Pango, PangoCairo

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


class ArtLabel:
    def __init__(self, width, height, greyscale_bits, artfile: ArtFile):
        self.artfile = artfile

        self.width = width
        self.height = height

        self.line_spacing = 1.5
        self.margin = self.width // 50
        self.cursor_position = (self.margin, 0)

        # Regular expression to find tags
        self.tag_regex = re.compile(r"(<b>|</b>|<i>|</i>)")

    def get_image(self) -> Image:
        # Create a Cairo surface and context
        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, self.width, self.height)
        context = cairo.Context(surface)

        # Create a Pango layout
        layout = PangoCairo.create_layout(context)

        label_text = f'<span size="x-large" color="#000000"><b>{self.artfile.artist_name}</b>'

        if self.artist_lifespan:
            label_text += f" ({self.artist_lifespan})"
        label_text += "\n<span>"

        layout.set_markup(label_text, -1)
        font_description = Pango.FontDescription("Sans")
        layout.set_font_description(font_description)
        layout.set_spacing(Pango.units_from_double(10))

        # Get the text extents
        text_width, text_height = layout.get_size()
        text_width /= Pango.SCALE
        text_height /= Pango.SCALE

        # Center the text
        context.move_to((self.width - text_width) / 2, (self.height - text_height) / 2)

        # Render the text
        PangoCairo.show_layout(context, layout)
        buffer = surface.get_data()
        self.label_image = Image.frombuffer("RGBA", (self.width, self.height), buffer, "raw", "BGRA", 0, 1)
        return self.label_image

        # return the image
        return self.label_image
