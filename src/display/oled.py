"""SSD1306 adapter. Needs: uv run tools/mpr.py connect COM4 mip install ssd1306"""
import framebuf
import ssd1306
from machine import SoftI2C
from display.base import Display


class OLED(Display):
    """Mono OLED over I2C, buffered."""

    mono = True

    def __init__(self, i2c: SoftI2C, width: int = 128, height: int = 64) -> None:
        """Wrap the ssd1306 driver."""
        self.width, self.height = width, height
        self.dev = ssd1306.SSD1306_I2C(width, height, i2c)

    def rgb(self, r: int, g: int, b: int) -> int:
        """Anything brighter than dark gray is on."""
        return 1 if (r + g + b) > 120 else 0

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        """Fill a rectangle."""
        self.dev.fill_rect(x, y, w, h, color)

    def blit_mono(self, buf: bytearray, w: int, h: int, x: int, y: int, fg: int, bg: int) -> None:
        """Bg box, then glyph with 0 as transparent key."""
        self.dev.fill_rect(x, y, w, h, bg)
        if fg:
            self.dev.blit(framebuf.FrameBuffer(buf, w, h, framebuf.MONO_HLSB), x, y, 0)

    def show(self) -> None:
        """Push buffer to the panel."""
        self.dev.show()
