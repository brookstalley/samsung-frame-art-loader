import requests
import re
from bs4 import BeautifulSoup

metadata_map = {
    "creator": ["creator", "artist", "created by", "by"],
    "date_created": ["date created", "date"],
    "title": ["title", "name"],
    "medium": ["medium"],
    "creator_nationality": ["creator nationality"],
    # Add other desired keys and their synonyms here
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
                    print(f"{key}: {value}")
    print(raw_metadata)
    cleaned_metadata = process_key_value_pairs(raw_metadata, metadata_map)
    print(cleaned_metadata)
    return cleaned_metadata
