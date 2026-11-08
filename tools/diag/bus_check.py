"""Bus check: does the TFT controller actually understand us? No need to look at the screen.

What:     resets the panel, writes registers + pixels over slow SoftSPI and reads them back via MISO.
Needs:    MISO wired, project deployed (uses config.py on the board).
Run:      uv run tools/mpr.py connect COM4 run tools/diag/bus_check.py
Expected (healthy ILI9341-ish panel):
    power after reset   08            sleep in
    power after on      9c            booster on, awake, display on
    madctl readback     a8 / 48       echoes what we wrote
    colmod              05            16 bit
    self diag           c0            regs loaded, panel detected
    gram readback       fc0000 00fc00 0000fc fcfcfc   (after one dummy byte)
    id DA DB DC         st7789: 85 85 52, ili9341: usually 00
Tells you:
    all ff         -> MISO not wired or controller dead / unpowered
    same byte everywhere, even in reset -> not the controller talking (crosstalk, wrong pin)
    readbacks ok but screen black       -> wiring is fine, look at init / backlight / reset after run
"""
import time
from machine import Pin
import config as cfg
from display import make_spi

dc = Pin(cfg.TFT_DC, Pin.OUT)
rst = Pin(cfg.TFT_RST, Pin.OUT)
spi = make_spi(cfg, soft=True, baud=200_000)


def cmd(c: int, data: bytes = b"") -> None:
    """Command + optional data."""
    dc(0)
    spi.write(bytes([c]))
    if data:
        dc(1)
        spi.write(data)


def rd(reg: int, n: int = 1) -> str:
    """Read n raw bytes after reg."""
    dc(0)
    spi.write(bytes([reg]))
    dc(1)
    return spi.read(n).hex(" ")


def check(label: str, got: str, want: str) -> None:
    """Print one line with ok/?? marker."""
    print("{:20s} {:28s} {}".format(label, got, "ok" if got.startswith(want) else "?? want " + want))


rst(0)
time.sleep_ms(50)
rst(1)
time.sleep_ms(150)
check("power after reset", rd(0x0A), "08")
cmd(0x11)
time.sleep_ms(150)
cmd(0x29)
check("power after on", rd(0x0A), "9c")
for v in (0xA8, 0x48):
    cmd(0x36, bytes([v]))
    check("madctl {:02x}".format(v), rd(0x0B), "{:02x}".format(v))
cmd(0x3A, b"\x55")
check("colmod", rd(0x0C), "05")
check("self diag", rd(0x0F), "c0")

cmd(0x2A, b"\x00\x00\x00\x03")
cmd(0x2B, b"\x00\x00\x00\x00")
cmd(0x2C, b"\xF8\x00\x07\xE0\x00\x1F\xFF\xFF")  # red green blue white
check("gram readback", rd(0x2E, 13), "00 fc 00 00 00 fc 00 00 00 fc fc fc fc")

print("id DA DB DC         ", rd(0xDA), rd(0xDB), rd(0xDC))
