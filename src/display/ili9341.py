"""Minimal ILI9341 driver, no framebuffer."""
# full fb = 150 KB, ESP8266 has ~40 KB. so we write straight to the panel.
import time
import framebuf
from machine import Pin, SPI
from display.base import Display

_MADCTL = (0x48, 0x28, 0x88, 0xE8)  # rot 0..3, BGR


class ILI9341(Display):
    """ILI9341 over SPI, RGB565."""

    def __init__(self, spi: SPI, cs: Pin, dc: Pin, rst: Pin, rotation: int = 0) -> None:
        """Reset and init the panel."""
        self.spi, self.cs, self.dc, self.rst = spi, cs, dc, rst
        self.width, self.height = (240, 320) if rotation % 2 == 0 else (320, 240)
        self.cs(1)
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(120)
        self._cmd(0x01)  # swreset
        time.sleep_ms(150)
        self._cmd(0x11)  # sleep out
        time.sleep_ms(120)
        self._cmd(0x3A, b"\x55")  # 16bpp
        self._cmd(0x36, bytes([_MADCTL[rotation % 4]]))
        self._cmd(0x29)  # on
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
