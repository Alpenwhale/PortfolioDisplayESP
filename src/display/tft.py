"""Minimal SPI TFT driver for ILI9341 / ST7789, no framebuffer."""
# full fb = 150 KB, ESP8266 has ~40 KB. so we write straight to the panel.
import time
import framebuf
from machine import Pin, SPI
from display.base import Display

# MADCTL per rotation 0..3
_MADCTL = {
    "ili9341": (0x48, 0x28, 0x88, 0xE8),  # BGR
    "st7789": (0x00, 0x60, 0xC0, 0xA0),   # RGB
}

# power/vcom/gamma. minimal init leaves some panels black.
_INIT = {
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


class TFT(Display):
    """240x320 SPI TFT, RGB565."""

    def __init__(self, spi: SPI, cs: Pin | None, dc: Pin, rst: Pin,
                 rotation: int = 0, controller: str = "ili9341") -> None:
        """Reset and init the panel. cs=None for modules without CS."""
        self.spi, self.dc, self.rst = spi, dc, rst
        self.cs = cs if cs is not None else (lambda v: None)
        self.width, self.height = (240, 320) if rotation % 2 == 0 else (320, 240)
        self.cs(1)
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(120)
        self._cmd(0x01)  # swreset
        time.sleep_ms(150)
        for c, data in _INIT[controller]:
            self._cmd(c, data)
        self._cmd(0x3A, b"\x55")  # 16bpp
        self._cmd(0x36, bytes([_MADCTL[controller][rotation % 4]]))
        if controller == "st7789":
            self._cmd(0x21)  # st7789 panels are usually inverted
        self._cmd(0x11)  # sleep out
        time.sleep_ms(150)
        self._cmd(0x13)  # normal mode
        self._cmd(0x29)  # on
        time.sleep_ms(50)
        self._glyph = framebuf.FrameBuffer(bytearray(8), 8, 8, framebuf.MONO_HLSB)

    def _cmd(self, c: int, data: bytes = None) -> None:
        """Send command plus optional data."""
        self.cs(0)
        self.dc(0)
        self.spi.write(bytes([c]))
        if data:
            self.dc(1)
            self.spi.write(data)
        self.cs(1)

    def _window(self, x: int, y: int, w: int, h: int) -> None:
        """Set draw window and start RAM write."""
        x1, y1 = x + w - 1, y + h - 1
        self._cmd(0x2A, bytes([x >> 8, x & 0xFF, x1 >> 8, x1 & 0xFF]))
        self._cmd(0x2B, bytes([y >> 8, y & 0xFF, y1 >> 8, y1 & 0xFF]))
        self._cmd(0x2C)

    def _blit(self, x: int, y: int, w: int, h: int, buf: bytearray) -> None:
        """Push raw RGB565 (big endian) into a window."""
        self._window(x, y, w, h)
        self.cs(0)
        self.dc(1)
        self.spi.write(buf)
        self.cs(1)

    def rgb(self, r: int, g: int, b: int) -> int:
        """8-bit RGB to RGB565."""
        return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        """Fill a clipped rectangle."""
        x, y = max(0, x), max(0, y)
        w, h = min(w, self.width - x), min(h, self.height - y)
        if w <= 0 or h <= 0:
            return
        self._window(x, y, w, h)
        chunk = bytes([color >> 8, color & 0xFF]) * 256
        total = w * h * 2
        self.cs(0)
        self.dc(1)
        while total > 0:
            n = min(total, len(chunk))
            self.spi.write(chunk if n == len(chunk) else chunk[:n])
            total -= n
        self.cs(1)

    def text(self, s: str, x: int, y: int, color: int, bg: int = 0, scale: int = 1) -> None:
        """Draw text char by char, scaled. Cuts off at right edge."""
        size = 8 * scale
        buf = bytearray(size * size * 2)
        fg = bytes([color >> 8, color & 0xFF])
        bk = bytes([bg >> 8, bg & 0xFF])
        g = self._glyph
        for ch in s:
            if x + size > self.width:
                break
            g.fill(0)
            g.text(ch, 0, 0, 1)
            i = 0
            for row in range(8):
                line = bytearray()
                for col in range(8):
                    line += (fg if g.pixel(col, row) else bk) * scale
                for _ in range(scale):
                    buf[i:i + len(line)] = line
                    i += len(line)
            self._blit(x, y, size, size, buf)
            x += size
