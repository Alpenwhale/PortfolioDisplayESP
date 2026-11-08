"""Display factory."""
from display.base import Display


def create_display(cfg) -> Display:
    """Build the display picked in cfg.DISPLAY."""
    if cfg.DISPLAY == "ili9341":
        from machine import Pin, SPI
        from display.ili9341 import ILI9341

        mode = cfg.TFT_SPI_MODE
        spi = SPI(1, baudrate=cfg.TFT_SPI_BAUD, polarity=mode >> 1, phase=mode & 1)
        cs = Pin(cfg.TFT_CS, Pin.OUT) if cfg.TFT_CS is not None else None
        return ILI9341(spi, cs, Pin(cfg.TFT_DC, Pin.OUT),
                       Pin(cfg.TFT_RST, Pin.OUT), rotation=cfg.TFT_ROTATION)

    if cfg.DISPLAY == "ssd1306":
        from machine import Pin, SoftI2C
        from display.oled import OLED

        i2c = SoftI2C(scl=Pin(cfg.OLED_SCL), sda=Pin(cfg.OLED_SDA))
        return OLED(i2c, cfg.OLED_WIDTH, cfg.OLED_HEIGHT)

    raise ValueError("unknown display: " + cfg.DISPLAY)
