import os
import logging

import config
import json

from image_utils import ResizeOptions, ImageSources
from image_utils import resize_file_with_matte, image_source, get_image, get_image_dimensions
from metadata import get_google_metadata, get_file_metadata, get_artic_metadata

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


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
        self.url: str = url
        self.raw_file: str = raw_file
        self.ready_file: str = ready_file
        self.resize_option = resize_option
        self.metadata = metadata
        self.raw_file_width: int = raw_file_width
        self.raw_file_height: int = raw_file_height
        self.tv_content_id: str = None

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

    def get_ready_fullpath(self):
        # Get the filename of the ready file
        ready_fullpath = os.path.join(
            config.art_folder_ready,
            os.path.splitext(os.path.basename(self.raw_file))[0] + "_" + self.resize_option + ".jpg",
        )
        return ready_fullpath

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

        self.ready_fullpath = self.get_ready_fullpath()

        if not os.path.exists(self.ready_fullpath) or always_generate:
            logging.debug(f"Generating ready file at {self.ready_fullpath}")
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
