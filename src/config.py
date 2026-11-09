"""Hardware + app constants. Pins are GPIO numbers, not D-labels."""

DISPLAY: str = "tft"  # "tft" | "ssd1306"

# --- TFT (SPI) ---
TFT_CONTROLLER: str = "ili9341"  # "ili9341" | "st7789"
TFT_WIDTH: int = 240    # native portrait size
TFT_HEIGHT: int = 320
TFT_X_OFFSET: int = 0   # some small st7789 panels need this (e.g. 135x240: 52/40)
TFT_Y_OFFSET: int = 0
TFT_ROTATION: int = 1   # odd = landscape
TFT_INVERT: bool = False  # IPS st7789 usually True
TFT_BGR: bool = True      # swap if red/blue are flipped

TFT_SPI_ID: int = 1     # 1 = ESP8266 HSPI (fixed pins below), -1 = SoftSPI
TFT_SPI_BAUD: int = 20_000_000  # 40M too flaky on dupont wires
TFT_SPI_MODE: int = 3   # 0 or 3, no-CS modules want 3
TFT_SCK: int = 14       # D5
TFT_MOSI: int = 13      # D7
TFT_MISO: int = 12      # D6, only diag reads it
TFT_CS = None           # None = tied low on module
TFT_DC: int = 4         # D2
TFT_RST: int = 5        # D1

# --- SSD1306 OLED (I2C), 0.96" = 128x64 ---
OLED_SCL: int = 5       # D1
OLED_SDA: int = 4       # D2
OLED_WIDTH: int = 128
OLED_HEIGHT: int = 64

# --- app ---
BUTTON_PIN: int = 0         # FLASH button
AP_PREFIX: str = "Portfolio"  # setup wifi = Portfolio-XXXX, short enough for 128 px
WIFI_TIMEOUT_S: int = 20
SETUP_IDLE_S: int = 600     # setup AP reboots after this idle time to retry wifi
INFO_S: int = 10            # short FLASH press: show settings url this long
RESET_HOLD_S: int = 10      # FLASH held this long = factory reset
PAGE_S: int = 5             # small screens: setup/info pages rotate this fast
