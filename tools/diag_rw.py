"""Board-side: write regs, read them back. Proves CLK/MOSI/DC/MISO path.

Run: uv run tools/mpr.py connect COM4 run tools/diag_rw.py
0A = power mode (after reset ~08, after sleep-out+on ~9C).
0B = MADCTL readback, should echo what we wrote.
"""
import time
from machine import Pin, SoftSPI
import config as cfg

dc = Pin(cfg.TFT_DC, Pin.OUT)
rst = Pin(cfg.TFT_RST, Pin.OUT)


def cmd(spi: SoftSPI, c: int, data: bytes = b"") -> None:
    """Command + optional data."""
    dc(0)
    spi.write(bytes([c]))
    if data:
        dc(1)
        spi.write(data)


def rd(spi: SoftSPI, reg: int, n: int = 3) -> str:
    """Read n raw bytes after reg."""
    dc(0)
    spi.write(bytes([reg]))
    dc(1)
    return spi.read(n).hex(" ")


for mode in (0, 3):
    spi = SoftSPI(baudrate=100_000, polarity=mode >> 1, phase=mode & 1,
                  sck=Pin(14), mosi=Pin(13), miso=Pin(12))
    rst(0)
    time.sleep_ms(50)
    rst(1)
    time.sleep_ms(150)
    print("mode", mode)
    print("  0A after reset   :", rd(spi, 0x0A))
    cmd(spi, 0x11)
    time.sleep_ms(150)
    cmd(spi, 0x29)
    print("  0A after on      :", rd(spi, 0x0A))
    for v in (0xA8, 0x48):
        cmd(spi, 0x36, bytes([v]))
        print("  0B after 36={:02X} :".format(v), rd(spi, 0x0B))
