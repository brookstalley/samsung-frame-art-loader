import requests
import re
import logging
import config
import hashlib
import os
import json
from bs4 import BeautifulSoup


logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)


async def get_artic_api_for_artwork_url(url: str) -> str:
    # extract the artwork ID. https://www.artic.edu/artworks/100472/untitled-purple-white-and-red becomes 100472
    # be durable in case the URL format changes. Just get the number.
    artwork_id = re.search(r"\d+", url).group()
    api_url = f"https://api.artic.edu/api/v1/artworks/{artwork_id}"
    return api_url


async def cache_filename_for_url(url: str) -> str:
    # generate a cache using a hash value because urls could be anything
    # and we can't have special characters in filenames
    # create the full path for the filename in a way that will work on windows and unix
    if not os.path.exists(config.cache_folder):
        os.makedirs(config.cache_folder)
    cache_fullpath = os.path.join(config.cache_folder, f"{hashlib.md5(url.encode()).hexdigest()}.json")

    return cache_fullpath


async def cache_get_json_for_url(url: str):
    cache_filename = await cache_filename_for_url(url)
    if os.path.exists(cache_filename):
        logging.debug(f"Cache hit for {url}")
        with open(cache_filename, "r") as f:
            return json.load(f)
    return None


async def cache_write_json_for_url(url: str, json_data: dict):
    cache_filename = await cache_filename_for_url(url)
    with open(cache_filename, "w") as f:
        json.dump(json_data, f, indent=4)
    return


async def artic_json_for_api_url(url: str, cache: bool = True):
    # check the cache first
    if cache:
        cached_json = await cache_get_json_for_url(url)
        if cached_json is not None:
            logging.debug(f"Cache hit for {url}")
            return cached_json

    try:
        # load json from the API url
        response = requests.get(url)
        response.raise_for_status()
        api_json = response.json()
        if cache:
            await cache_write_json_for_url(url, api_json)

        return api_json
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error downloading {url}: {e}")
        return None


async def artic_metadata_for_artwork_url(url: str) -> dict:
    api_url = await get_artic_api_for_artwork_url(url)
    return await artic_json_for_api_url(api_url)


async def google_metadata_for_artwork_url(url: str, cache: bool = True):
    if cache:
        cached_json = await cache_get_json_for_url(url)
        if cached_json is not None:
            logging.debug(f"Cache hit for {url}")
            return cached_json

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
    print(f"Raw google metadata: {raw_metadata}")
    if cache:
        await cache_write_json_for_url(url, raw_metadata)

    return raw_metadata
