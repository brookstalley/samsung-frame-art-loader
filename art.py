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
from image_utils import resize_file_with_matte, image_source, get_image, get_image_dimensions
from metadata import get_google_metadata, get_file_metadata, get_artic_metadata

import config

sys.path.append("../")

from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws import exceptions
from samsungtvws.remote import SendRemoteKey
from samsungtvws.async_remote import SamsungTVWSAsyncRemote


artsets = []

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
    parser.add_argument("--stay", action="store_true", help="Keep running")

    return parser.parse_args()


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


class DownloadError(Exception):
    """Exception raised for errors in the download process."""

    def __init__(self, url, message="Failed to download the file"):
        self.url = url
        self.message = message
        super().__init__(f"{message}: {url}")


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
        raw_file_width=None,
        raw_file_height=None,
        ready_file=None,
        resize_option=None,
        metadata=None,
    ):
        self.url = url
        self.raw_file = raw_file
        self.ready_file = ready_file
        self.resize_option = resize_option
        self.metadata = metadata
        self.raw_file_width = raw_file_width
        self.raw_file_height = raw_file_height

    def to_dict(self):
        # return a JSON representation of the art file, but only the fields that are needed to recreate the object
        me = {"url": self.url}
        if self.raw_file is not None:
            me["raw_file"] = self.raw_file
        if self.ready_file is not None:
            me["ready_file"] = self.ready_file
        if self.raw_file_width is not None:
            me["raw_file_width"] = self.raw_file_width
        if self.raw_file_height is not None:
            me["raw_file_height"] = self.raw_file_height
        if self.resize_option is not None:
            me["resize_option"] = self.resize_option
        if self.metadata is not None:
            me["metadata"] = self.metadata
        return me

    @classmethod
    def from_dict(cls, data: dict, default_resize: str):
        url = data.get("url")
        raw_file = data.get("raw_file", None)
        ready_file = data.get("ready_file", None)
        raw_file_width = data.get("raw_file_width", None)
        raw_file_height = data.get("raw_file_height", None)
        resize_option = data.get("resize_option", default_resize)
        metadata = data.get("metadata", None)
        return cls(
            url=url,
            raw_file=raw_file,
            ready_file=ready_file,
            raw_file_width=raw_file_width,
            raw_file_height=raw_file_height,
            resize_option=resize_option,
            metadata=metadata,
        )

    async def process(self, always_download=False, always_generate=False, always_metadata=False):
        """Process the art file. Download the raw file if necessary, and generate the ready file."""
        """ TODO: Support files that are already downloaded and have no URL """
        raw_file_exists = False
        ready_file_exists = False
        if not self.url:
            raise Exception("URL is required")

        logging.info(f"Processing {self.url}")

        # URL is specified
        raw_file_exists = False
        if self.raw_file:
            self.raw_fullpath = config.art_folder_raw + "/" + self.raw_file
            # If the file is zero bytes, delete it and download again
            if os.path.exists(self.raw_fullpath) and os.path.getsize(self.raw_fullpath) == 0:
                os.remove(self.raw_fullpath)
            if os.path.exists(self.raw_fullpath) and not always_download:
                raw_file_exists = True
        if not raw_file_exists:
            # Raw file is not specified or does not exist. For now always download because we can't get the filename from the URL
            result, fullpath = await get_image(self.url, destination_fullpath=None, destination_dir=config.art_folder_raw)
            if result:
                raw_file_exists = True
                # Only save the basename so the program is portable
                self.raw_file = os.path.basename(fullpath)
                self.raw_fullpath = fullpath
            else:
                raise DownloadError(self.url)

        if self.raw_file_width is None or self.raw_file_height is None:
            self.raw_file_width, self.raw_file_height = get_image_dimensions(self.raw_fullpath)
            logging.debug(f"Got dimensions {self.raw_file_width}x{self.raw_file_height} for {self.raw_fullpath}")
        else:
            logging.debug(f"Using dimensions {self.raw_file_width}x{self.raw_file_height} for {self.raw_fullpath}")

        self.ready_fullpath = get_ready_fullpath(self.raw_file, config.art_folder_ready, self.resize_option)

        if not os.path.exists(self.ready_fullpath) or always_generate:
            logging.info(f"Generating ready file at {self.ready_fullpath}")
            description_box = resize_file_with_matte(self.raw_fullpath, self.ready_fullpath, 3840, 2160, self.resize_option)

        self.ready_file = os.path.basename(self.ready_fullpath)

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


class ArtSet:
    name: str = None
    default_resize: str = None
    art: list[ArtFile] = []
    source_file: str = None

    def __init__(self, source_file=None, name=None, default_resize=None, art: list[ArtFile] = []):
        self.name = name
        self.default_resize = default_resize
        self.art = art
        self.source_file = source_file

    def to_dict(self):
        return {
            "name": self.name,
            "default_resize": self.default_resize,
            "art": [art_file.to_dict() for art_file in self.art],
        }

    @classmethod
    def from_dict(cls, data: dict):
        name = data.get("name", None)
        default_resize = data.get("default_resize", None)
        source_file = data.get("source_file", None)
        art_json = data.get("art", None)
        art: list[ArtFile] = []
        if art_json:
            art_list = data.pop("art")
            art = [ArtFile.from_dict(art_file, default_resize) for art_file in art_list]
        return cls(name=name, default_resize=default_resize, source_file=source_file, art=art)

    @classmethod
    def from_file(cls, source_file: str):
        logging.info(f"Loading art set from {source_file}")
        try:
            with open(source_file, "r") as file:
                data = json.load(file)
        except FileNotFoundError:
            logging.error(f"File {source_file} not found")
            raise e
        except Exception as e:
            logging.error(f"Error loading file {source_file}: {e}")
            raise e
        data["source_file"] = source_file
        return cls.from_dict(data)

    def save(self):
        """Save the art set to a JSON file."""
        logging.debug(f'Saving art set "{self.name}" to {self.source_file}')
        with open(self.source_file, "w") as file:
            json.dump(self.to_dict(), file, indent=4)

    async def process(self, always_download: bool = False, always_generate: bool = False, always_metadata: bool = False) -> bool:
        logging.info(f"Processing set file {self.name}")
        print(f"ArtSet: {self.name}, {self.default_resize} has {len(self.art)} items")
        errors_downloading = False
        for art_file in self.art:
            try:
                await art_file.process(always_download, always_generate, always_metadata)
            except DownloadError as e:
                logging.info(f"Error downloading file: {e}")
                errors_downloading = True
                continue
            except Exception as e:
                logging.error(f"Error processing file: {e}")
                raise e

            self.save()
        return not errors_downloading  # yes this is weird #TODO: fix


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
    available_art = await get_available(tv, category)
    logging.info("Available art:")
    for art in available_art:
        logging.info(art)


async def delete_all_uploaded(tv_art):
    available_art = await get_available(tv_art, UPLOADED_CATEGORY)
    logging.info(f"Deleting {len(available_art)} uploaded images")
    await tv_art.delete_list([art["content_id"] for art in available_art])
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
            remote_filename = await tv_art.upload(data, file_type="JPEG", matte="none", portrait_matte="none")
        elif local_file.endswith(".png"):
            remote_filename = await tv_art.upload(data, file_type="PNG", matte="none", portrait_matte="none")
    except Exception as e:
        logging.error("There was an error: " + str(e))
    finally:
        f.close()
    return remote_filename


async def upload_all(tv_art: SamsungTVAsyncArt, always_upload: bool = False):
    # Build the list of all ready files that need to be uploaded

    files = []

    for artset in artsets:
        for art_file in artset.art:
            files.append(art_file.ready_fullpath)

    logging.info(f"{len(files)} files are candidates to upload")

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
            remote_filename = await upload_one(file_to_upload, tv_art)
            # Add the filename to the list of uploaded filenames
            uploaded_files.append({"file": file_to_upload, "remote_filename": remote_filename})
            try:
                await tv_art.select_image(remote_filename, show=True)
            except SamsungTVAsyncArt.samsungtvws.exceptions.ResponseError as e:
                # fine to swallow this one
                logging.error(f"Could not select image {remote_filename}: {e}")
            except Exception as e:
                raise e

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
        logging.info("Turning TV on")
        await tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))
        await asyncio.sleep(3)
        tv_on = True

    if tv_on and not art_mode:
        logging.info("Clicking power to set art mode")
        await tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))
        await asyncio.sleep


async def image_callback(event, response):
    logging.info("CALLBACK: image callback: {}, {}".format(event, response))


async def ensure_folders_exist():
    # Ensure that the folders exist
    if not os.path.exists(config.base_folder):
        raise FileNotFoundError(f"Base folder {config.base_folder} does not exist.")

    for folder in [config.art_folder_raw, config.art_folder_ready, config.dezoomify_tile_cache]:
        if not os.path.exists(folder):
            logging.info(f'Creating folder "{folder}"')
            os.makedirs(folder)


async def main():
    # Increase debug level
    args = parse_args()

    logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)
    # logging.getLogger().setLevel(logging.DEBUG)

    logging.info("Starting art.py!")
    logging.debug("Logging in debug mode")
    try:
        await ensure_folders_exist()
    except FileNotFoundError as e:
        logging.error(f"Base folder {config.base_folder} does not exist.")
        return

    if args.setfile:
        loaded_set = ArtSet.from_file(args.setfile)
        download_success = await loaded_set.process(args.always_download, args.always_generate, args.always_metadata)
        if not download_success:
            logging.error(f"Could not download all files in set {args.setfile}")
            return
        artsets.append(loaded_set)

    if args.no_tv:
        logging.info(f"Not connecting to TV, exiting")
        return

    logging.info(f"Creating TV object for {config.tv_address}")
    tv_art = SamsungTVAsyncArt(host=config.tv_address, port=config.tv_port, token_file="token_file")
    logging.info(f"Starting art listening on {config.tv_address}:{config.tv_port}")
    await tv_art.start_listening()
    logging.info(f"Listening on {config.tv_address} started")

    tv_remote = SamsungTVWSAsyncRemote(host=config.tv_address, port=config.tv_port, token_file="token_file")
    logging.debug(f"Connecting to {config.tv_address}:{config.tv_port}")
    await tv_remote.start_listening()
    logging.debug("Connected")

    # Checks if the TV supports art mode
    art_mode = await tv_art.supported()
    if not art_mode:
        logging.warning("Your TV does not support art mode.")
        return

    logging.info("Art mode supported")
    art_mode_version = await tv_art.get_api_version()

    logging.info(f"TV at {config.tv_address} supports art mode version {art_mode_version}")

    # example callbacks
    tv_art.set_callback("slideshow_image_changed", image_callback)  # new api
    tv_art.set_callback("auto_rotation_image_changed", image_callback)  # old api
    tv_art.set_callback("image_selected", image_callback)

    if args.debug:
        await debug()

    if args.show_uploaded:
        await show_available(tv_art, UPLOADED_CATEGORY)
        return

    if args.delete_all:
        logging.info("Deleting all uploaded images")
        await delete_all_uploaded(tv_art)

    if len(artsets) > 0:
        await upload_all(tv_art)

    await set_correct_mode(tv_art, tv_remote)
    if args.stay:
        logging.info(f"Staying alive. Ctrl-c to exit")
        exit_requested = False
        while not exit_requested:
            try:
                await set_correct_mode(tv_art, tv_remote)
                # wait one second at a time, 60 times
                for i in range(0, 59):
                    await asyncio.sleep(60)
            except KeyboardInterrupt:
                logging.info("Exiting...")
                exit_requested = True
                continue

    logging.info("Closing connection")
    await tv_art.close()
    await tv_remote.close()
    return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        os._exit(1)
