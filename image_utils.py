# import resizing from PIL
from PIL import Image

import cv2
import logging
import numpy as np
import os
import subprocess

logging.basicConfig(level=logging.INFO)

dezoomify_rs_path = "/Users/brookstalley/bin/dezoomify-rs"
dezoomify_params = "--max-width 8192 --max-height 8192 --compression 0"


# Enums for resizing options
class ResizeOptions:
    SCALE = "scaled"
    CROP = "cropped"


def get_average_color(image: Image):
    # skimage = io.imread(image)[:, :, :-1]

    # We don't need a giant image to get average color. If it is larger than 2048x2048, resize it. But do not overwrite the original image!
    max_size = 768
    skimage = np.array(image)
    if skimage.shape[0] > max_size or skimage.shape[1] > max_size:
        # If X is larger than Y, use max_size/X, otherwise use max_size/Y
        ratio = max_size / max(skimage.shape[0], skimage.shape[1])

        logging.info("Resizing image to get average color")
        skimage = skimage.resize((int(skimage.shape[1] * ratio), int(skimage.shape[0] * ratio)))

    average = skimage.mean(axis=0).mean(axis=0)
    pixels = np.float32(skimage.reshape(-1, 3))

    n_colors = 5
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
    flags = cv2.KMEANS_RANDOM_CENTERS

    _, labels, palette = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)
    _, counts = np.unique(labels, return_counts=True)
    dominant = palette[np.argmax(counts)]

    return average, dominant


def resize_image_with_matte(image: Image, resize_option, width, height) -> Image:
    # Get x and y dimensions
    x, y = image.size
    if (x == width) and (y == height):
        # image is already the correct size
        return image

    dominant_color = (0, 0, 0)
    if resize_option == ResizeOptions.SCALE:
        average, dominant = get_average_color(image)
        dominant_color = (
            int((dominant[0] + 127) / 2),
            int((dominant[1] + 127) / 2),
            int((dominant[2] + 127) / 2),
        )
    canvas = Image.new("RGB", (width, height), dominant_color)
    description_box = None
    if resize_option == ResizeOptions.SCALE:
        # determine whether to scale x or y to width x height
        if (x / width) > (y / height):
            x = width
            y = int(y * (width / x))
            image = image.resize((x, y), Image.Resampling.LANCZOS)
            # Get the bottom area for descriptions
            description_box = (0, y, width, height)
        else:
            x = int(x * (height / y))
            y = height
            image = image.resize((x, y), Image.Resampling.LANCZOS)
            # Get the right area for descriptions
            description_box = (x, 0, width, height)

        # paste image into center of canvas
        paste_box = (int((width - x) / 2), int((height - y) / 2))
        canvas.paste(image, paste_box)
        # Get the coordinates of the added borders

    elif resize_option == ResizeOptions.CROP:
        # first resize so the smallest dimension is width or height
        if (x / width) > (y / height):
            # The image's aspect ratio is wider than the target. Scale y to match target height and then crop x to match target width
            scale = height / y
            x = int(x * scale)
            image = image.resize((x, height), Image.Resampling.LANCZOS)
            crop_box = (
                int((x - width) / 2),
                0,
                int((x + width) / 2),
                height,
            )
            image = image.crop(crop_box)

        else:
            # The image's aspect ratio is taller than the target. Scale x to match target width and then crop y to match target height
            scale = width / x
            y = int(y * scale)
            image = image.resize((width, y), Image.Resampling.LANCZOS)
            crop_box = (
                0,
                int((y - height) / 2),
                width,
                int((y + height) / 2),
            )
            image = image.crop(crop_box)

        canvas.paste(image, (0, 0))
    return canvas, description_box


def resize_file_with_matte(in_file: str, out_file: str, width, height, resize_option):
    # load image from file
    # set decompression limit high
    Image.MAX_IMAGE_PIXELS = 933120000

    image = Image.open(in_file)
    resized, description_box = resize_image_with_matte(image, resize_option, width, height)

    # Save the resized image
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    if in_file.endswith(".jpg"):
        resized.save(out_file, "JPEG", quality=95)
    elif in_file.endswith(".png"):
        resized.save(out_file, "PNG")
    logging.info(f"Resized {in_file} to {out_file}")


async def get_google_file(url, download_dir: str, destination_fullpath: str) -> tuple[bool, str]:
    # Run dezoomify-rs, passing dezoomify_params as arguments and starting in the art_folder_raw directory
    # See https://github.com/lovasoa/dezoomify-rs for info
    cmdline = f"{dezoomify_rs_path} {dezoomify_params} {url}"
    logging.info(f"Running: {cmdline}")
    p = subprocess.Popen(
        f"{dezoomify_rs_path} {dezoomify_params} {url}",
        shell=True,
        cwd=download_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    p.wait()
    out, err = p.communicate()
    # get the output of the command
    if p.returncode != 0:
        logging.error(f"Error running dezoomify-rs: {p.returncode}")
        logging.error(out)
        logging.error(err)
        return False, None

    # Typical response is b"\x1b[38;5;10mImage successfully saved to '/Users/username/art/raw/Still, Clyfford; PH-129; 1949_0001.jpg' (current working directory: /Users/brookstalley/art/raw)\n"
    # Get the filename from the output
    out_file = out.decode("utf-8").split("'")[1]
    logging.info(f"Downloaded {out_file}")
    if destination_fullpath:
        os.rename(out_file, destination_fullpath)
        out_file = destination_fullpath
    return True, out_file
