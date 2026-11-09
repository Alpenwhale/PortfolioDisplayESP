"""Panel init for display.tft. Only loaded when the panel really gets (re)initialised (boot)."""
import time

# MADCTL rotation bits per controller (BGR added separately)
ROT = {
    "ili9341": (0x40, 0x20, 0x80, 0xE0),
    "st7789": (0x00, 0x60, 0xC0, 0xA0),
}

# power/vcom/gamma. minimal init leaves some panels black.
SEQ = {
    "ili9341": (
        (0xEF, b"\x03\x80\x02"),
        (0xCF, b"\x00\xC1\x30"),
        (0xED, b"\x64\x03\x12\x81"),
        (0xE8, b"\x85\x00\x78"),
        (0xCB, b"\x39\x2C\x00\x34\x02"),
        (0xF7, b"\x20"),
        (0xEA, b"\x00\x00"),
        (0xC0, b"\x23"),
        (0xC1, b"\x10"),
        (0xC5, b"\x3E\x28"),
        (0xC7, b"\x86"),
        (0xB1, b"\x00\x18"),
        (0xB6, b"\x08\x82\x27"),
        (0xF2, b"\x00"),
        (0x26, b"\x01"),
        (0xE0, b"\x0F\x31\x2B\x0C\x0E\x08\x4E\xF1\x37\x07\x10\x03\x0E\x09\x00"),
        (0xE1, b"\x00\x0E\x14\x03\x11\x07\x31\xC1\x48\x08\x0F\x0C\x31\x36\x0F"),
    ),
    "st7789": (
        (0xB2, b"\x0C\x0C\x00\x33\x33"),
        (0xB7, b"\x35"),
        (0xBB, b"\x19"),
        (0xC0, b"\x2C"),
        (0xC2, b"\x01"),
        (0xC3, b"\x12"),
        (0xC4, b"\x20"),
        (0xC6, b"\x0F"),
        (0xD0, b"\xA4\xA1"),
        (0xE0, b"\xD0\x04\x0D\x11\x13\x2B\x3F\x54\x4C\x18\x0D\x0B\x1F\x23"),
        (0xE1, b"\xD0\x04\x0C\x11\x13\x2C\x3F\x44\x51\x2F\x1F\x1F\x20\x23"),
    ),
}


def run(tft, controller: str, rotation: int, invert: bool, bgr: bool) -> None:
    """Hard reset + full init sequence."""

    # hard reset, then soft reset
    tft.cs(1)
    tft.rst(0)
    time.sleep_ms(50)
    tft.rst(1)
    time.sleep_ms(120)
    tft._cmd(0x01)
    time.sleep_ms(150)

    # controller profile: power, vcom, gamma
    for c, data in SEQ[controller]:
        tft._cmd(c, data)

    # pixel format, orientation, inversion
    tft._cmd(0x3A, b"\x55")  # 16bpp
    tft._cmd(0x36, bytes([ROT[controller][rotation % 4] | (0x08 if bgr else 0)]))
    tft._cmd(0x21 if invert else 0x20)

    # wake up + display on
    tft._cmd(0x11)
    time.sleep_ms(150)
    tft._cmd(0x13)
    tft._cmd(0x29)
    time.sleep_ms(50)
