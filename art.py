import asyncio
import sys
import logging
import os
import random
import json
import argparse

import requests
import time

from image_utils import ResizeOptions, ImageSources
from image_utils import resize_file_with_matte, image_source, get_image
from metadata import get_google_metadata, get_file_metadata, get_artic_metadata

sys.path.append("../")

from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws import exceptions
from samsungtvws.remote import SendRemoteKey
from samsungtvws.async_remote import SamsungTVWSAsyncRemote


artsets = []
tv_address = "10.23.17.77"
tv_port = 8002

# debug params: --always-generate --upload-all --resize-option cropped


def parse_args():
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description="Upload images to Samsung TV.")

    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to check if TV is reachable",
    )
    parser.add_argument("--show-uploaded", action="store_true", help="Show uploaded images from TV")
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
    parser.add_argument("--always-generate", action="store_true", help="Always generate resized images")
    parser.add_argument("--always-metadata", action="store_true", help="Always retrieve metadata")

    parser.add_argument(
        "--always-download",
        action="store_true",
        help="Always download images from URLs",
    )
    parser.add_argument("--delete-all", action="store_true", help="Delete all uploaded images")
    parser.add_argument("--no-tv", action="store_true", help="Do not connect to TV")

    return parser.parse_args()


# Set the path to the folder containing the images
base_folder = "/home/brooks/art"
art_folder_raw = f"{base_folder}/raw"
art_folder_ready = f"{base_folder}/ready"

UPLOADED_CATEGORY = "MY-C0002"

# Set the path to the file that will store the list of uploaded filenames
upload_list_path = "./uploaded_files.json"


def get_ready_fullpath(raw_filename, ready_folder, resize_option):
    # Get the filename of the ready file
    ready_fullpath = os.path.join(
        ready_folder,
        os.path.splitext(os.path.basename(raw_filename))[0] + "_" + resize_option + ".jpg",
    )
    return ready_fullpath


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
        metadata=None,
    ):
        self.url = url
        self.raw_file = raw_file
        self.resize_option = resize_option
        self.metadata = metadata

    async def process(self, always_download=False, always_generate=False, always_metadata=False):
        """Process the art file. Download the raw file if necessary, and generate the ready file."""
        """ TODO: Support files that are already downloaded and have no URL """
        raw_file_exists = False
        ready_file_exists = False
        if not self.url:
            raise Exception("URL is required")

        logging.debug(f"Processing {self.url}")

        # URL is specified
        raw_file_exists = False
        if self.raw_file:
            self.raw_fullpath = art_folder_raw + "/" + self.raw_file
            if os.path.exists(self.raw_fullpath) and not always_download:
                raw_file_exists = True
        if not raw_file_exists:
            # Raw file is not specified or does not exist. For now always download because we can't get the filename from the URL
            result, fullpath = await get_image(self.url, destination_fullpath=None, destination_dir=art_folder_raw)
            if result:
                raw_file_exists = True
                # Only save the basename so the program is portable
                self.raw_file = os.path.basename(fullpath)
                self.raw_fullpath = fullpath
            else:
                raise Exception("Error downloading image")

        self.ready_fullpath = get_ready_fullpath(self.raw_file, art_folder_ready, self.resize_option)

        if not os.path.exists(self.ready_fullpath) or always_generate:
            description_box = resize_file_with_matte(self.raw_fullpath, self.ready_fullpath, 3840, 2160, self.resize_option)
        # print(f"Processed {self.url}, metadata is {self.metadata}")
        if (self.metadata is None) or always_metadata:
            await self.get_metadata()

    async def get_metadata(self):
        match image_source(self.url):
            case ImageSources.GOOGLE_ARTSANDCULTURE:
                new_metadata = get_google_metadata(self.url)
                if new_metadata:
                    self.metadata = new_metadata | (self.metadata if self.metadata else {})
            case ImageSources.ARTIC:
                new_metadata = await get_artic_metadata(self.url)
                if new_metadata:
                    self.metadata = new_metadata | (self.metadata if self.metadata else {})
            case ImageSources.HTTP:
                if self.raw_file is not None:
                    new_metadata = get_file_metadata(self.raw_fullpath)
                    if new_metadata:
                        self.metadata = new_metadata | (self.metadata if self.metadata else {})
                else:
                    self.metadata = None
            case _:
                raise Exception("Unknown image source")

    def to_json(self):
        # return a JSON representation of the art file, but only the fields that are needed to recreate the object
        json = {
            "url": self.url,
            "raw_file": self.raw_file,
            "resize_option": self.resize_option,
        }
        if self.metadata:
            json["metadata"] = self.metadata
        return json


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


def debug(tv: SamsungTVAsyncArt):
    # Check if TV is reachable in debug mode
    try:
        logging.info("Checking if the TV can be reached.")
        info = tv.rest_device_info()
        logging.info("If you do not see an error, your TV could be reached.")
        sys.exit()
    except Exception as e:
        logging.error("Could not reach the TV: " + str(e))
        sys.exit()


async def get_available(tv, category=None):
    # Retrieve available art
    available_art = await tv.available(category=category)
    return available_art


async def show_available(tv, category=None):
    available_art = get_available(tv, category)
    logging.info("Available art:")
    for art in available_art:
        logging.info(art)


async def delete_all_uploaded(tv):
    available_art = get_available(tv, UPLOADED_CATEGORY)
    logging.info(f"Deleting {len(available_art)} uploaded images")
    tv.art().delete_list([art["content_id"] for art in available_art])
    logging.info("Deleted all uploaded images")
    # Clear the list of uploaded filenames
    uploaded_files = []
    with open(upload_list_path, "w") as f:
        json.dump(uploaded_files, f)


async def upload_files(
    tv,
    art_files: list[ArtFile],
    always_download: bool = False,
    always_generate: bool = False,
):
    for art_file in art_files:
        if not os.path.exists(art_file.raw_file) or always_download:
            try:
                art_file.download()
            except Exception as e:
                logging.error("There was an error: " + str(e))
                sys.exit()

        if not os.path.exists(art_file.ready_file) or always_generate:
            pass


async def get_uploaded_files(ignore_uploaded: bool = False):
    uploaded_files = []
    # Load the list of uploaded filenames from the file
    if os.path.isfile(upload_list_path) and not ignore_uploaded:
        with open(upload_list_path, "r") as f:
            uploaded_files = json.load(f)

    return uploaded_files


async def save_uploaded_files(uploaded_files):
    with open(upload_list_path, "w") as f:
        json.dump(uploaded_files, f, indent=4)


async def process_set_file(set_file, always_download: bool = False, always_generate: bool = False, always_metadata: bool = False):
    logging.debug(f"Processing set file {set_file}")
    try:
        with open(set_file, "r") as f:
            set_json = json.load(f)
        f.close()
    except Exception as e:
        logging.error(f"Error loading set file: {e}")
        sys.exit()

    set_schema_version = set_json["schema_version"]
    set_name = set_json["name"]
    set_resize = set_json["default_resize"]
    set_art = set_json["art"]

    artset = ArtSet(set_file, set_name, set_resize, set_art)
    artsets.append(artset)

    for art_item in set_art:
        af = ArtFile()
        if "url" in art_item:
            url = art_item["url"]
            # print(f"Processing {url}")
            af.url = art_item["url"]
        if "raw_file" in art_item:
            af.raw_file = art_item["raw_file"]
        if "resize_option" in art_item:
            af.resize_option = art_item["resize_option"]
        else:
            af.resize_option = set_resize
        if "metadata" in art_item:
            af.metadata = art_item["metadata"]

        await af.process(always_download, always_generate, always_metadata)
        artset.add_art(af)
        updated_json = artset.to_json()
        with open(set_file, "w") as o:
            # write the updated JSON in human readable format
            json.dump(updated_json, o, indent=4)

        o.close()


async def upload_one(local_file: str, tv_art: SamsungTVAsyncArt) -> str:
    logging.debug(f"Processing {local_file}")
    if not os.path.exists(local_file):
        logging.error(f"File {local_file} does not exist.")
        raise FileNotFoundError(f"File {local_file} does not exist.")
    remote_file = None
    with open(local_file, "rb") as f:
        data = f.read()
    try:
        if local_file.endswith(".jpg"):
            remote_filename = await tv_art.upload(data, file_type="JPEG", matte="none")
        elif local_file.endswith(".png"):
            remote_filename = await tv_art.upload(data, file_type="PNG", matte="none")
    except Exception as e:
        logging.error("There was an error: " + str(e))
    finally:
        f.close()
    return remote_filename


async def upload_all(tv: SamsungTVAsyncArt, always_upload: bool = False):
    # Build the list of all ready files that need to be uploaded
    files = []
    for artset in artsets:
        for art in artset.get_art():
            files.append(art.ready_fullpath)

    uploaded_files = await get_uploaded_files()

    # Remove the filenames of images that have already been uploaded
    files_to_upload = list(set(files) - set([f["file"] for f in uploaded_files]))

    if not files_to_upload:
        logging.info("No new images to upload.")
        return

    # make a dict of local file : remote filenames from the uploaded_files JSON
    remote_files = {f["file"]: f["remote_filename"] for f in uploaded_files}

    for file_to_upload in files_to_upload:
        remote_filename = None

        # if file is in the list of uploaded files, set the remote filename
        if file_to_upload in remote_files.keys():
            remote_filename = remote_files[file_to_upload]
            logging.info("Image already uploaded.")
        else:
            remote_filename = await upload_one(file_to_upload, tv)
            # Add the filename to the list of uploaded filenames
            uploaded_files.append({"file": file_to_upload, "remote_filename": remote_filename})
            tv.art().select_image(remote_filename, show=True)

        # Save the list of uploaded filenames to the file
        with open(upload_list_path, "w") as f:
            json.dump(uploaded_files, f, indent=4)


async def set_correct_mode(tv_art: SamsungTVAsyncArt, tv_remote: SamsungTVWSAsyncRemote):
    # get current state
    tv_on = await tv_art.on()
    art_mode = True if await tv_art.get_artmode() == "on" else False
    logging.info(f"TV on: {tv_on}, art mode: {art_mode}")
    if art_mode:
        info = await tv_art.get_artmode_settings()
        logging.info("current artmode settings: {}".format(info))

    # if the current time is between 21:00 and 5:00
    if 21 <= time.localtime().tm_hour or time.localtime().tm_hour < 5:
        # if we're in art mode, turn the TV off. Otherwise, do nothing
        if art_mode:
            logging.info("Turning off TV")
            await tv_remote.send_command(SendRemoteKey.hold("KEY_POWER", 3))
        return

    # It is during waking hours. If the TV is off, turn it on and set to art mode
    if not tv_on:
        await tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))


async def image_callback(event, response):
    logging.info("CALLBACK: image callback: {}, {}".format(event, response))


async def main():
    # Increase debug level
    args = parse_args()

    logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)
    logging.info("Starting art.py!")
    logging.debug("Logging in debug mode")

    # Set your TVs local IP address. Highly recommend using a static IP address for your TV.
    if not args.no_tv:
        logging.info(f"Creating TV object for {tv_address}")
        tv_art = SamsungTVAsyncArt(host=tv_address, port=tv_port, token_file="token_file")
        logging.info(f"Starting art listening on {tv_address}:{tv_port}")
        await tv_art.start_listening()
        logging.info(f"Listening on {tv_address} started")

        tv_remote = SamsungTVWSAsyncRemote(host=tv_address, port=tv_port, token_file="token_file")
        logging.debug(f"Connecting to {tv_address}:{tv_port}")
        await tv_remote.start_listening()
        logging.debug("Connected")

        # Checks if the TV supports art mode
        art_mode = await tv_art.supported()
        if not art_mode:
            logging.warning("Your TV does not support art mode.")
            sys.exit()

        logging.info("Art mode supported")
        art_mode_version = await tv_art.get_api_version()

        logging.info(f"TV at {tv_address} supports art mode version {art_mode_version}")

        # example callbacks
        tv_art.set_callback("slideshow_image_changed", image_callback)  # new api
        tv_art.set_callback("auto_rotation_image_changed", image_callback)  # old api
        tv_art.set_callback("image_selected", image_callback)

        if args.debug:
            await debug()

        if args.show_uploaded:
            await show_available(tv_art, UPLOADED_CATEGORY)
            sys.exit()

        if args.delete_all:
            logging.info("Deleting all uploaded images")
    else:
        logging.info("Not connecting to TV")

    if args.setfile:
        await process_set_file(args.setfile, args.always_download, args.always_generate, args.always_metadata)

    if not args.no_tv:
        await upload_all(tv_art)

        await set_correct_mode(tv_art, tv_remote)

        logging.info("Closing connection")
        await tv_art.close()
        await tv_remote.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        os._exit(1)
