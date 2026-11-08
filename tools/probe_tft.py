"""Board-side: cycle controller/SPI-mode combos, show the variant number big.

Run: uv run tools/mpr.py connect COM4 run tools/probe_tft.py
Whichever number shows up clean (red bg, white digit) is the right combo.
"""
import time
from machine import Pin, SPI
from display.tft import TFT
import config as cfg

VARIANTS = (
    ("ili9341", 0),
    ("ili9341", 3),
    ("st7789", 3),
    ("st7789", 0),
)
BAUD = 10_000_000  # slow on purpose, dupont wires


def show(n: int, controller: str, mode: int) -> None:
    """Init with one combo and draw its number."""
    spi = SPI(1, baudrate=BAUD, polarity=mode >> 1, phase=mode & 1)
    d = TFT(spi, None, Pin(cfg.TFT_DC, Pin.OUT), Pin(cfg.TFT_RST, Pin.OUT),
            rotation=1, controller=controller)
    red, white = d.rgb(200, 0, 0), d.rgb(255, 255, 255)
    d.fill(red)
    d.text(str(n), 120, 60, white, red, scale=10)
    d.text("{} mode{}".format(controller, mode), 8, 200, white, red, scale=2)


for n, (ctrl, mode) in enumerate(VARIANTS, 1):
    print("variant", n, ctrl, "mode", mode)
    show(n, ctrl, mode)
    time.sleep(6)
print("done")
