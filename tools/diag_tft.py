"""Board-side: read controller ID regs over MISO. Needs MISO -> D6.

Run: uv run tools/mpr.py connect COM4 run tools/diag_tft.py
ILI9341 -> D3 gives .. 00 93 41. ST7789 -> 04 gives 85 85 52-ish.
All FF/00 = no data coming back (wiring/power).
"""
import time
from machine import Pin, SPI
import config as cfg

dc = Pin(cfg.TFT_DC, Pin.OUT)
rst = Pin(cfg.TFT_RST, Pin.OUT)


def reset() -> None:
    """Hard reset the panel."""
    rst(0)
    time.sleep_ms(50)
    rst(1)
    time.sleep_ms(150)


def read_reg(spi: SPI, reg: int, n: int = 4) -> str:
    """Send reg, clock back n bytes, hex string."""
    dc(0)
    spi.write(bytes([reg]))
    dc(1)
    return spi.read(n).hex(" ")


for mode in (0, 3):
    spi = SPI(1, baudrate=1_000_000, polarity=mode >> 1, phase=mode & 1)
    reset()
    print("mode", mode,
          "| 04:", read_reg(spi, 0x04),
          "| 09:", read_reg(spi, 0x09, 5),
          "| D3:", read_reg(spi, 0xD3))

miso = Pin(12, Pin.IN)
print("MISO idle level:", miso.value())
