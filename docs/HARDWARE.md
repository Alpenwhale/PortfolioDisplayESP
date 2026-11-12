# Hardware

Supported boards and displays, wiring, and the matching settings in `src/config.py`.

## Combinations

| Board | 2.8" TFT ILI9341 (SPI) | ST7789 TFT (SPI) | 0.96" OLED SSD1306 (I2C) |
|---|---|---|---|
| NodeMCU v3 dev board (ESP-12F, USB-C) | tested | supported | supported |
| Wemos/LOLIN D1 mini | supported | supported | supported |
| bare ESP-12E/F module | supported | supported | supported |
| ESP32 DevKit | small change | small change | small change |

- **tested**: runs on real hardware. Reference: NodeMCU v3 development board with USB-C and CH340 + 2.8" ILI9341 240x320 module without CS pin, MicroPython 1.29.
- **supported**: covered by the code, not yet run on hardware.
- **ESP32**: needs the ESP32 firmware and `make_spi()` in `display/__init__.py` has to pass the pins (`SPI(1, sck=..., mosi=...)`).
- Not supported: SH1106 OLEDs (different driver), 128x32 OLEDs (too low), parallel displays, ESP-01.

## The board

The reference build uses a **NodeMCU v3 development board**, not a bare ESP8266. On the board the ESP8266 sits on an ESP-12F module with 4 MB flash and the antenna; the board adds a USB-C socket, a CH340 USB-to-serial chip, a 5 V to 3.3 V regulator, the RST and FLASH buttons and pin headers. Power and flashing both go through one USB-C cable.

| | Development board (NodeMCU v3) | Bare module (ESP-12F) |
|---|---|---|
| Power | USB-C, regulator on board | own 3.3 V supply |
| Flashing | same USB-C cable | separate USB-to-serial adapter |
| Buttons | RST + FLASH on board | to be added |
| Connecting | jumper wires on pin headers | soldering |
| Size | about 58 x 31 mm | about 24 x 16 mm |
| Power draw | USB chip, regulator and LED draw extra | lower |
| Quirk | the USB chip can hold the ESP8266 in reset, see `tools/mpr.py` | none |

## ESP8266 pins

`config.py` always uses GPIO numbers, not the D labels.

| GPIO | Label | Note |
|---|---|---|
| 16 | D0 | no PWM, no I2C |
| 5 | D1 | free |
| 4 | D2 | free |
| 0 | D3 | FLASH button, must be high at boot |
| 2 | D4 | board LED, must be high at boot |
| 14 | D5 | SPI clock (fixed) |
| 12 | D6 | SPI MISO (fixed) |
| 13 | D7 | SPI MOSI (fixed) |
| 15 | D8 | must be low at boot |
| 1, 3 | TX, RX | USB serial, don't use |
| 6-11 | | internal flash, never use |

NodeMCU boards have two buttons next to the USB port: **RST** and **FLASH** (sometimes **BOOT**). A D1 mini only has RST; add a push button from D3 to GND.

Power: the board runs from USB-C; its 3V3 pin feeds the display and backlight without problems.

## TFT over SPI (ILI9341 / ST7789)

| Display pin | GPIO | Label | `config.py` |
|---|---|---|---|
| VCC | | 3V3 | |
| GND | | G | |
| CLK / SCK / SCL | 14 | D5 | `TFT_SCK` |
| MOSI / SDA | 13 | D7 | `TFT_MOSI` |
| MISO / SDO | 12 | D6 | `TFT_MISO`, optional, only for `tools/diag` |
| RES / RST | 5 | D1 | `TFT_RST` |
| DC / RS / A0 | 4 | D2 | `TFT_DC` |
| CS | 15 | D8 | `TFT_CS`, `None` for modules without CS |
| BLK / LED | | 3V3 | `TFT_BL = None` |

```python
DISPLAY = "tft"
TFT_CONTROLLER = "ili9341"   # or "st7789"
TFT_WIDTH, TFT_HEIGHT = 240, 320   # native portrait size
TFT_ROTATION = 1             # 1/3 = landscape
TFT_SPI_MODE = 3             # modules without CS need 3, with CS usually 0
TFT_SPI_BAUD = 20_000_000    # not higher on jumper wires
```

| Panel | Controller | Size | Settings |
|---|---|---|---|
| 2.4" / 2.8" / 3.2" | ILI9341 | 240x320 | `TFT_BGR = True` |
| 2.0" IPS | ST7789 | 240x320 | `TFT_INVERT = True`, `TFT_BGR = False` |
| 1.3" / 1.54" IPS | ST7789 | 240x240 | `TFT_HEIGHT = 240`, `TFT_INVERT = True` |
| 1.14" IPS | ST7789 | 135x240 | `TFT_X_OFFSET = 52`, `TFT_Y_OFFSET = 40` |

**Brightness.** With BLK on 3V3 the backlight is always fully on, and the brightness setting darkens the colors instead. For real dimming connect BLK to a PWM pin (e.g. D4) and set `TFT_BL = 2`. The backlight path is not yet tested on hardware.

**White screen** means the controller is not initialised: CLK/MOSI swapped, VCC missing, or the ESP is held in reset. Check with `tools/diag/bus_check.py`, then `probe.py`, then `stages.py` (see [SETUP.md](SETUP.md)).

## OLED over I2C (SSD1306, 128x64)

| OLED pin | GPIO | Label | `config.py` |
|---|---|---|---|
| VCC | | 3V3 | |
| GND | | G | |
| SCL | 5 | D1 | `OLED_SCL` |
| SDA | 4 | D2 | `OLED_SDA` |

```python
DISPLAY = "ssd1306"
OLED_WIDTH, OLED_HEIGHT = 128, 64
```

Install the driver once (it lands in `/lib`, which `deploy.py` leaves alone):

```bash
uv run tools/mpr.py connect COM4 mip install ssd1306
```

D1/D2 are also RES/DC of the TFT, so only one display can be connected at a time. The brightness setting controls the OLED contrast.
