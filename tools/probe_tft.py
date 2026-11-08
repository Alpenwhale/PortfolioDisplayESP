"""Board-side: cycle controller/SPI combos, show the variant number big.

Run: uv run tools/mpr.py connect COM4 run tools/probe_tft.py
Whichever number shows up clean (red bg, white digit) is the right combo.
"""
import time
from machine import Pin, SPI, SoftSPI
from display.tft import TFT
import config as cfg

# (controller, spi mode, soft spi?)
VARIANTS = (
    ("ili9341", 0, False),
    ("ili9341", 3, False),
    ("st7789", 3, False),
    ("st7789", 0, False),
    ("ili9341", 0, True),
    ("st7789", 3, True),
)
BAUD = 10_000_000  # slow on purpose, dupont wires


def make_spi(mode: int, soft: bool):
    """HW SPI(1) or bitbanged on the same pins."""
    pol, pha = mode >> 1, mode & 1
    if soft:
        return SoftSPI(baudrate=1_000_000, polarity=pol, phase=pha,
                       sck=Pin(14), mosi=Pin(13), miso=Pin(12))
    return SPI(1, baudrate=BAUD, polarity=pol, phase=pha)


def show(n: int, controller: str, mode: int, soft: bool) -> None:
    """Init with one combo and draw its number."""
    d = TFT(make_spi(mode, soft), None, Pin(cfg.TFT_DC, Pin.OUT),
            Pin(cfg.TFT_RST, Pin.OUT), rotation=1, controller=controller)
    red, white = d.rgb(200, 0, 0), d.rgb(255, 255, 255)
    d.fill(red)
    d.text(str(n), 120, 60, white, red, scale=10)
    d.text("{} m{}{}".format(controller, mode, " soft" if soft else ""), 8, 200, white, red, scale=2)


for n, (ctrl, mode, soft) in enumerate(VARIANTS, 1):
    print("variant", n, ctrl, "mode", mode, "soft" if soft else "hw")
    show(n, ctrl, mode, soft)
    time.sleep(6)
print("done")
