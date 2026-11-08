"""Stages: bus check passes but main.py shows nothing? Find the layer that breaks. Watch the screen.

What:     5 stages, 6 s each, then holds 20 s. Each stage swaps one thing.
            1 red     bare init, SoftSPI           baseline, should always work
            2 green   driver init, SoftSPI         driver init sequence
            3 blue    bare init, HW SPI mode 0     hardware SPI
            4 yellow  bare init, HW SPI mode 3
            5 test    exactly main.py              config values, full speed
Needs:    project deployed.
Run:      uv run tools/mpr.py connect COM4 run tools/diag/stages.py
Expected: red, green, blue, yellow, then the test screen stays.
Tells you: first missing color = broken layer.
          2 missing -> driver init / controller profile wrong.
          3+4 missing -> HW SPI issue, try TFT_SPI_ID = -1.
          only 5 missing -> TFT_SPI_BAUD too high or wrong TFT_SPI_MODE.
Note:     screen going black after the script ends = board reset on disconnect, not a driver bug.
"""
import time
from machine import Pin
import config as cfg
from display import make_spi
from display.tft import TFT

dc = Pin(cfg.TFT_DC, Pin.OUT)
rst = Pin(cfg.TFT_RST, Pin.OUT)
W, H = cfg.TFT_WIDTH, cfg.TFT_HEIGHT
HOLD_S = 6


def spi_for(soft: bool, mode: int):
    """SPI with given mode, 10 MHz HW or 1 MHz soft."""
    cfg.TFT_SPI_MODE = mode
    return make_spi(cfg, soft=soft, baud=1_000_000 if soft else 10_000_000)


def cmd(spi, c: int, data: bytes = b"") -> None:
    """Command + optional data."""
    dc(0)
    spi.write(bytes([c]))
    if data:
        dc(1)
        spi.write(data)


def bare_fill(spi, color: bytes) -> None:
    """Minimal init (no power/gamma), full fill."""
    rst(0); time.sleep_ms(50); rst(1); time.sleep_ms(150)
    cmd(spi, 0x11); time.sleep_ms(150)
    cmd(spi, 0x3A, b"\x55")
    cmd(spi, 0x13)
    cmd(spi, 0x29)
    cmd(spi, 0x2A, bytes([0, 0, (W - 1) >> 8, (W - 1) & 255]))
    cmd(spi, 0x2B, bytes([0, 0, (H - 1) >> 8, (H - 1) & 255]))
    cmd(spi, 0x2C)
    dc(1)
    row = color * W
    for _ in range(H):
        spi.write(row)


def driver_fill(spi) -> None:
    """Driver init with config profile, green."""
    d = TFT(spi, dc, rst, width=W, height=H, controller=cfg.TFT_CONTROLLER,
            invert=cfg.TFT_INVERT, bgr=cfg.TFT_BGR)
    d.fill(d.rgb(0, 255, 0))


def stage(n: int, name: str, fn) -> None:
    """Run one stage and hold."""
    print("stage", n, name)
    fn()
    time.sleep(HOLD_S)


mode = cfg.TFT_SPI_MODE
stage(1, "red bare soft", lambda: bare_fill(spi_for(True, 0), b"\xF8\x00"))
stage(2, "green driver soft", lambda: driver_fill(spi_for(True, 0)))
stage(3, "blue bare hw m0", lambda: bare_fill(spi_for(False, 0), b"\x00\x1F"))
stage(4, "yellow bare hw m3", lambda: bare_fill(spi_for(False, 3), b"\xFF\xE0"))
cfg.TFT_SPI_MODE = mode
print("stage 5 main.py")
import main  # noqa: E402,F401  draws on import
print("done, holding 20 s")
time.sleep(20)
