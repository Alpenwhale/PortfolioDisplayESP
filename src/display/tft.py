"""Generic SPI TFT driver (MIPI-DCS style: ILI9341, ST7789, ...), no framebuffer."""
# full fb = 150 KB, ESP8266 has ~40 KB. so we write straight to the panel.
import time
import framebuf
from machine import Pin, SPI
from display.base import Display

# MADCTL rotation bits per controller (BGR added separately)
_ROT = {
    "ili9341": (0x40, 0x20, 0x80, 0xE0),
    "st7789": (0x00, 0x60, 0xC0, 0xA0),
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
    """SPI TFT, RGB565. Panel specifics come from config."""

    def __init__(self, spi: SPI, dc: Pin, rst: Pin, cs: Pin | None = None,
                 width: int = 240, height: int = 320, x_offset: int = 0, y_offset: int = 0,
                 rotation: int = 0, controller: str = "ili9341",
                 invert: bool = False, bgr: bool = True) -> None:
        """Reset and init. width/height = native portrait size."""
        self.spi, self.dc, self.rst = spi, dc, rst
        self.cs = cs if cs is not None else (lambda v: None)

        # logical size + ram offsets follow the rotation
        landscape = rotation % 2 == 1
        self.width, self.height = (height, width) if landscape else (width, height)
        self._xo, self._yo = (y_offset, x_offset) if landscape else (x_offset, y_offset)

        # hard reset, then soft reset
        self.cs(1)
        self.rst(0)
        time.sleep_ms(50)
        self.rst(1)
        time.sleep_ms(120)
        self._cmd(0x01)
        time.sleep_ms(150)

        # controller profile: power, vcom, gamma
        for c, data in _INIT[controller]:
            self._cmd(c, data)

        # pixel format, orientation, inversion
        self._cmd(0x3A, b"\x55")  # 16bpp
        self._cmd(0x36, bytes([_ROT[controller][rotation % 4] | (0x08 if bgr else 0)]))
        self._cmd(0x21 if invert else 0x20)

        # wake up + display on
        self._cmd(0x11)
        time.sleep_ms(150)
        self._cmd(0x13)
        self._cmd(0x29)
        time.sleep_ms(50)

        # 2-color palette + one scratch buffer for all drawing, allocated once while the heap is clean
        self._pal = framebuf.FrameBuffer(bytearray(4), 2, 1, framebuf.RGB565)
        self._mv = memoryview(bytearray(512))

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
        x, y = x + self._xo, y + self._yo
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

        # clip to screen
        x, y = max(0, x), max(0, y)
        w, h = min(w, self.width - x), min(h, self.height - y)
        if w <= 0 or h <= 0:
            return

        # fill the scratch buffer with the color by doubling (no allocation)
        mv = self._mv
        mv[0], mv[1] = color >> 8, color & 0xFF
        n = 2
        while n < len(mv):
            mv[n:2 * n] = mv[:n]
            n *= 2

        # stream it over and over
        self._window(x, y, w, h)
        total = w * h * 2
        self.cs(0)
        self.dc(1)
        while total > 0:
            n = min(total, len(mv))
            self.spi.write(mv[:n])
            total -= n
        self.cs(1)

    def blit_mono(self, buf: bytearray, w: int, h: int, x: int, y: int, fg: int, bg: int) -> None:
        """Expand 1-bit to RGB565 via framebuf palette (C speed), in bands through the scratch buffer."""

        # framebuf stores RGB565 little endian, panel wants big endian -> swap
        self._pal.pixel(0, 0, ((bg & 0xFF) << 8) | (bg >> 8))
        self._pal.pixel(1, 0, ((fg & 0xFF) << 8) | (fg >> 8))

        # as many rows per band as fit the scratch buffer; a 60 px digit no longer needs 4 KB at once
        rb = (w + 7) // 8
        band = max(1, len(self._mv) // (w * 2))
        src = memoryview(buf)
        for y0 in range(0, h, band):
            bh = min(band, h - y0)
            out = self._mv[:w * bh * 2]
            framebuf.FrameBuffer(out, w, bh, framebuf.RGB565).blit(
                framebuf.FrameBuffer(src[y0 * rb:(y0 + bh) * rb], w, bh, framebuf.MONO_HLSB), 0, 0, -1, self._pal)
            self._blit(x, y + y0, w, bh, out)
