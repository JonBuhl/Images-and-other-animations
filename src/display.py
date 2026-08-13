"""Driver for the 16x16 FREKVENS LED panel on an ESP32.

The panel is a chain of shift registers: 32 bytes are clocked in (byte 0..15
are the top half, byte 16..31 the bottom half, one byte per column, LSB is the
top row) and then latched. That bit layout is exactly `framebuf.MONO_VLSB`,
so `Screen` can inherit all the drawing primitives for free.

Unlike the original Pico version this uses hardware SPI instead of bit
banging. SPI shifts out MSB first, so every byte is mirrored through a lookup
table before it goes out on the wire.
"""

import framebuf
import random
from machine import Pin, SPI, PWM

import config


# --- HW ----------------------------------------------------------------------

_latch = Pin(config.PIN_LATCH, Pin.OUT, value=0)

_spi = SPI(
    config.SPI_ID,
    baudrate=config.SPI_BAUDRATE,
    polarity=0,
    phase=0,
    sck=Pin(config.PIN_CLK),
    mosi=Pin(config.PIN_DATA),
    miso=Pin(config.PIN_MISO),
)

# En is active low: duty 65535 == output disabled == panel dark.
_pwm = PWM(Pin(config.PIN_EN), freq=config.PWM_FREQ, duty_u16=65535)

# bit reversal table (SPI sends MSB first, the panel expects LSB first)
def _rev8(b):
    b = ((b & 0xF0) >> 4) | ((b & 0x0F) << 4)
    b = ((b & 0xCC) >> 2) | ((b & 0x33) << 2)
    b = ((b & 0xAA) >> 1) | ((b & 0x55) << 1)
    return b

_REV = bytes(_rev8(i) for i in range(256))

_brightness = 0


def set_brightness(percent):
    """Set panel brightness in percent (0..100)."""
    global _brightness
    percent = max(0, min(100, int(percent)))
    _brightness = percent
    # squared curve, the linear duty cycle looks very top heavy to the eye
    level = (percent * percent * 65535) // 10000
    _pwm.duty_u16(65535 - level)


def get_brightness():
    return _brightness


# --- buffer operations -------------------------------------------------------

class Screen(framebuf.FrameBuffer):
    """A 16x16 mono frame buffer that knows how to push itself to the panel."""

    def __init__(self):
        self.buffer = bytearray(32)
        self._out = bytearray(32)
        super().__init__(self.buffer, 16, 16, framebuf.MONO_VLSB)

    def __eq__(self, other):
        return self.buffer == other.buffer

    # kept for compatibility with the original API
    def get(self, x, y):
        return self.pixel(x, y)

    def set(self, x, y, v):
        self.pixel(x, y, v)

    def clear(self):
        self.fill(0)

    def fill_random(self):
        for i in range(32):
            self.buffer[i] = random.getrandbits(8)

    def load(self, data):
        """Copy 32 raw bytes (upload format) into the buffer."""
        self.buffer[:] = data

    def show(self):
        out = self._out
        buf = self.buffer
        rev = _REV
        for i in range(32):
            out[i] = rev[buf[i]]
        _spi.write(out)
        _latch.on()
        _latch.off()


def blank():
    """Immediately blank the panel without touching any frame buffer."""
    _spi.write(bytes(32))
    _latch.on()
    _latch.off()
