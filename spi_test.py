import RPi.GPIO as GPIO
import spidev
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

# Setup GPIO
GPIO.setmode(GPIO.BCM)

GPIO.setup(HRDY, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
GPIO.setup(RESET, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(CS_PIN, GPIO.OUT)

# reset
GPIO.output(RESET, GPIO.LOW)
time.sleep(0.1)
GPIO.output(RESET, GPIO.HIGH)


def delay_ms(delaytime):
    time.sleep(float(delaytime) / 1000.0)


def reset():
    GPIO.output(RESET, GPIO.LOW)
    delay_ms(200)
    GPIO.output(RESET, GPIO.HIGH)
    delay_ms(200)


def wait_for_hrdy():
    while GPIO.input(HRDY) == 0:
        time.sleep(0.01)  # Wait for HRDY to become high


def spi_transfer(data):
    # wait_for_hrdy()
    response = spi.xfer2(data, 2000000, 10, 8)
    return response


def spi_send_command(preamble, command, response_size):
    # GPIO.output(CS_PIN, GPIO.LOW)
    spi_transfer(preamble)
    # wait_for_hrdy()
    spi_transfer(command)
    # wait_for_hrdy()
    # time.sleep(DELAY_US / 1000000)
    if response_size > 0:
        response = spi_transfer([0] * response_size)
    else:
        response = None

    # GPIO.output(CS_PIN, GPIO.HIGH)
    return response


# Create an SPI instance
spi = spidev.SpiDev()
# Open SPI bus 0, device (CS) 0
spi.open(SPI_BUS, SPI_DEVICE)
spi.max_speed_hz = 1000000
spi.mode = 0b00

# reset board
reset()


spi_send_command(command_preamble, command_run, 0)
wait_for_hrdy()
response = spi_send_command(command_preamble, command_info, 20)

# Display the received data
print("Received Data: ", response)

# Close the SPI connection
spi.close()
GPIO.cleanup()
