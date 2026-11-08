"""SSD1306 adapter. Needs: mpremote connect COM4 mip install ssd1306"""
import ssd1306
from machine import SoftI2C
from display.base import Display


class OLED(Display):
    """Mono OLED over I2C, buffered."""

    def __init__(self, i2c: SoftI2C, width: int = 128, height: int = 64) -> None:
        """Wrap the ssd1306 driver."""
        self.width, self.height = width, height
        self.dev = ssd1306.SSD1306_I2C(width, height, i2c)

    def rgb(self, r: int, g: int, b: int) -> int:
        """Anything non-black is on."""
        return 1 if (r + g + b) > 0 else 0

    def fill(self, color: int) -> None:
        """Fill whole screen."""
        self.dev.fill(color)

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        """Fill a rectangle."""
        self.dev.fill_rect(x, y, w, h, color)

    def text(self, s: str, x: int, y: int, color: int, bg: int = 0, scale: int = 1) -> None:
        """Draw 8x8 text. scale/bg ignored."""
        self.dev.text(s, x, y, color)

    def show(self) -> None:
        """Push buffer to the panel."""
        self.dev.show()
