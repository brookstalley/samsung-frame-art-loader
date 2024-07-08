import requests
import re
from bs4 import BeautifulSoup


def get_google_metadata(url: str):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/100.0.4896.60 Safari/537.36",
    }

    params = {}
    html = requests.get(url, params=params, headers=headers, timeout=30)
    soup = BeautifulSoup(html.text, "lxml")
    divs = soup.find_all("div", id=lambda x: x and x.startswith("metadata-"))
    for div in divs:
        ul = div.find_all("ul")
        if ul:
            lis = ul.find_all("li")
            for li in lis:
                span = li.find("span")
                if span:
                    key = span.text
                    value = li.text
                    print(key, value)
