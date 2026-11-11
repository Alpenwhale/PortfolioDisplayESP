# Setup

- **Part A**: using the device. All you need is a phone.
- **Part B**: flashing and development. Needs a PC with USB.

Wiring: [HARDWARE.md](HARDWARE.md). Code: [ARCHITECTURE.md](ARCHITECTURE.md).

The display images are rendered by the real display code (`tools/sim.py`), left the 0.96" OLED, right the 2.8" TFT. The portal images show the real page (`tools/portal_shots.py`). All data is made up.

# Part A: using the device

## A1. First start

1. Power the device over USB. It shows `Starting...`, then the setup screen.
2. Scan the QR code **Scan to join Wi-Fi**. The phone joins `Portfolio-XXXX`. The password is fixed per device and also shown as text.
3. Scan **Scan to open setup** or open `http://192.168.4.1`.

   | | 0.96" OLED (pages rotate every 5 s) | 2.8" TFT |
   |---|---|---|
   | join Wi-Fi | <img src="img/128x64/setup0.png" width="256"> | <img src="img/320x240/setup0.png" width="320"> |
   | open page | <img src="img/128x64/setup1.png" width="256"> | |
   | as text | <img src="img/128x64/setup2.png" width="256"> | |

4. Fill in the page (A2) and press **Save**.
5. The device restarts, joins your Wi-Fi, loads the prices and shows the address of the settings page for 10 s. Then the slideshow starts.

Every save restarts the device (about 15 s). If the phone stays in the same Wi-Fi, the page reloads by itself.

## A2. The settings page

| First setup | Configured |
|---|---|
| <img src="img/portal/1_first_setup.png" width="300"> | <img src="img/portal/2_configured.png" width="300"> |

**Wi-Fi**

<img src="img/portal/wifi.png" width="300">

| Field | Meaning |
|---|---|
| Network | your Wi-Fi, networks in range are suggested |
| Password | never shown again. Empty = keep the stored one |

**Display**

<img src="img/portal/display.png" width="300">

| Field | Meaning |
|---|---|
| show total portfolio performance | adds a page with the total of all assets that have a quantity |
| show each asset in the slideshow | one page per asset |
| show only the first asset | static, no slideshow. Overrides the two switches above |
| show own performance since purchase | adds the "Since purchase" line (default on) |
| Own performance as | percent or amount in money |
| Show change over | day / week / year to date / all time. Applies to every page |
| Number format | German `1.234,56 €` (default) or English `€1,234.56` |
| Currency | display currency (default EUR), converted at today's rate |
| Asset slide time / Total slide time | seconds per asset page / for the total page |
| Refresh prices every | seconds, at least 60 |
| Brightness | 10-100 % |

**Assets** (up to 50)

<img src="img/portal/assets.png" width="300">

| Field | Example | Note |
|---|---|---|
| Identifier | `IE00B4L5Y983`, `AAPL`, `716460` | ISIN works best. WKN only for German securities. After the first refresh the resolved symbol is shown, e.g. `→ EUNL.DE` |
| Exchange | Xetra, NYSE/Nasdaq, London, ... | `Automatic` prefers Xetra |
| Description | `MSCI World` | optional, default is the name from Yahoo |
| Quantity / Buy price | `10` / `80,50` | optional. Quantity is needed for the total page and the amount, the buy price for "Since purchase". Buy price in the display currency |

**+ Add asset** adds a row, **×** removes it. Comma and point both work in numbers.

**Security**

<img src="img/portal/security.png" width="300">

| Field | Meaning |
|---|---|
| Password for this page | optional protection in your home network |
| new setup Wi-Fi password | rolls a new password for the setup Wi-Fi. Normally it never changes |

Phone keyboards don't learn or suggest anything on this page (`autocomplete`, `autocorrect`, `spellcheck` off).

## A3. The FLASH button

FLASH (sometimes labelled BOOT) is one of the two small buttons next to the USB port. The other one is RST (restart).

| What | How |
|---|---|
| show the settings address (QR + IP, 10 s) | short press |
| setup mode, page open without password | press RST, then press FLASH while `Starting...` is shown |
| factory reset | hold FLASH for 10 s. A countdown starts after 2 s, releasing cancels |

| | 0.96" OLED | 2.8" TFT |
|---|---|---|
| settings address | <img src="img/128x64/info0.png" width="256"> | <img src="img/320x240/info0.png" width="320"> |
| factory reset | <img src="img/128x64/reset.png" width="256"> | <img src="img/320x240/reset.png" width="320"> |

Don't hold FLASH while plugging in, the chip then waits for a firmware upload. Press RST to get out.

A factory reset clears Wi-Fi, assets and the page password. The setup Wi-Fi password stays.

## A4. Forgot a password?

| Password | Fix |
|---|---|
| settings page | force setup mode (A3), the page is open there |
| home Wi-Fi changed | after 20 s without Wi-Fi the device enters setup mode by itself |
| setup Wi-Fi | shown on the display in setup mode |

## A5. What the display shows

Asset and total page look the same:

1. name (or `Portfolio`)
2. change in percent over the chosen period, green = up, red = down
3. price (total: value of all holdings) with a trend arrow
4. change in money over the period
5. own performance since purchase, in percent or as amount (can be switched off)

The OLED only fits lines 1-3. Dots at the bottom mark the slideshow position.

The total page adds up all assets that have a quantity; the own performance uses those that also have a buy price. Assets without these values are left out, and a `*` behind the own performance shows that something was left out.

| | 0.96" OLED | 2.8" TFT |
|---|---|---|
| asset, up | <img src="img/128x64/asset0.png" width="256"> | <img src="img/320x240/asset0.png" width="320"> |
| asset, down | <img src="img/128x64/asset1.png" width="256"> | <img src="img/320x240/asset1.png" width="320"> |
| portfolio total | <img src="img/128x64/total.png" width="256"> | <img src="img/320x240/total.png" width="320"> |
| own performance as amount | | <img src="img/320x240/total_abs.png" width="320"> |
| own performance off | | <img src="img/320x240/asset0_nogain.png" width="320"> |
| only the first asset | <img src="img/128x64/single.png" width="256"> | <img src="img/320x240/single.png" width="320"> |
| English number format | <img src="img/128x64/asset1_en.png" width="256"> | <img src="img/320x240/asset1_en.png" width="320"> |
| brightness 40 % | | <img src="img/320x240/dimmed.png" width="320"> |
| identifier not found | <img src="img/128x64/asset2.png" width="256"> | <img src="img/320x240/asset2.png" width="320"> |

Messages:

- `Loading...`: the first refresh is still running.
- `HTTP 404`, `not found`, `not on this exchange`: check identifier and exchange.
- `WKN: use the ISIN`: WKNs only resolve for German securities.

**Refresh.** When a refresh is due, the picture stands still for a few seconds (about 9 s with 2 assets, 2-3 s per further asset, 10 assets per refresh) and then continues with new prices. A refresh never comes before every slide was shown once, and the device stretches short intervals so that the picture moves at least 80 % of the time.

# Part B: flashing and development

## B1. Requirements

- USB driver for the board's serial chip (CH340 or CP2102). The port shows up as `COMx`.
- [uv](https://docs.astral.sh/uv/). It installs the right Python version itself.
- MicroPython firmware for the ESP8266 from <https://micropython.org/download/ESP8266_GENERIC/>, put the `.bin` into the project folder.

```bash
uv sync
```

## B2. Flash the firmware (once per board)

```bash
uv run esptool --port COM4 erase-flash
```

```bash
uv run esptool --port COM4 --baud 460800 write-flash --flash-size=detect 0 ESP8266_GENERIC-20260824-v1.29.0.bin
```

`erase-flash` also removes all settings and the setup Wi-Fi password.

## B3. Configure and deploy

1. Adjust `src/config.py` to your hardware, see [HARDWARE.md](HARDWARE.md).
2. OLED only, once:
   ```bash
   uv run tools/mpr.py connect COM4 mip install ssd1306
   ```
3. Deploy:
   ```bash
   uv run tools/deploy.py COM4
   ```
   Compiles everything to `.mpy`, removes stale code from the board (settings stay), uploads and restarts.

Always use `tools/mpr.py` instead of plain `mpremote`. On these boards plain `mpremote` holds the ESP in reset (`could not enter raw repl`).

## B4. Tools

| Command | Purpose |
|---|---|
| `uv run tools/sim.py` | render every screen on the PC into `docs/img/<size>/` |
| `uv run tools/portal_shots.py` | screenshots of the settings page into `docs/img/portal/` (needs Edge or Chrome) |
| `uv run tools/make_fonts.py` | rebuild the fonts |
| `uv run tools/mpr.py connect COM4 repl` | console of the board, shows the device log |
| `uv run tools/mpr.py connect COM4 ls` | files on the board |

## B5. Display diagnostics

Each script explains in its header what to expect. Run them in this order:

```bash
uv run tools/mpr.py connect COM4 run tools/diag/bus_check.py
```

Does the controller answer? Needs MISO, no need to look at the screen.

```bash
uv run tools/mpr.py connect COM4 run tools/diag/probe.py
```

Which controller and SPI mode fit? The variant with a clean digit on red is the right one.

```bash
uv run tools/mpr.py connect COM4 run tools/diag/stages.py
```

Which layer loses the picture (init, hardware SPI, speed)?

Screenshot of the real panel (reads its video memory, needs MISO):

```bash
uv run tools/diag/screenshot.py COM4 --wait 45 --out shot.png
```
