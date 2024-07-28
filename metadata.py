import logging
import requests
import re


# from libxmp import XMPFiles, consts, XMPMeta
# from libxmp.utils import file_to_dict
from PIL import Image, ExifTags
from source_utils import artic_metadata_for_artwork_url, artic_json_for_api_url, google_metadata_for_artwork_url

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)

metadata_map = {
    "artist": ["creator", "artist", "created by", "by", "artist_title"],
    "date_created": ["date created", "date", "date_display"],
    "title": ["title", "name"],
    "medium": ["medium", "media", "medium_display"],
    "artist_nationality": ["creator nationality", "artist_nationality", "creator_nationality"],
    "dimensions": ["dimensions", "size", "physical dimensions"],
    "creator_lived": ["creator_lived", "creator lifespan", "artist_lifespan"],
    "creator_born": ["creator_born", "birth_year", "birth_date"],
    "creator_died": ["creator_died", "death_year", "death_date"],
    "rights": ["rights", "usage rights", "dc:rights", "dc:rights[1]"],
    "description": ["description", "caption", "dc:description"],
    "artist_details": ["artist details", "artist_display"],
}


# Function to normalize keys based on the synonyms map
def normalize_key(key, synonyms_map):
    for desired_key, synonyms in synonyms_map.items():
        if key.lower() in [syn.lower() for syn in synonyms]:
            return desired_key
    return None  # Return None if the key is not in the synonyms map


# Process input dict, mapping to normalized keys
def process_key_value_pairs(input_dict, synonyms_map):
    result = {}
    for key, value in input_dict.items():
        normalized_key = normalize_key(key, synonyms_map)
        if normalized_key:
            result[normalized_key] = f"{value}"
    return result


async def parse_artic_details(artist_details: str):
    artist_nationality = None
    birth_year = None
    death_year = None

    # logging.info(f"Got {artist_details}")
    # Patterns for extracting birth and death years
    birth_pattern = re.compile(r"(\b(?:b\.|born)\s*(\d{4}))|(\b(\d{4})\b)(?=\s*-\s*\d{4})")
    death_pattern = re.compile(r"(\b(?:d\.|died)\s*(\d{4}))|(?<=\s-\s)(\d{4})")

    # Pattern for extracting nationality
    nationality_pattern = re.compile(r"^([A-Za-z\s\(\),]+?)(?=,\s\d|$)")

    # Search for nationality
    nationality_match = nationality_pattern.search(artist_details)
    if nationality_match:
        artist_nationality = nationality_match[0]
        # logging.info(f"Got naionality: {artist_nationality}")

    # Search for birth year
    birth_match = birth_pattern.search(artist_details)
    if birth_match:
        birth_year = birth_match.group(2) or birth_match.group(4)

    # Search for death year
    death_match = death_pattern.search(artist_details)
    if death_match:
        death_year = death_match.group(2) or death_match.group(3)

    # Convert years to integers if found
    if birth_year:
        birth_year = int(birth_year)
    if death_year:
        death_year = int(death_year)

    return artist_nationality, birth_year, death_year


async def get_artic_metadata(url: str):
    artwork_api_response = await artic_metadata_for_artwork_url(url)
    artwork_metadata = artwork_api_response["data"]
    thumbail_data = artwork_metadata.pop("thumbnail")
    # print(f"Raw artic metadata: {metadata}")
    # artic likes to put the arist name, nationality, and birth/death in the artist_details field, separated by newlines.
    # break them out if it's written that way
    artist_details = artwork_metadata.get("artist_display", "")
    # split artist details at \n
    artist_details = artist_details.split("\n")
    if len(artist_details) > 1:
        artist_info = artist_details[1]
        nationality, birth_year, death_year = await parse_artic_details(artist_info)
        if nationality:
            # print(f"****  setting nationality to: {nationality}")
            artwork_metadata["artist_nationality"] = nationality

        if birth_year:
            artwork_metadata["creator_born"] = birth_year
        if death_year:
            artwork_metadata["creator_died"] = death_year

    # print(f"Artwork metadata: {artwork_metadata}")

    filtered_artwork_metadata = process_key_value_pairs(artwork_metadata, metadata_map)
    print(f"filtered artwork: {filtered_artwork_metadata}")

    artist_id = artwork_metadata.pop("artist_ids")[0]
    artist_api = f"https://api.artic.edu/api/v1/artists/{artist_id}"
    artist_api_response = await artic_json_for_api_url(artist_api)
    artist_metadata = artist_api_response["data"]
    # print(f"Got artist metadata for {artist_api}: {artist_metadata}")
    # the artist response will have the artist name in the title field, move it to artist
    artist_metadata["artist"] = artist_metadata.pop("title")
    artist_metadata["artist_description"] = artist_metadata.pop("description")
    filtered_artist_metadata = process_key_value_pairs(artist_metadata, metadata_map)
    cleaned_metadata = {**filtered_artwork_metadata, **filtered_artist_metadata}

    print(f"Got metadata for {url}: {cleaned_metadata}")
    return cleaned_metadata


# def get_xmp_metadata(image_path):
#     # Open the file and get the XMP data
#     xmp_dict = file_to_dict(image_path)
#     try:
#         dublin_core = xmp_dict[consts.XMP_NS_DC]
#         # print(f"{image_path} Dublin Core: {dublin_core}")
#         metadata = {}
#         for item in dublin_core:
#             tag = item[0]
#             value = item[1]
#             attributes = item[2]
#             metadata[tag] = value
#         print(f"Got XMP Dublin core for {image_path}: {metadata}")
#         return metadata
#     except KeyError:
#         print(f"{image_path} has no Dublin Core metadata")
#         return None


def get_exif_metadata(file_path: str):
    try:
        image = Image.open(file_path)
        exif = {ExifTags.TAGS[k]: v for k, v in image._getexif().items() if k in ExifTags.TAGS}
        print(f"Got EXIF metadata for {file_path}: {exif}")
    except Exception as e:
        print(f"Error getting EXIF metadata: {e}")
    return {}


def get_file_metadata(file_path: str):
    metadata = {}

    # xmp_data = get_xmp_metadata(file_path)
    # if xmp_data is not None:
    #    cleaned_metadata = process_key_value_pairs(xmp_data, metadata_map)
    #    metadata = metadata | cleaned_metadata

    exif_data = get_exif_metadata(file_path)

    return metadata


async def google_get_metadata(url: str):
    raw_metadata = await google_metadata_for_artwork_url(url)

    cleaned_metadata = process_key_value_pairs(raw_metadata, metadata_map)
    # print(cleaned_metadata)
    return cleaned_metadata
