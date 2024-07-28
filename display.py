# good info: https://github.com/jhirner/pi-frame/

from art import ArtFile
from omni_epd import displayfactory, EPDNotFoundError
from PIL import Image
from art_label import ArtLabel
import config


class DisplayLabel:
    def __init__(self):
        self.rotate = 180
        try:
            self.epd = displayfactory.load_display_driver(config.EPD_TYPE)
        except EPDNotFoundError:
            print(f"Could not find EPD dispaly {config.EPD_TYPE}")
            return

    def display_image(self, image: Image):
        my_image = image.copy()
        my_image = my_image.rotate(self.rotate)
        self.epd.prepare()
        self.epd.display(my_image)
        self.epd.sleep()

    def close(self):
        self.epd.close()


if __name__ == "__main__":
    display = DisplayLabel()
    artfile = ArtFile(
        artist_name="Artist Name",
        artist_lifespan="Artist Lifespan",
        artwork_title="Artwork Title",
        creation_date="Creation Date",
        medium="Artwork medium",
        description="Artwork description",
    )
    artlabel = ArtLabel(width=648, height=480, greyscale_bits=1, artfile=artfile)
    label_image = artlabel.get_image()
    label_image.save(config.art_folder_label + "/label_test.png")
    display.display_image(label_image)
    display.close()
