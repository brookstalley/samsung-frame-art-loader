import requests
import re
from bs4 import BeautifulSoup

# from libxmp import XMPFiles, consts, XMPMeta
# from libxmp.utils import file_to_dict
from PIL import Image, ExifTags
from source_utils import artic_metadata_for_url

metadata_map = {
    "creator": ["creator", "artist", "created by", "by"],
    "date_created": ["date created", "date", "date_display"],
    "title": ["title", "name"],
    "medium": ["medium", "media", "medium_display"],
    "creator_nationality": ["creator nationality"],
    "dimensions": ["dimensions", "size", "physical dimensions"],
    "creator_lived": ["creator lifespan"],
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
            result[normalized_key] = value
    return result


def get_google_metadata(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    }

    params = {}
    html = requests.get(url, params=params, headers=headers, timeout=30)
    soup = BeautifulSoup(html.text, "lxml")
    divs = soup.find_all("div", id=lambda x: x and x.startswith("metadata-"))

    raw_metadata = {}
    for div in divs:
        ul = div.find("ul")
        if ul:
            lis = ul.find_all("li")
            for li in lis:
                span = li.find("span")
                if span:
                    key = span.text.replace(":", "").strip().lower()
                    value = li.text.replace(span.text, "").strip()
                    raw_metadata[key] = value
    cleaned_metadata = process_key_value_pairs(raw_metadata, metadata_map)
    # print(cleaned_metadata)
    return cleaned_metadata


async def get_artic_metadata(url: str):
    api_response = await artic_metadata_for_url(url)
    metadata = api_response["data"]
    thumbail_data = metadata.pop("thumbnail")
    cleaned_metadata = process_key_value_pairs(metadata, metadata_map)
    # print(f"Got metadata for {url}: {cleaned_metadata}")
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
