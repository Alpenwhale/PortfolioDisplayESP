"""Generic SPI TFT driver (MIPI-DCS style: ILI9341, ST7789, ...), no framebuffer."""
# full fb = 150 KB, ESP8266 has ~40 KB. so we write straight to the panel.
# init tables live in display.tft_init, loaded only for a real (re)init.
import framebuf
from machine import Pin, SPI
from display.base import Display


class TFT(Display):
    """SPI TFT, RGB565. Panel specifics come from config."""

    def __init__(self, spi: SPI, dc: Pin, rst: Pin, cs: Pin | None = None,
                 width: int = 240, height: int = 320, x_offset: int = 0, y_offset: int = 0,
                 rotation: int = 0, controller: str = "ili9341",
                 invert: bool = False, bgr: bool = True, init: bool = True, bl=None) -> None:
        """Reset + init (init=False: just attach, panel keeps its image). width/height = native portrait."""
        self.spi, self.dc, self.rst, self.bl = spi, dc, rst, bl
        self.cs = cs if cs is not None else (lambda v: None)

        # logical size + ram offsets follow the rotation
        landscape = rotation % 2 == 1
        self.width, self.height = (height, width) if landscape else (width, height)
        self._xo, self._yo = (y_offset, x_offset) if landscape else (x_offset, y_offset)

        # full panel init only at boot
        if init:
            import sys
            from display import tft_init
            tft_init.run(self, controller, rotation, invert, bgr)
            del tft_init
            sys.modules.pop("display.tft_init", None)
            sys.modules["display"].__dict__.pop("tft_init", None)

        # 2-color palette + one scratch buffer for all drawing
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

    def brightness(self, pct: int) -> bool:
        """Backlight PWM, only if BLK hangs on a pin (config.TFT_BL)."""
        if self.bl is None:
            return False
        from machine import PWM
        PWM(Pin(self.bl), freq=1000, duty=pct * 1023 // 100)
        return True

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
