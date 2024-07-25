# import resizing from PIL
from PIL import Image, ImageFilter, ImageChops

import asyncio
import cv2
import logging
import numpy as np
import os
import subprocess
from skimage.transform import resize
from scipy.spatial.distance import pdist, squareform
import requests
import re
from source_utils import artic_metadata_for_url
import time
from colormath.color_objects import sRGBColor, LabColor
from colormath.color_conversions import convert_color
from colormath.color_diff import delta_e_cie2000

import config

logging.basicConfig(format="%(levelname)s:%(message)s", level=logging.INFO)

dezoomify_rs_path = "dezoomify-rs"
dezoomify_params = f'--max-width 8192 --max-height 8192 --compression 0 --parallelism 16 --min-interval 100ms --tile-cache "{config.dezoomify_tile_cache}" --header "{config.dezoomify_user_agent}"'

last_artic_call = 0


# Enums for resizing options
class ResizeOptions:
    SCALE = "scaled"
    CROP = "cropped"


class ImageSources:
    GOOGLE_ARTSANDCULTURE = "google"
    HTTP = "http"
    ARTIC = "artic"


def image_source(url):
    # If the URL is a Google Arts and Culture URL, use dezoomify-rs to download the image
    if "artsandculture.google.com" in url:
        return ImageSources.GOOGLE_ARTSANDCULTURE
    elif "www.artic.edu/artworks" in url:
        return ImageSources.ARTIC
    else:
        return ImageSources.HTTP


def pairwise_distances(palette):
    # Calculate pairwise Euclidean distances between the colors in the palette
    distances = pdist(palette, metric="euclidean")

    # Convert the distances to a square matrix form
    distance_matrix = squareform(distances)

    # Calculate the average distance
    average_distance = np.mean(distances)

    # Calculate the standard deviation of the distances
    std_distance = np.std(distances)

    print("Average Distance: ", average_distance)
    print("Standard Deviation of Distances: ", std_distance)


def get_average_color(image: Image):
    # skimage = io.imread(image)[:, :, :-1]

    # We don't need a giant image to get average color. If it is larger than 2048x2048, resize it. But do not overwrite the original image!
    max_size = 768
    np_image = np.array(image)
    working_image = resize(np_image, (max_size, max_size), anti_aliasing=False)

    my_image = np.array(working_image)
    average = my_image.mean(axis=0).mean(axis=0)

    return average


def get_dominant_colors_five(image: Image):
    # We don't need a giant image to get average color. If it is larger than 2048x2048, resize it. But do not overwrite the original image!
    max_size = 768
    np_image = np.array(image)
    working_image = resize(np_image, (max_size, max_size), anti_aliasing=False)

    pixels = np.float32(working_image.reshape(-1, 3))
    n_colors = 5
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.1)
    flags = cv2.KMEANS_RANDOM_CENTERS
    _, labels, palette = cv2.kmeans(pixels, n_colors, None, criteria, 10, flags)
    _, counts = np.unique(labels, return_counts=True)
    # pairwise_distances(palette)
    # print(f"Dominant distance: {dom_distance}")

    dominant = palette[np.argmax(counts)]
    print(f"dominant: {dominant}")
    return dominant


import numpy as np
import cv2


def get_top_n_colors(image, coverage_threshold=0.8, tmp_name: str = None):
    # We don't need a giant image to get average color. If it is larger than 2048x2048, resize it. But do not overwrite the original image!
    max_size = 512
    max_distance = 15

    image.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    np_image = np.array(image.convert("RGB"))
    lab_image = cv2.cvtColor(np_image, cv2.COLOR_RGB2LAB)

    # Reshape the image to a 2D array of pixels
    pixels = lab_image.reshape(-1, 3).astype(np.float32)

    # Define criteria for k-means clustering
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 200, 0.95)
    # flags = cv2.KMEANS_RANDOM_CENTERS
    flags = cv2.KMEANS_PP_CENTERS

    # Start with an initial guess for the number of clusters
    initial_n_colors = 2
    max_colors = 20  # Set a reasonable maximum to avoid infinite loops
    for n_colors in range(initial_n_colors, max_colors + 1):
        # Apply k-means clustering
        ret, labels, centers = cv2.kmeans(pixels, n_colors, None, criteria, 50, flags)
        centers = np.uint8(centers)

        # Generate the intermediate image
        intermediate_image = centers[labels.flatten()]
        intermediate_image = intermediate_image.reshape(lab_image.shape)

        # Calculate the absolute difference between each pixel and the intermediate image
        diff = np.abs(lab_image.astype(np.float32) - intermediate_image.astype(np.float32))

        # Calculate the distance (Euclidean norm) for each pixel
        distances = np.linalg.norm(diff, axis=2)
        # print(f"average distance for {n_colors} colors: {np.mean(distances)}")

        # Determine the number of pixels within the max_distance from any cluster center
        within_threshold = distances <= max_distance
        coverage = np.sum(within_threshold) / pixels.shape[0]

        # generate image to show this cluster result
        if tmp_name is not None:

            img_file = f"{config.art_folder_temp}/{os.path.basename(tmp_name)}_cluster_{n_colors}_{int(coverage*100)}pct.jpg"

            res3 = cv2.cvtColor(intermediate_image, cv2.COLOR_LAB2RGB)

            print(f"writing {img_file}")
            Image.fromarray(res3).save(img_file)

        print(f"Coverage for {n_colors} colors: {coverage})")
        # Check if the coverage exceeds the threshold
        if coverage >= coverage_threshold:
            break

    # Flatten labels for bincount
    flat_labels = labels.flatten()

    # Determine the number of colors required to meet the coverage threshold
    top_n = np.argmax(np.cumsum(np.bincount(flat_labels)) / pixels.shape[0] >= coverage_threshold) + 1
    top_colors = centers[:top_n]
    top_color_counts = np.bincount(flat_labels)[:top_n]

    # Calculate the percentage of each top color
    top_color_percentages = top_color_counts / pixels.shape[0]

    return top_colors, top_color_percentages


def resize_image_with_matte(image: Image, resize_option, width, height, tmp_name=None) -> Image:
    # Get x and y dimensions
    x, y = image.size
    if (x == width) and (y == height):
        # image is already the correct size
        return image

    dominant_color = (0, 0, 0)
    if resize_option == ResizeOptions.SCALE:
        dominant = get_dominant_colors_five(image)
        all_dominants = get_top_n_colors(image, tmp_name=tmp_name)
        print(f"dominant color: {dominant}")

        mutiplier: float = 0.66
        dominant_color = (
            int((dominant[0] * 256) * mutiplier),
            int((dominant[1] * 256) * mutiplier),
            int((dominant[2] * 256) * mutiplier),
        )
    canvas = Image.new("RGB", (width, height), dominant_color)
    description_box = None
    if resize_option == ResizeOptions.SCALE:
        # Determine whether to scale x or y to width x height
        if (x / width) > (y / height):
            new_y = int(y * (width / x))
            new_x = width
            description_box = (0, y, width, height)  # Get the bottom area for descriptions
        else:
            new_x = int(x * (height / y))
            new_y = height
            description_box = (x, 0, width, height)  # Get the right area for descriptions

        image = image.resize((new_x, new_y), Image.Resampling.LANCZOS)

        # paste image into center of canvas
        paste_box = (int((width - x) / 2), int((height - y) / 2))
        canvas.paste(image, paste_box)
        # Get the coordinates of the added borders

    elif resize_option == ResizeOptions.CROP:
        # first resize so the smallest dimension is width or height
        if (x / width) > (y / height):
            # The image's aspect ratio is wider than the target. Scale y to match target height and then crop x to match target width
            scale = height / y
            x = int(x * scale)
            image = image.resize((x, height), Image.Resampling.LANCZOS)
            crop_box = (int((x - width) / 2), 0, int((x + width) / 2), height)
            image = image.crop(crop_box)

        else:
            # The image's aspect ratio is taller than the target. Scale x to match target width and then crop y to match target height
            scale = width / x
            y = int(y * scale)
            image = image.resize((width, y), Image.Resampling.LANCZOS)
            crop_box = (0, int((y - height) / 2), width, int((y + height) / 2))
            image = image.crop(crop_box)

        canvas.paste(image, (0, 0))
    return canvas, description_box


def resize_file_with_matte(in_file: str, out_file: str, width, height, resize_option):
    # load image from file
    # set decompression limit high
    logging.info(f"Resizing {in_file} to {out_file} at {width}x{height}")
    Image.MAX_IMAGE_PIXELS = 933120000

    image = Image.open(in_file)
    resized, description_box = resize_image_with_matte(image, resize_option, width, height, tmp_name=in_file)

    # Save the resized image
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    if in_file.endswith(".jpg"):
        resized.save(out_file, "JPEG", quality=95)
    elif in_file.endswith(".png"):
        resized.save(out_file, "PNG")
    logging.debug(f"Resized {in_file} to {out_file}")


def get_image_dimensions(image_path: str) -> tuple[int, int]:
    image = Image.open(image_path)
    width, height = image.size[0], image.size[1]
    image.close()
    return width, height


async def get_dezoomify_file(
    url, destination_dir: str, destination_fullpath: str, out_file: str = "", http_referer: str = None
) -> tuple[bool, str]:
    # Run dezoomify-rs, passing dezoomify_params as arguments and starting in the art_folder_raw directory
    # See https://github.com/lovasoa/dezoomify-rs for info
    if out_file is not None and out_file != "":
        out_file = os.path.join(destination_dir, out_file)
        # Dezoomify will error out if the file already exists. If out_file is specified, delete it if it does exist
        if os.path.exists(out_file):
            os.remove(out_file)

    my_params = dezoomify_params
    if http_referer is not None:
        my_params = f"{my_params} --header 'Referer: {http_referer}'"
    cmdline = f'{dezoomify_rs_path} {my_params} "{url}"'
    if out_file is not None and out_file != "":
        cmdline = f'{cmdline} "{out_file}"'
    cmdline = cmdline.strip()
    logging.debug(f"Running: {cmdline}")
    p = subprocess.Popen(
        cmdline,
        shell=True,
        cwd=destination_dir,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    p.wait()
    out, err = p.communicate()
    # get the output of the command
    if p.returncode != 0:
        if p.returncode == 1:
            # We got some tiles but not all of them
            # the out message will look like b"\x1b[38;5;11mOnly 332 tiles out of 441 could be downloaded. The resulting image was still created in '/home/brooks/art/raw/Jasper Johns - Target.jpg'.\n
            # Parse the X of Y part and present it nicely
            match = re.search(r"Only (\d+) tiles out of (\d+) could be downloaded", out.decode("utf-8"))
            if match:
                logging.info(f"Only {match.group(1)} out of {match.group(2)} tiles could be downloaded.")
            else:
                logging.error(f"Error running dezoomify-rs: {p.returncode}")
                logging.info(out)
                logging.error(err)
        # Dezoomify likes creating images with missing tiles. If one was created, delete it.
        # Any successfully cached tiles will be used later
        if os.path.exists(out_file):
            os.remove(out_file)
        return False, None
    out_file = out.decode("utf-8").split("'")[1]
    logging.info(f"Downloaded {out_file}")
    if destination_fullpath:
        os.rename(out_file, destination_fullpath)
        out_file = destination_fullpath
    return True, out_file


async def images_match(image1: Image, image2: Image, match_threshold=0.10) -> bool:
    # Use numpy for a fast compare. Resize images to 384x216 for faster compare.
    # Check for a close match because resizing and other factors can cause a perfect match to fail
    image1 = image1.convert("L").resize((384, 216)).filter(ImageFilter.GaussianBlur(radius=2))
    image2 = image2.convert("L").resize((384, 216)).filter(ImageFilter.GaussianBlur(radius=2))
    img3 = ImageChops.subtract(image1, image2)
    diff = sum(list(img3.getdata())) / (384 * 216)  # normalize
    logging.info(f"Images match: {diff}")
    return diff < match_threshold


async def get_google_image(url, destination_fullpath: str, destination_dir: str) -> tuple[bool, str]:
    success, out_file = await get_dezoomify_file(
        url=url, destination_dir=destination_dir, destination_fullpath=destination_fullpath
    )
    return success, out_file


async def get_http_image(url, destination_fullpath: str = None, destination_dir: str = None) -> tuple[bool, str]:
    # Download the image from the URL
    logging.info(f"Downloading {url}")
    try:
        response = requests.get(url)
        response.raise_for_status()
    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return False, None

    if destination_fullpath:
        filename = destination_fullpath
    else:
        filename = os.path.join(destination_dir, os.path.basename(url))

    with open(filename, "wb") as f:
        f.write(response.content)

    return True, filename


async def artic_throttle():
    global last_artic_call

    current_time = time.time()
    elapsed_time = current_time - last_artic_call
    if elapsed_time < 5000:
        wait_time = 5000 - elapsed_time
        logging.debug(f"Waiting {wait_time}ms")
        await asyncio.sleep(wait_time / 1000)


async def artic_accessed():
    global last_artic_call
    last_artic_call = time.time()


async def get_artic_image(url, destination_fullpath: str = None, destination_dir: str = None) -> tuple[bool, str]:
    # Download the image from the URL
    global last_artic_call

    logging.debug(f"Downloading {url}")
    await artic_throttle()
    metadata = await artic_metadata_for_url(url)
    await artic_accessed()

    try:
        # load json from the API url

        image_id = metadata["data"]["image_id"]
        iiif_url = metadata["config"]["iiif_url"]
        info_url = f"{iiif_url}/{image_id}/info.json"
        # Make the filename
        artist = metadata["data"]["artist_title"]
        title = metadata["data"]["title"]
        # strip out bad filename characters
        filename = f"{artist} - {title}.jpg"
        keepcharacters = (" ", ".", "_", "-")
        clean_filename = "".join(c for c in filename if c.isalnum() or c in keepcharacters).rstrip()
        await artic_throttle()
        success, out_file = await get_dezoomify_file(
            info_url, destination_dir, destination_fullpath, clean_filename, http_referer=info_url
        )
        await artic_accessed()
        return success, out_file

    except requests.exceptions.RequestException as e:
        logging.error(f"Error downloading {url}: {e}")
        return False, None
    except Exception as e:
        logging.error(f"Error downloading {url}: {e}")
        return False, None


async def get_image(url, destination_fullpath: str = None, destination_dir: str = None) -> tuple[bool, str]:
    logging.debug(f"Getting image from {url}")
    match image_source(url):
        case ImageSources.GOOGLE_ARTSANDCULTURE:
            # Dezoomify can get a good filename for Google even if destination_fullpath is None
            return await get_google_image(url, destination_fullpath=destination_fullpath, destination_dir=destination_dir)
        case ImageSources.ARTIC:
            # Dezoomify cannot determine a filename for artic if destination_fullpath is None
            return await get_artic_image(url, destination_fullpath=destination_fullpath, destination_dir=destination_dir)
        case ImageSources.HTTP:
            return await get_http_image(url, destination_fullpath, destination_dir)
        case _:
            raise Exception("Unknown image source")
