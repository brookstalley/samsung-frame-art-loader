# good info: https://github.com/jhirner/pi-frame/

from omni_epd import displayfactory
from PIL import Image
from art_label import ArtLabel

class DisplayIT8951:
    def __init__(self):
        self.epd = displayfactory.load_display_driver("waveshare_epd.it8951")
        self.epd.prepare()

    def display_image(self, image: Image):
        self.epd.display(image)

    def close(self):
        self.epd.close()

if __name__ == "__main__":
    display = DisplayIT8951()
    art_label = ArtLabel(
        width=1448,
        height=1072,
        greyscale_bits=4,
        artist_name="Artist Name",
        artist_lifespan="Artist Lifespan",
        artwork_title="Artwork Title",
        creation_date="Creation Date"
    )
    display.display_image(art_label)
    display.close()

