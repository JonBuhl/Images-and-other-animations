"""Hardware and runtime configuration.

Everything that depends on the board wiring lives here. Adjust the pin
numbers if you use a board other than a classic ESP32 DevKit (WROOM-32).
"""

from micropython import const

# --- Panel (Ikea FREKVENS, 16x16, shift register chain) ----------------------

PIN_CLK = const(18)     # panel wire 4 (Clk)   -> SPI SCK
PIN_DATA = const(23)    # panel wire 3 (Data)  -> SPI MOSI
PIN_LATCH = const(21)   # panel wire 5 (Latch)
PIN_EN = const(22)      # panel wire 2 (En)    -> PWM, active low
PIN_MISO = const(19)    # not connected, the ESP32 SPI driver still wants a pin

SPI_ID = const(2)               # 2 = VSPI on the ESP32
SPI_BAUDRATE = const(10000000)  # 10 MHz, the 74HC595 chain copes easily

PWM_FREQ = const(1000)          # brightness PWM on the En line

# --- Buttons (optional, set to False if you did not wire them) ---------------

BUTTONS_ENABLED = True
PIN_BTN_MODE = const(32)  # yellow button, other side to GND
PIN_BTN_PWR = const(33)   # red button, other side to GND

# --- Network -----------------------------------------------------------------

HOSTNAME = "boxoflife"          # try http://boxoflife.local/
WIFI_TIMEOUT = const(15)        # seconds to wait for the station to connect

AP_SSID = "Box-of-Life"         # fallback access point when no STA connection
AP_PASSWORD = "boxoflife"       # at least 8 characters

HTTP_PORT = const(80)

# --- Storage / limits --------------------------------------------------------

WIFI_FILE = "/wifi.json"
SETTINGS_FILE = "/settings.json"

MAX_FRAMES = const(300)         # frames per uploaded animation
MAX_UPLOAD = const(16384)       # bytes accepted by /api/upload
MAX_JSON = const(2048)          # bytes accepted for JSON request bodies
