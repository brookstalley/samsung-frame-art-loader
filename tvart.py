import argparse
import asyncio
from datetime import datetime
import hashlib
import io
import json
import logging
import os
from PIL import Image
import time

from samsungtvws.async_art import SamsungTVAsyncArt
from samsungtvws import exceptions
from samsungtvws.remote import SendRemoteKey
from samsungtvws.async_remote import SamsungTVWSAsyncRemote

from art import ArtFile, ArtSet
import config
from display import DisplayLabel
from local import SunInfo, perceived_brightness
from image_utils import images_match

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)
# logging.getLogger().setLevel(logging.DEBUG)
artsets = []
uploaded_files = {}
label_display: DisplayLabel = None
last_tv_content_id = None
previous_art_mode = False
previous_auto_start = None

UPLOADED_CATEGORY = "MY-C0002"


def parse_args():
    # Add command line argument parsing
    parser = argparse.ArgumentParser(description="Upload images to Samsung TV.")

    parser.add_argument(
        "--always-download",
        action="store_true",
        help="Always download images from URLs",
    )
    parser.add_argument(
        "--always-generate",
        action="store_true",
        help="Always generate resized images",
    )
    parser.add_argument(
        "--always-labels",
        action="store_true",
        help="Always generate labels",
    )
    parser.add_argument(
        "--always-mat",
        action="store_true",
        help="Always generate new mat colors",
    )
    parser.add_argument(
        "--always-metadata",
        action="store_true",
        help="Always retrieve metadata",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug mode to check if TV is reachable",
    )
    parser.add_argument(
        "--delete-all",
        action="store_true",
        help="Delete all uploaded images",
    )
    parser.add_argument(
        "--ignore-uploaded",
        action="store_true",
        help="Ignore uploaded images and upload all",
    )
    parser.add_argument(
        "--no-tv",
        action="store_true",
        help="Do not connect to TV",
    )
    parser.add_argument(
        "--set-brightness",
        type=str,
        help="Set TV brightness (0-10)",
    )
    parser.add_argument(
        "--setfile",
        nargs="+",
        type=str,
        help="Load art set from file",
    )
    parser.add_argument(
        "--show-uploaded",
        action="store_true",
        help="Show uploaded images from TV",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip uploading images to TV",
    )
    parser.add_argument(
        "--stay",
        action="store_true",
        help="Keep running to update labels and adjust brightness",
    )

    return parser.parse_args()


def update_uploaded_files(local_file, tv_content_id):
    uploaded_files[local_file] = {"tv_content_id": tv_content_id}


async def get_available(tv, category=None):
    # Retrieve available art
    return await tv.available(category=category)


async def show_available(tv, category=None):
    available_art = await get_available(tv, category)
    logging.info("Available art:")
    for art in available_art:
        logging.info(art)


async def delete_all_uploaded(tv_art):
    available_art = await get_available(tv_art, UPLOADED_CATEGORY)
    await tv_art.delete_list([art["content_id"] for art in available_art])
    # clear the tv_content_id from any artfiles that were uploaded
    for art_set in artsets:
        for art_file in art_set.art:
            art_file.tv_content_id = None
    logging.info(f"Deleted {len(available_art)} uploaded images")
    # Clear the list of uploaded filenames
    uploaded_files = {}


async def upload_file(local_file: str, tv_art: SamsungTVAsyncArt) -> str:
    logging.debug(f"Processing {local_file}")
    if not os.path.exists(local_file):
        raise FileNotFoundError(f"File {local_file} does not exist.")
    remote_filename = None
    with open(local_file, "rb") as f:
        data = f.read()
    try:
        if local_file.endswith(".jpg"):
            remote_filename = await tv_art.upload(data, file_type="JPEG", matte="none", portrait_matte="none")
        elif local_file.endswith(".png"):
            remote_filename = await tv_art.upload(data, file_type="PNG", matte="none", portrait_matte="none")
        update_uploaded_files(local_file, remote_filename)
        await tv_art.select_image(remote_filename)
    except Exception as e:
        logging.error("There was an error: " + str(e))
    finally:
        f.close()

    return remote_filename


async def get_thumbnails(tv_art: SamsungTVAsyncArt, content_ids):
    thumbnails = {}
    if content_ids:
        thumbnail_list = await tv_art.get_thumbnail_list(content_ids)
        thumbnails = {os.path.splitext(k)[0]: v for k, v in thumbnail_list.items()}
        for tv_content_id, thumbnail_data in thumbnails.items():
            with open(f"{config.art_folder_tv_thumbs}/{tv_content_id}.jpg", "wb") as f:
                f.write(thumbnail_data)
    logging.info("got {} thumbnails".format(len(thumbnails)))
    return thumbnails


async def get_thumbnail_md5(tv_art: SamsungTVAsyncArt, content_id) -> str:
    logging.info(f"Getting thumbnail for {content_id}")
    try:
        thumbnail_list = await tv_art.get_thumbnail_list([content_id])
        keys = list(thumbnail_list.keys())
        for key in keys:
            new_key = key.rsplit(".", 1)[0]
            thumbnail_list[new_key] = thumbnail_list.pop(key)
        # logging.info(thumbnail_list)
        # thumbnail_data = await tv_art.get_thumbnail(content_id)
        md5 = hashlib.md5(thumbnail_list[content_id]).hexdigest()
    except AssertionError:  # exceptions.ArtError as e:
        logging.error(f"Error getting thumbnail for {content_id}")
        md5 = None
    return md5


async def upload_art_files(tv_art: SamsungTVAsyncArt, art_files: list[ArtFile]):
    for art_file in art_files:
        logging.info(f"Uploading {art_file.ready_fullpath}")
        retry_limit = 3
        retries = 0
        success = False
        while not success and retries < retry_limit:
            try:
                tv_content_id = await upload_file(art_file.ready_fullpath, tv_art)
                update_uploaded_files(art_file.ready_fullpath, tv_content_id)
                art_file.tv_content_id = tv_content_id
                try:
                    md5 = await get_thumbnail_md5(tv_art, tv_content_id)
                    art_file.tv_content_thumb_md5 = md5
                except AssertionError:
                    md5 = None
                    logging.error("No data returned getting thumbnail")

                success = True
            except BrokenPipeError:
                retries += 1
                logging.warning(f"Erorr uploading, now on retry {retries}")
            except Exception as e:
                logging.error(f"Error uploading {art_file.ready_fullpath}: {e}")
                raise e
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
    tv_content_ids = [image["content_id"] for image in tv_images]
    if tv_content_ids:
        tv_thumbnails = await get_thumbnails(tv_art, tv_content_ids)
        logging.info(f"Got thumbnails for {len(tv_thumbnails)}.")
        checked = 0
        matched = 0
        total_art_files = sum([len(art_set.art) for art_set in artsets])
        for art_set in artsets:
            for art_file in art_set.art:
                # Clear the tv_content_id since we're not sure it's real, but leave the MD5 because the thumb should be the same
                art_file.tv_content_id = None
                for i, (tv_content_id, thumbnail_data) in enumerate(tv_thumbnails.items()):
                    tv_thumb_md5 = hashlib.md5(thumbnail_data).hexdigest()
                    if tv_thumb_md5 == art_file.tv_content_thumb_md5:
                        logging.info(f"Found match for {art_file.ready_fullpath} in TV image {tv_content_id}")
                        update_uploaded_files(art_file.ready_fullpath, tv_content_id)
                        art_file.tv_content_id = tv_content_id
                        matched += 1
                checked += 1
        print(f"Checked {checked} / {total_art_files}. Matched: {matched}")

        # Delete images on TV but not in any artset
        tv_ids_in_use = [art_file.tv_content_id for art_set in artsets for art_file in art_set.art if art_file.tv_content_id]
        tv_ids_not_used = [tv_content_id for tv_content_id in tv_thumbnails.keys() if tv_content_id not in tv_ids_in_use]
        logging.info(f"Deleting {len(tv_ids_not_used)} images from TV that are not in an active artset: {tv_ids_not_used}")
        await tv_art.delete_list(tv_ids_not_used)

    # upload art_files that do not have a tv_content_id yet
    art_files_to_upload = [art_file for art_set in artsets for art_file in art_set.art if not art_file.tv_content_id]
    logging.info(f"Uploading {len(art_files_to_upload)} new images to TV")
    await upload_art_files(tv_art, art_files_to_upload)


async def set_brightness_for_local(tv_art: SamsungTVAsyncArt):
    current_dt = datetime.now()  # Use datetime.utcnow() if you need UTC time

    # brightness for time of day, scaled 0.0 - 1.0
    suninfo: SunInfo = perceived_brightness()
    brightness = suninfo.brightness
    # we know we'll never get to relative brightness 1.0. Scale it so 0.8 becomes 1.0
    max_brightness_at_relative_brightness = 0.6
    brightness = min(1.0, brightness * (1 / max_brightness_at_relative_brightness))

    brightness_range = config.max_brightness - config.min_brightness
    cur_brightness = round(brightness * brightness_range) + config.min_brightness
    await tv_art.set_brightness(cur_brightness)
    logging.info(f"Setting brightness to {cur_brightness} (calculated relat {brightness})")


async def set_correct_mode(tv_art: SamsungTVAsyncArt, tv_remote: SamsungTVWSAsyncRemote):
    # get current state
    global previous_art_mode
    global previous_auto_start

    logging.info("setting mode")

    tv_on = await tv_art.on()
    art_mode = True if await tv_art.get_artmode() == "on" else False
    logging.info(f"TV on: {tv_on}, art mode: {art_mode}")

    # if the current time is between 21:00 and 5:00
    # if 21 <= time.localtime().tm_hour or time.localtime().tm_hour < 5:
    #     # if we're in art mode, turn the TV off. Otherwise, do nothing
    #     # if art_mode:
    #     #     logging.info("Turning off TV")
    #     #     await tv_remote.send_command(SendRemoteKey.hold("KEY_POWER", 3))
    #     print(f"Not setting TV mode")
    #     return

    # It is during waking hours. If the TV is off, turn it on.  and set to art mode
    # if previous_auto_start was not today, turn on the TV and set previous_autostart to today
    # if previous_auto_start is today, do nothing
    if previous_auto_start is None or previous_auto_start < datetime.now().date():
        # config.auto_artmode_time_on is in 24 hour time (0530, 1715, etc). See if the current time is past that.
        current_time_24h = datetime.now().strftime("%H%M")
        if current_time_24h >= str(config.auto_artmode_time_on):
            logging.info("Time to wake up and see the art")
            if not tv_on:
                await set_brightness_for_local(tv_art)
                logging.info("Turning TV on")
                await tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))
                await asyncio.sleep(3)
            if not art_mode:
                await tv_art.set_artmode("on")
            await set_brightness_for_local(tv_art)
            previous_auto_start = datetime.now().date()

    # if not tv_on:
    #     logging.info("Turning TV on")
    #     await tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))
    #     await asyncio.sleep(2)
    #     tv_on = True

    # if tv_on and not art_mode:
    #     await tv_art.set_artmode("on")
    #     art_mode = "on"
    #     # logging.info("Clicking power to set art mode")
    #     # await tv_remote.send_command(SendRemoteKey.click("KEY_POWER"))
    #     await asyncio.sleep(1)

    if art_mode and not previous_art_mode:
        # Artmode was switched on since last time we checked
        info = await tv_art.get_artmode_settings()
        logging.info("current artmode settings: {}".format(info))
        # Get the relative brightness based on current time, day of year, latitude, and longitude
        # Get current datetime
        slideshow_duration = 3
        slideshow_shuffle = True
        logging.info(f"Setting slideshow to {slideshow_duration} minutes, shuffle: {slideshow_shuffle}")
        try:
            data = await tv_art.set_slideshow_status(duration=3, type=True, category=2)
        except AssertionError:
            logging.error("No data returned setting slideshow status")

    if art_mode:
        await set_brightness_for_local(tv_art)

    previous_art_mode = art_mode


async def set_brightness(tv_art: SamsungTVAsyncArt, brightness: str):
    logging.info(f"Setting brightness to {brightness}")
    data = await tv_art.set_brightness(brightness)
    logging.info(f"Got data: {data}")


async def image_callback(event, response):
    global label_display, last_tv_content_id

    logging.debug("CALLBACK: image callback: {}, {}".format(event, response))
    data_str = response["data"]
    data = json.loads(data_str)
    event = data.get("event", None)
    tv_content_id = data.get("content_id", None)
    is_shown = data.get("is_shown", None)
    displayed_artfile = None
    if label_display is None:
        logging.error("Label display is None")
        return

    if event == "image_selected" and is_shown == "Yes" and tv_content_id != last_tv_content_id:
        last_tv_content_id = tv_content_id
        # find the artfile with the matching tv_content_id
        for art_set in artsets:
            for art_file in art_set.art:
                if art_file.tv_content_id == tv_content_id:
                    displayed_artfile = art_file
                    break
        if not displayed_artfile:
            logging.error(f"Could not find artfile with tv_content_id {tv_content_id}")
            return
        # logging.info(f"Displayed artfile: {displayed_artfile.ready_fullpath}\n{displayed_artfile.metadata}")
        if config.use_art_label:
            if displayed_artfile.label_file:
                fullpath = os.path.join(config.art_folder_label, displayed_artfile.label_file)
                if os.path.exists(fullpath):
                    label_image = Image.open(fullpath)
                    label_display.display_image(label_image)
                else:
                    logging.error(f"Label file {fullpath} does not exist.")
            else:
                logging.info(f'No label file for {displayed_artfile.metadata.get("title", "Unknown")}')


async def ensure_folders_exist():
    # Ensure that the folders exist
    if not os.path.exists(config.base_folder):
        raise FileNotFoundError(f"Base folder {config.base_folder} does not exist.")

    for folder in [
        config.art_folder_raw,
        config.art_folder_ready,
        config.dezoomify_tile_cache,
        config.art_folder_tv_thumbs,
        config.art_folder_label,
        config.art_folder_temp,
        config.cache_folder,
    ]:
        if not os.path.exists(folder):
            logging.info(f'Creating folder "{folder}"')
            os.makedirs(folder)


async def main():
    global label_display

    args = parse_args()

    logging.info("Starting art.py!")
    logging.debug("Logging in debug mode")
    try:
        await ensure_folders_exist()
    except FileNotFoundError as e:
        logging.error(f"Base folder {config.base_folder} does not exist.")
        return

    if args.setfile:
        for setfile in args.setfile:
            if not os.path.exists(setfile):
                logging.error(f"Set file {setfile} does not exist.")
                return

            loaded_set = ArtSet.from_file(setfile)
            download_success = await loaded_set.process(
                args.always_download, args.always_generate, args.always_metadata, args.always_labels, args.always_mat
            )
            if not download_success:
                logging.error(f"Could not download all files in set {args.setfile}")
                return
            artsets.append(loaded_set)

    if args.no_tv:
        logging.info(f"Not connecting to TV, exiting")
        return

    logging.info(f"Creating TV object for {config.tv_address}")

    tv_art = SamsungTVAsyncArt(host=config.tv_address, port=config.tv_port, name="tvpi", token_file="token_file")
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
        await tv_remote.close()
        await tv_art.close()
        return

    logging.info("Art mode supported")
    art_mode_version = await tv_art.get_api_version()

    logging.info(f"TV at {config.tv_address} supports art mode version {art_mode_version}")

    if args.set_brightness:
        brightness = args.set_brightness
        await set_brightness(tv_art, args.set_brightness)
        await tv_remote.close()
        await tv_art.close()
        return

    # example callbacks
    tv_art.set_callback("slideshow_image_changed", image_callback)  # new api
    tv_art.set_callback("auto_rotation_image_changed", image_callback)  # old api
    tv_art.set_callback("image_selected", image_callback)

    # if args.debug:
    #     logging.getLogger().setLevel(logging.DEBUG)

    if args.show_uploaded:
        await show_available(tv_art, UPLOADED_CATEGORY)
        return

    if args.delete_all:
        logging.info("Deleting all uploaded images")
        await delete_all_uploaded(tv_art)
        for art_set in artsets:
            # write the updated tv ID's
            logging.info(f"...saving {art_set.name}")
            art_set.save()

    if len(artsets) > 0:
        if args.skip_sync:
            logging.info("Skipping upload to TV")
        else:
            await sync_artsets_to_tv(tv_art)
            for art_set in artsets:
                # write the updated tv ID's
                art_set.save()

    if args.stay:
        logging.info(f"Staying alive. Ctrl-c to exit")
        label_display = DisplayLabel()
        exit_requested = False
        while not exit_requested:
            logging.info("loop")
            try:
                await set_correct_mode(tv_art, tv_remote)
                # wait one second at a time, 120 times
                for i in range(0, 120):
                    await asyncio.sleep(1)
            except KeyboardInterrupt:
                logging.info("Exiting...")
                exit_requested = True
                continue
        label_display.close()
    else:
        await set_correct_mode(tv_art, tv_remote)  # just do it once

    logging.info("Closing connection")
    await tv_art.close()
    await tv_remote.close()
    return


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        os._exit(1)
