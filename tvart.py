import asyncio
import sys
import logging
import os
import io
import argparse

import time
from PIL import Image
from art import ArtFile, ArtSet
from image_utils import images_match

import config

sys.path.append("../")

from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws import exceptions
from samsungtvws.remote import SendRemoteKey
from samsungtvws.async_remote import SamsungTVWSAsyncRemote


artsets = []
uploaded_files = {}

UPLOADED_CATEGORY = "MY-C0002"


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


def update_uploaded_files(local_file, tv_content_id):
    uploaded_files[local_file] = {"tv_content_id": tv_content_id}


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
    await tv_art.delete_list([art["content_id"] for art in available_art])
    logging.info(f"Deleted {len(available_art)} uploaded images")
    # Clear the list of uploaded filenames
    uploaded_files = {}


async def upload_file(local_file: str, tv_art: SamsungTVAsyncArt) -> str:
    logging.debug(f"Processing {local_file}")
    if not os.path.exists(local_file):
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
    update_uploaded_files(local_file, remote_filename)
    return remote_filename


async def get_thumbnails(tv_art: SamsungTVAsyncArt, content_ids):
    thumbnails = {}
    if content_ids:
        thumbnails = {os.path.splitext(k)[0]: v for k, v in (await tv_art.get_thumbnail_list(content_ids)).items()}
    logging.info("got {} thumbnails".format(len(thumbnails)))
    return thumbnails


async def upload_art_files(tv_art: SamsungTVAsyncArt, art_files: list[ArtFile]):
    for art_file in art_files:
        logging.info(f"Uploading {art_file.ready_fullpath}")
        try:
            tv_content_id = await upload_file(art_file.ready_fullpath, tv_art)
            update_uploaded_files(art_file.ready_fullpath, tv_content_id)
            art_file.tv_content_id = tv_content_id
        except Exception as e:
            logging.error(f"Error uploading {art_file.ready_fullpath}: {e}")
    return


async def sync_artsets_to_tv(tv_art: SamsungTVAsyncArt):
    """
    Syncs the images in our global artsets list to the TV.

    :param tv_art: An instance of SamsungTVAsyncArt representing the TV's art functionality.
    :type tv_art: SamsungTVAsyncArt

    :param always_upload: A flag indicating whether to always clear the TV and upload from scratch. Defaults false.
    :type always_upload: bool, optional

    :return: None
    :rtype: None

    This function synchronizes the images in the global artsets list to the TV. It uses the provided `tv_art` instance
    to interact with the TV's art functionality. By default, it only uploads images that do not already exist on the TV,
    but if the `always_upload` flag is set to True, it will delete all user files on the TV and upload everything.
    """
    tv_images = await get_available(tv_art, UPLOADED_CATEGORY)
    if tv_images:
        tv_thumbnails = await get_thumbnails(tv_images)
        logging.info(f"Got thumbnails for {len(tv_thumbnails)}.")
        checked = 0
        matched = 0
        total_art_files = sum([len(art_set.art) for art_set in artsets])
        for art_set in artsets:
            for art_file in art_set.art:
                art_image = Image.open(art_file.ready_fullpath)
                for i, (tv_content_id, thumbnail_data) in enumerate(tv_thumbnails.items()):
                    thumbnail_image = Image.open(io.BytesIO(thumbnail_data))
                    if images_match(art_image, thumbnail_image):
                        logging.info(f"Found match for {art_file.ready_fullpath} in TV images")
                        update_uploaded_files(art_file.ready_fullpath, tv_content_id)
                        art_file.tv_content_id = tv_content_id
                        matched += 1
                    checked += 1
                    print(f"Checked {checked} / {total_art_files}. Matched: {matched}")

        # Delete images on TV but not in any artset
        tv_ids_in_use = [art_file.tv_content_id for art_set in artsets for art_file in art_set.art if art_file.tv_content_id]
        tv_ids_not_used = [tv_content_id for tv_content_id in tv_thumbnails.keys() if tv_content_id not in tv_ids_in_use]
        logging.info(f"Deleting {len(tv_ids_not_used)} unused images from TV")
        await tv_art.delete_list(tv_ids_not_used)

        # upload art_files that do not have a tv_content_id yet
        art_files_to_upload = [art_file for art_set in artsets for art_file in art_set.art if not art_file.tv_content_id]
        logging.info(f"Uploading {len(art_files_to_upload)} new images to TV")
        await upload_art_files(tv_art, art_files_to_upload)


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
    tv_content_id = response["contentId"]


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
        await sync_artsets_to_tv(tv_art)

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
