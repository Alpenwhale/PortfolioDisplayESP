"""Hardware config. Pins are GPIO numbers, not D-labels."""

DISPLAY: str = "ili9341"  # or "ssd1306"

# ILI9341, HSPI is fixed: SCK=14, MOSI=13, MISO=12
TFT_CS = None        # module has no CS pin, tied low on board
TFT_DC: int = 4      # D2
TFT_RST: int = 5     # D1
TFT_ROTATION: int = 1  # odd = landscape
TFT_SPI_BAUD: int = 40_000_000
TFT_SPI_MODE: int = 3  # no-CS modules want mode 3

# SSD1306, later
OLED_SCL: int = 5    # D1
OLED_SDA: int = 4    # D2
OLED_WIDTH: int = 128
OLED_HEIGHT: int = 64
