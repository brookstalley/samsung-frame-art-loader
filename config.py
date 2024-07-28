from dotenv import load_dotenv
import os

# load environment from .env
# override enabled so we don't use cached values that pipenv loaded
load_dotenv(override=True)

OPENAI_KEY = os.environ.get("OPENAI_KEY", default=None)
EPD_TYPE = os.environ.get("EPD_TYPE", default=None)

# Set the path to the folder containing the images
# base_folder = "/home/brooks/art"
# base_folder = "/Users/brookstalley/art"
base_folder = "/home/tvpi/art"
art_folder_raw = f"{base_folder}/raw"
art_folder_ready = f"{base_folder}/ready"
art_folder_tv_thumbs = f"{base_folder}/tv-thumbs"
art_folder_label = f"{base_folder}/label"
art_folder_temp = f"{base_folder}/temp"

cache_folder = f"{base_folder}/api-cache"

label_width = 648
label_height = 480

dezoomify_tile_cache = f"{base_folder}/tile-cache"

# Set the path to the file that will store the list of uploaded filenames
upload_list_path = "./uploaded_files.json"

tv_address = "10.23.17.77"
tv_port = 8002

use_art_label = True

dezoomify_user_agent = "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36"
