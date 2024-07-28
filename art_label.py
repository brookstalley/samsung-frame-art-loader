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

        self.fontsize_regular = round(self.width / 25.0)
        self.fontsize_title = round(self.fontsize_regular * 1.8)
        self.fontsize_subtitle = round(self.fontsize_regular * 1.3)

        self.font_regular = "LiberationSans-Regular"
        self.font_bold = "LiberationSans-Bold"
        self.font_italic = "LiberationSans-Italic"
        self.font_bolditalic = "LiberationSans-BoldItalic"

        self.line_spacing = 1.5
        self.margin = self.width // 50
        self.cursor_position = (self.margin, 0)

        # Regular expression to find tags
        self.tag_regex = re.compile(r"(<b>|</b>|<i>|</i>)")

    def get_box_for_text(self, font, text):
        bbox = font.getbbox(text)
        height = bbox[3] - bbox[1]
        width = bbox[2] - bbox[0]
        return bbox, width, height

    def get_current_font(self, style_stack):
        is_bold = "b" in style_stack
        is_italic = "i" in style_stack
        if is_bold and is_italic:
            return self.font_bolditalic
        elif is_bold:
            return self.font_bold
        elif is_italic:
            return self.font_italic
        else:
            return self.font_regular

    def add_text(self, text, font_size):
        draw = ImageDraw.Draw(self.label_image)
        x = self.cursor_position[0]
        y = self.cursor_position[1]

        # Stack to track the current styles
        style_stack = []

        # Split the text and iterate through parts
        parts = self.tag_regex.split(text)
        line_height = 0
        for part in parts:
            if part == "<b>":
                style_stack.append("b")
            elif part == "</b>":
                style_stack.remove("b")
            elif part == "<i>":
                style_stack.append("i")
            elif part == "</i>":
                style_stack.remove("i")
            else:
                # Draw the text part with the current style
                current_font_name = self.get_current_font(style_stack)
                # load the truetype font
                current_font = ImageFont.truetype(f"fonts/{current_font_name}.ttf", font_size)

                draw.text((x, y), part, font=current_font, fill=0)
                part_box, part_width, part_height = self.get_box_for_text(current_font, part)
                line_height = max(line_height, part_height)
                x += part_width

        # TODO: Support word wrap
        self.cursor_position = (self.margin, self.cursor_position[1] + round(self.line_spacing * part_height))

    def get_image(self) -> Image:
        # Create a new image with the specified dimensions and greyscale color mode
        self.label_image = Image.new("L", (self.width, self.height), 255)  # 'L' mode is for greyscale

        artist_line = f"<b>{self.artist_name}</b>"
        if self.artist_lifespan:
            artist_line += f" ({self.artist_lifespan})"
        self.add_text(artist_line, self.fontsize_title)

        artwork_line = f"<b>{self.artwork_title}</b>"
        if self.creation_date:
            artwork_line += f" ({self.creation_date})"
        self.add_text(artwork_line, self.fontsize_title)

        if self.medium and self.medium != "":
            self.add_text(f"<i>{self.medium}</i>", self.fontsize_subtitle)

        if self.description and self.description != "":
            # Descriptions may have paragraphs with line breaks, or with HTML <p></p>. Normalize to line breaks.
            self.description = self.description.replace("<p>", "\n\n").replace("</p>", "")
            self.add_text(f"{self.description}", self.fontsize_regular)

        # return the image
        return self.label_image
