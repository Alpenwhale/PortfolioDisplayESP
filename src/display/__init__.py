"""Display factory."""
from display.base import Display


def create_display(cfg) -> Display:
    """Build the display picked in cfg.DISPLAY."""
    if cfg.DISPLAY in ("ili9341", "st7789"):
        from machine import Pin, SPI
        from display.tft import TFT

        mode = cfg.TFT_SPI_MODE
        spi = SPI(1, baudrate=cfg.TFT_SPI_BAUD, polarity=mode >> 1, phase=mode & 1)
        cs = Pin(cfg.TFT_CS, Pin.OUT) if cfg.TFT_CS is not None else None
        return TFT(spi, cs, Pin(cfg.TFT_DC, Pin.OUT), Pin(cfg.TFT_RST, Pin.OUT),
                   rotation=cfg.TFT_ROTATION, controller=cfg.DISPLAY)

    if cfg.DISPLAY == "ssd1306":
        from machine import Pin, SoftI2C
        from display.oled import OLED

        i2c = SoftI2C(scl=Pin(cfg.OLED_SCL), sda=Pin(cfg.OLED_SDA))
        return OLED(i2c, cfg.OLED_WIDTH, cfg.OLED_HEIGHT)

    raise ValueError("unknown display: " + cfg.DISPLAY)
