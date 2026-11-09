"""Probe: which controller profile / SPI mode / inversion fits an unknown panel? Watch the screen.

What:     cycles combos, each fills red and shows its number big, 6 s per variant.
Needs:    project deployed. Uses pins + size from config.py, ignores TFT_CONTROLLER/MODE/INVERT.
Run:      uv run tools/mpr.py connect COM4 run tools/diag/probe.py
Expected: one number shows clean, red background + white digit + its label at the bottom.
          Colors inverted (cyan bg, black digit) -> right combo but flip TFT_INVERT.
          Blue instead of red -> flip TFT_BGR.
Tells you: the values for TFT_CONTROLLER / TFT_SPI_MODE / TFT_INVERT in config.py.
"""
import time
from machine import Pin
import config as cfg
from display import make_spi
from display.tft import TFT
from ui import font

# (controller, spi mode, invert)
VARIANTS = (
    ("ili9341", 0, False),
    ("ili9341", 3, False),
    ("st7789", 3, True),
    ("st7789", 0, True),
    ("st7789", 3, False),
)
HOLD_S = 6


def show(n: int, controller: str, mode: int, invert: bool) -> None:
    """Init with one combo and draw its number."""
    cfg.TFT_SPI_MODE = mode
    d = TFT(make_spi(cfg, baud=10_000_000), Pin(cfg.TFT_DC, Pin.OUT), Pin(cfg.TFT_RST, Pin.OUT),
            width=cfg.TFT_WIDTH, height=cfg.TFT_HEIGHT, rotation=1,
            controller=controller, invert=invert, bgr=cfg.TFT_BGR)
    red, white = d.rgb(200, 0, 0), d.rgb(255, 255, 255)
    d.fill(red)
    d.draw(font.get("xl"), str(n), d.width // 2 - 15, 40, white, red)
    d.text("{} m{}{}".format(controller, mode, " inv" if invert else ""), 8, d.height - 16, white, red)


for n, v in enumerate(VARIANTS, 1):
    print("variant", n, v)
    show(n, *v)
    time.sleep(HOLD_S)
print("done")
