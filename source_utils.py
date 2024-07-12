import requests
import re
import logging

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.DEBUG)


async def get_artic_api_for_url(url: str) -> str:
    # extract the artwork ID. https://www.artic.edu/artworks/100472/untitled-purple-white-and-red becomes 100472
    # be durable in case the URL format changes. Just get the number.
    artwork_id = re.search(r"\d+", url).group()
    api_url = f"https://api.artic.edu/api/v1/artworks/{artwork_id}"
    return api_url


async def artic_metadata_for_url(url: str) -> dict:
    api_url = await get_artic_api_for_url(url)
    try:
        # load json from the API url
        response = requests.get(api_url)
        response.raise_for_status()
        artwork_json = response.json()
        return artwork_json
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return None
    except Exception as e:
        logging.error(f"Error downloading {url}: {e}")
        return None
