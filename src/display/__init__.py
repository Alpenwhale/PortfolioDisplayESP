"""Display factory. Drivers only, no layout here."""
from display.base import Display


def make_spi(cfg, soft: bool = False, baud: int = 0):
    """SPI bus for the TFT. soft=True forces SoftSPI (diag)."""
    from machine import Pin, SPI, SoftSPI

    # mode 0..3 -> polarity/phase bits
    baud = baud or cfg.TFT_SPI_BAUD
    pol, pha = cfg.TFT_SPI_MODE >> 1, cfg.TFT_SPI_MODE & 1

    # bitbang on any pins, or the fixed hardware SPI
    if soft or cfg.TFT_SPI_ID < 0:
        return SoftSPI(baudrate=baud, polarity=pol, phase=pha, sck=Pin(cfg.TFT_SCK),
                       mosi=Pin(cfg.TFT_MOSI), miso=Pin(cfg.TFT_MISO))
    return SPI(cfg.TFT_SPI_ID, baudrate=baud, polarity=pol, phase=pha)


def create_display(cfg, init: bool = True) -> Display:
    """Build the display picked in cfg.DISPLAY. init=False re-attaches a TFT without touching the panel."""

    # SPI TFT (ili9341 / st7789)
    if cfg.DISPLAY == "tft":
        from machine import Pin
        from display.tft import TFT

        cs = Pin(cfg.TFT_CS, Pin.OUT) if cfg.TFT_CS is not None else None
        return TFT(make_spi(cfg), Pin(cfg.TFT_DC, Pin.OUT), Pin(cfg.TFT_RST, Pin.OUT), cs=cs,
                   width=cfg.TFT_WIDTH, height=cfg.TFT_HEIGHT,
                   x_offset=cfg.TFT_X_OFFSET, y_offset=cfg.TFT_Y_OFFSET,
                   rotation=cfg.TFT_ROTATION, controller=cfg.TFT_CONTROLLER,
                   invert=cfg.TFT_INVERT, bgr=cfg.TFT_BGR, init=init)

    # I2C OLED (0.96" 128x64)
    if cfg.DISPLAY == "ssd1306":
        from machine import Pin, SoftI2C
        from display.oled import OLED

        i2c = SoftI2C(scl=Pin(cfg.OLED_SCL), sda=Pin(cfg.OLED_SDA))
        return OLED(i2c, cfg.OLED_WIDTH, cfg.OLED_HEIGHT)

    raise ValueError("unknown display: " + cfg.DISPLAY)
