import sys
import logging
import os
import random
import json
import argparse
import subprocess
import requests

# import resizing from PIL
from PIL import Image

import cv2
import numpy as np
from skimage import io

sys.path.append("../")

from samsungtvws import SamsungTVWS

# debug params: --always-generate --upload-all --resize-option cropped

# Add command line argument parsing
parser = argparse.ArgumentParser(description="Upload images to Samsung TV.")

parser.add_argument(
    "--debug", action="store_true", help="Enable debug mode to check if TV is reachable"
)
parser.add_argument(
    "--show-uploaded", action="store_true", help="Show uploaded images from TV"
)
parser.add_argument(
    "--ignore-uploaded",
    action="store_true",
    help="Ignore uploaded images and upload all",
)

parser.add_argument(
    "--setfile",
    type=str,
    help="Load art set from file",
)
parser.add_argument(
    "--always-generate", action="store_true", help="Always generate resized images"
)
parser.add_argument(
    "--always-download", action="store_true", help="Always download images from URLs"
)
parser.add_argument(
    "--delete-all", action="store_true", help="Delete all uploaded images"
)

args = parser.parse_args()

# Set the path to the folder containing the images
art_folder_raw = "/Users/brookstalley/art/raw"
art_folder_ready = "/Users/brookstalley/art/ready"

dezoomify_rs_path = "/Users/brookstalley/bin/dezoomify-rs"
dezoomify_params = "--max-width 8192 --max-height 8192 --compression 0"


UPLOADED_CATEGORY = "MY-C0002"

# Set the path to the file that will store the list of uploaded filenames
upload_list_path = "./uploaded_files.json"


def get_ready_fullpath(raw_filename, ready_folder, resize_option):
    # Get the filename of the ready file
    ready_fullpath = os.path.join(
        ready_folder,
        os.path.splitext(os.path.basename(raw_filename))[0]
        + "_"
        + resize_option
        + ".jpg",
    )
    return ready_fullpath


# Enums for resizing options
class ResizeOptions:
    SCALE = "scaled"
    CROP = "cropped"


class ImageRetrievers:
    DEZOZOM = "dezoomify"
    HTTP = "http"


class ArtFile:
    url: str = None
    resize_option: str = None
    raw_file: str = None
    raw_fullpath: str = None
    ready_file: str = None
    ready_fullpath: str = None

    def __init__(
        self,
        url=None,
        raw_file=None,
        raw_fullpath=None,
        ready_file=None,
        ready_fullpath=None,
        resize_option=None,
        retriever=None,
    ):
        self.url = url
        self.raw_file = raw_file
        self.resize_option = resize_option

    def process(self, always_download=False, always_generate=False):
        """Process the art file. Download the raw file if necessary, and generate the ready file."""
        """ TODO: Support files that are already downloaded and have no URL """
        raw_file_exists = False
        ready_file_exists = False
        if not self.url:
            raise Exception("URL is required")

        logging.debug(f"Processing {self.url}")
        self.retriever = image_retriever(self.url)

        # URL is specified
        if self.raw_file:
            self.raw_fullpath = art_folder_raw + "/" + self.raw_file
            if os.path.exists(self.raw_fullpath) and not always_download:
                raw_file_exists = True
            else:
                result, fullpath = get_image(self.url, self.raw_fullpath)
                if result:
                    # Only save the basename so the program is portable
                    self.raw_file = os.path.basename(fullpath)
                    self.raw_fullpath = fullpath
                    raw_file_exists = True
                else:
                    raise Exception("Error downloading image")

        else:
            # Raw file is not specified. For now always download because we can't get the filename from the URL
            result, fullpath = get_image(
                self.url, destination_fullpath=None, destination_dir=art_folder_raw
            )
            if result:
                raw_file_exists = True
                # Only save the basename so the program is portable
                self.raw_file = os.path.basename(fullpath)
                self.raw_fullpath = fullpath
            else:
                raise Exception("Error downloading image")

        self.ready_fullpath = get_ready_fullpath(
            self.raw_file, art_folder_ready, self.resize_option
        )

        if not os.path.exists(self.ready_fullpath) or always_generate:
            description_box = resize_file(
                self.raw_fullpath, self.ready_fullpath, 3840, 2160, self.resize_option
            )

    def to_json(self):
        # return a JSON representation of the art file, but only the fields that are needed to recreate the object
        return {
            "url": self.url,
            "raw_file": self.raw_file,
            "resize_option": self.resize_option,
        }


class ArtSet:
    name: str = None
    default_resize: str = None
    art_list: list[ArtFile] = []
    source_file: str = None

    def __init__(self, source_file, name, default_resize, art):
        self.name = name
        self.default_resize = default_resize
        self.art = art

    # Provide setter and gett for the art list
    def set_art(self, art_list: list[ArtFile]):
        self.art_list = art_list

    def get_art(self) -> list[ArtFile]:
        return self.art_list

    def add_art(self, art: ArtFile):
        self.art_list.append(art)

    def to_json(self):
        # return a JSON representation of the art set
        return {
            "schema_version": 1,
            "name": self.name,
            "default_resize": self.default_resize,
            "art": [art.to_json() for art in self.art_list],
        }


def get_http_image(
    url, destination_fullpath: str = None, destination_dir: str = None
) -> tuple[bool, str]:
    # Download the image from the URL
    logging.info(f"Downloading {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return False, None

    if destination_fullpath:
        filename = destination_fullpath
    else:
        filename = os.path.join(destination_dir, os.path.basename(url))

    with open(filename, "wb") as f:
        f.write(response.content)

    return True, filename


def image_retriever(url):
    # If the URL is a Google Arts and Culture URL, use dezoomify-rs to download the image
    if "artsandculture.google.com" in url:
        return ImageRetrievers.DEZOZOM
    else:
        return ImageRetrievers.HTTP


def get_image(
    url, destination_fullpath: str = None, destination_dir: str = None
) -> tuple[bool, str]:
    if image_retriever(url) == ImageRetrievers.DEZOZOM:
        return get_google_file(url, destination_fullpath)
    else:
        return get_http_image(url, destination_fullpath, destination_dir)


def get_average_color(image: Image):
    # skimage = io.imread(image)[:, :, :-1]

    # We don't need a giant image to get average color. If it is larger than 2048x2048, resize it. But do not overwrite the original image!
    
    skimage = np.array(image)
    if skimage.shape[0] > 1024 or skimage.shape[1] > 1024:
        logging.info("Resizing image to get average color")
        skimage = cv2.resize(skimage, (1024, 1024), interpolation=cv2.INTER_AREA)
    
    average = skimage.mean(axis=0).mean(axis=0)
    pixels = np.float32(skimage.reshape(-1, 3))

    n_colors = 5
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
    flags = cv2.KMEANS_RANDOM_CENTERS

    _, labels, palette = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)
    _, counts = np.unique(labels, return_counts=True)
    dominant = palette[np.argmax(counts)]

    return average, dominant


def resize_image(image: Image, resize_option, width, height) -> Image:
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


def resize_file(in_file: str, out_file: str, width, height, resize_option):
    # load image from file
    # set decompression limit high
    Image.MAX_IMAGE_PIXELS = 933120000

    image = Image.open(in_file)
    resized, description_box = resize_image(image, resize_option, width, height)

    # Save the resized image
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    if in_file.endswith(".jpg"):
        resized.save(out_file, "JPEG", quality=95)
    elif in_file.endswith(".png"):
        resized.save(out_file, "PNG")
    logging.info(f"Resized {in_file} to {out_file}")


def debug():
    # Check if TV is reachable in debug mode
    try:
        logging.info("Checking if the TV can be reached.")
        info = tv.rest_device_info()
        logging.info("If you do not see an error, your TV could be reached.")
        sys.exit()
    except Exception as e:
        logging.error("Could not reach the TV: " + str(e))
        sys.exit()


def get_available(tv, category=None):
    # Retrieve available art
    available_art = tv.art().available(category=category)
    return available_art


def show_available(tv, category=None):
    available_art = get_available(tv, category)
    logging.info("Available art:")
    for art in available_art:
        logging.info(art)


def delete_all_uploaded(tv):
    available_art = get_available(tv, UPLOADED_CATEGORY)
    logging.info(f"Deleting {len(available_art)} uploaded images")
    tv.art().delete_list([art["content_id"] for art in available_art])
    logging.info("Deleted all uploaded images")
    # Clear the list of uploaded filenames
    uploaded_files = []
    with open(upload_list_path, "w") as f:
        json.dump(uploaded_files, f)


def get_google_file(url, destination_fullpath: str = None) -> tuple[bool, str]:
    # Run dezoomify-rs, passing dezoomify_params as arguments and starting in the art_folder_raw directory
    cmdline = f"{dezoomify_rs_path} {dezoomify_params} {url}"
    logging.info(f"Running: {cmdline}")
    p = subprocess.Popen(
        f"{dezoomify_rs_path} {dezoomify_params} {url}",
        shell=True,
        cwd=art_folder_raw,
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


def get_google_list(URLs):
    # Get images from Google arts and culture
    logging.info("Getting images from Google Arts and Culture")
    for url in URLs:
        out_file = get_google_file(url)


def upload_files(tv, art_files: list[ArtFile]):
    for art_file in art_files:
        if not os.path.exists(art_file.raw_file) or args.always_download:
            try:
                art_file.download()
            except Exception as e:
                logging.error("There was an error: " + str(e))
                sys.exit()

        if not os.path.exists(art_file.ready_file) or args.always_generate:
            pass


def get_uploaded_files():
    # Load the list of uploaded filenames from the file
    if os.path.isfile(upload_list_path) and not args.ignore_uploaded:
        with open(upload_list_path, "r") as f:
            uploaded_files = json.load(f)
    else:
        uploaded_files = []

    return uploaded_files


# Increase debug level
logging.basicConfig(level=logging.INFO)

# Set your TVs local IP address. Highly recommend using a static IP address for your TV.
tv = SamsungTVWS("10.23.17.139")

# Checks if the TV supports art mode
art_mode = tv.art().supported()
if not art_mode:
    logging.warning("Your TV does not support art mode.")
    sys.exit()

if args.debug:
    debug()

if args.show_uploaded:
    show_available(tv, UPLOADED_CATEGORY)
    sys.exit()

if args.delete_all:
    logging.info("Deleting all uploaded images")
    delete_all_uploaded(tv)

artsets = []

if args.setfile:
    with open(args.setfile, "r") as f:
        set_json = json.load(f)
    set_schema_version = set_json["schema_version"]
    set_name = set_json["name"]
    set_resize = set_json["default_resize"]
    set_art = set_json["art"]

    artset = ArtSet(args.setfile, set_name, set_resize, set_art)
    artsets.append(artset)

    for art_item in set_art:
        af = ArtFile()
        if "url" in art_item:
            af.url = art_item["url"]
        if "raw_file" in art_item:
            af.raw_file = art_item["raw_file"]
        if "resize_option" in art_item:
            af.resize_option = art_item["resize_option"]
        else:
            af.resize_option = set_resize

        af.process(args.always_download, args.always_generate)
        artset.add_art(af)
    f.close()
    # Now write the art set back to the file
    updated_json = artset.to_json()
    with open(args.setfile, "w") as f:
        # write the updated JSON in human readable format
        json.dump(updated_json, f, indent=4)

    f.close()

# Build the list of all ready files that need to be uploaded
files = []
for artset in artsets:
    for art in artset.get_art():
        files.append(art.ready_fullpath)

uploaded_files = get_uploaded_files()

# Remove the filenames of images that have already been uploaded
files = list(set(files) - set([f["file"] for f in uploaded_files]))
files_to_upload = files

# make a dict of local file : remote filenames from the uploaded_files JSON
remote_files = {f["file"]: f["remote_filename"] for f in uploaded_files}

if not files_to_upload:
    logging.info("No new images to upload.")
    sys.exit()

for file in files_to_upload:
    if not os.path.exists(file):
        logging.error(f"File {file} does not exist.")
        continue

    remote_filename = None
    logging.debug(f"Processing {file}")
    # if file is in the list of uploaded files, set the remote filename
    if file in remote_files.keys():
        remote_filename = remote_files[file]
        logging.info("Image already uploaded.")
        if not args.upload_all:
            # Select the image using the remote file name only if not in 'upload-all' mode
            logging.info("Setting existing image, skipping upload")
            tv.art().select_image(remote_filename, show=True)
    else:
        with open(file, "rb") as f:
            data = f.read()

        # Upload the file to the TV and select it as the current art, or select it using the remote filename if it has already been uploaded
        logging.info(f"Uploading new image: {file} ({len(data)} bytes)")

        try:
            if file.endswith(".jpg"):
                remote_filename = tv.art().upload(data, file_type="JPEG", matte="none")
            elif file.endswith(".png"):
                remote_filename = tv.art().upload(data, file_type="PNG", matte="none")
            # Add the filename to the list of uploaded filenames
            uploaded_files.append({"file": file, "remote_filename": remote_filename})

            tv.art().select_image(remote_filename, show=True)
        except Exception as e:
            logging.error("There was an error: " + str(e))

        # Save the list of uploaded filenames to the file
        # Get JSON of the final artset after processing
    with open(upload_list_path, "w") as f:
        json.dump(uploaded_files, f, indent=4)
