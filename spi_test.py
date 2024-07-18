import RPi.GPIO as GPIO
import time


CS_PIN = 8
HRDY = 24
RESET = 17
DELAY_US = 10
SPI_BUS = 0
SPI_DEVICE = 0

IT8951_TCON_SYS_RUN = 0x0001

# Convert preamble and command to bytes
command_preamble = [0x60, 0x00]
command_info = [0x03, 0x02]
command_run = [0x00, 0x01]
import RPi.GPIO as GPIO
import spidev
import time

# Constants
CS_PIN = 8
HRDY = 24
RESET = 17
DELAY_US = 10
SPI_BUS = 0
SPI_DEVICE = 0

# SPI Initialization data
init_data = [0x60, 0x00, 0x03, 0x02]

# Setup GPIO
GPIO.setmode(GPIO.BCM)
GPIO.setup(CS_PIN, GPIO.OUT)
GPIO.setup(HRDY, GPIO.IN)
GPIO.setup(RESET, GPIO.OUT)

# Initialize SPI
spi = spidev.SpiDev()
spi.open(SPI_BUS, SPI_DEVICE)
spi.max_speed_hz = 100000


def spi_transfer(data):
    GPIO.output(CS_PIN, GPIO.LOW)
    time.sleep(DELAY_US / 1000000.0)  # Convert microseconds to seconds
    received = spi.xfer2(data)
    GPIO.output(CS_PIN, GPIO.HIGH)
    return received


def main():
    # Reset the device
    GPIO.output(RESET, GPIO.LOW)
    time.sleep(0.1)
    GPIO.output(RESET, GPIO.HIGH)
    time.sleep(0.1)

    # Send initialization data
    response = spi_transfer(init_data)

    # Read the first 20 bytes received in return
    read_data = spi_transfer([0x00] * 20)

    # Print the received data
    print("Received data:", read_data)


if __name__ == "__main__":
    try:
        main()
    finally:
        spi.close()
        GPIO.cleanup()
