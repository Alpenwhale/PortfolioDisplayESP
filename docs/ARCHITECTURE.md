# Architecture

How the code is organised and how a price gets onto the screen.

Everything the device shows (display and portal) is English. Number format and currency are settings.

## Layout

```
src/
  main.py          entry: warm boot? -> core.fetch; then core.boot, then setup or run
  config.py        pins, panel, timings
  core/
    app.py         shared state (settings, price arrays), web serving, FLASH button
    boot.py        once per boot: display, pending form, Wi-Fi, mode decision
    fetch.py       fetch phase: prices -> /prices.bin, runs with an empty heap
    reset.py       soft reset from running code
    run.py         normal loop: slideshow, web, button, triggers refresh
    setup.py       setup mode (AP + portal), QR pages, settings address screen
    screens.py     asset page and portfolio total page
  data/
    store.py       settings.json, encrypted secrets, factory reset
    assets.py      /assets.jsonl, one asset per line
    prices.py      /prices.bin, one 32 byte record per asset
  net/
    wifi.py        join Wi-Fi / open AP
    portal.py      http router: static files, login, stores the POST body
    cfg.py         GET /cfg.json
    save.py        applies a stored form at boot
    quotes.py      Yahoo chart endpoint, streamed parser
    search.py      ISIN/WKN -> Yahoo symbol
  ui/
    layout.py      size class, palette, text fitting
    card.py        label / big value / sub lines
    font.py        bitmap fonts read from flash
    fmt.py         number and currency format (de/en)
    qr.py          QR encoder (versions 1-4)
  display/
    base.py        common interface
    tft.py         ILI9341 / ST7789 over SPI, no framebuffer
    tft_init.py    init sequences
    oled.py        SSD1306 over I2C
  fonts/*.bin      built by tools/make_fonts.py
  www/             portal: index.html, saved.html, s.css
tools/             deploy, simulator, screenshots, diagnostics
```

```
main -> core -> ui -> display
          |-> net
          `-> data
```

- `core` decides what happens and which screen is up.
- `ui` decides where things go and in which font size. It only knows the `Display` interface.
- `display` puts pixels on the panel. A new display needs `rgb`, `fill_rect` and `blit_mono`.
- `net` and `data` know nothing about the display.

## Memory model

The whole app runs in about 36 KB of heap. Three rules keep it there:

- **Precompiled.** Everything except `main.py` ships as `.mpy` (`tools/deploy.py`).
- **Load, use, drop.** Modules are imported right before use and unloaded with `core.app.drop()`: drawing code per frame, portal code per request, boot code once.
- **Data stays on flash.** Fonts, HTML and the asset list are read in small pieces. RAM holds four floats and one byte per asset.

| State | free heap |
|---|---|
| fetch phase | ~31 KB |
| applying a saved form | ~30 KB |
| normal loop, idle | ~14 KB |

## Boot

```
main.py
  |- RTC memory starts with "W"?  -> warm boot
  |    `- core.fetch.run(): next batch of assets -> /prices.bin   (display untouched)
  |- core.boot.start()
  |    |- warm: attach the display without init, restore the slideshow position
  |    `- cold: init display, apply /pending.form, "Starting..." (FLASH?), join Wi-Fi,
  |             "Loading prices" + refresh()
  |- setup mode  -> core.setup.run()
  `- normal mode -> core.run.loop()
```

Setup mode starts when FLASH is pressed during `Starting...`, no Wi-Fi is stored, or the Wi-Fi isn't reachable within 20 s.

Any uncaught exception is printed, then the chip resets after 5 s.

## Normal loop

```
every 30 ms:
  app.serve()     one web request, if any
  app.button()    FLASH: short = settings address, 10 s = factory reset
  refresh due?    app.refresh()
  next slide due? advance
  render only on change, then release the drawing code
```

Slides: the portfolio total page first (if enabled), then one page per asset. `single` shows only the first asset. `App.load_assets()` derives `app.total` (0/1) and `app.pages` from the settings.

## Refresh

A TLS connection needs about 20 KB of free heap. The fetch therefore runs in its own phase right after a soft reset, before anything else is loaded.

1. `App.refresh()` stores slideshow position, batch offset and a timestamp in RTC memory and calls `core.reset.soft_reset()`. Nothing is drawn.
2. Only the Python VM restarts. Wi-Fi stays connected and the display keeps its last picture.
3. `main.py` finds the marker and runs `core.fetch.run()`: resolve the symbol once, fetch price and base price, convert the currency, write the record to `/prices.bin`.
4. `core.boot` attaches the display without resetting it, the loop continues with the new prices.

Interval (`run.every()`): the configured one, but at least one full slideshow pass and at least `FREEZE_FACTOR` x the measured freeze.

Limits per refresh: `FETCH_BATCH` assets, `FETCH_MAX_S` seconds, 10 s per request. Assets that can't be resolved are retried only every 12th cycle.

## Prices

`quotes.quote(sym, period)` reads the Yahoo chart endpoint in 256 byte pieces and only parses the `meta` object.

| Period | range / interval | base price |
|---|---|---|
| Day | `1d` / `1d` | previous close |
| Week | `5d` / `1d` | close 5 trading days ago |
| Year to date | `ytd` / `1mo` | close at the end of last year |
| All time | `max` / `3mo` | first open in the history |

- Price and base are converted with today's rate, so the percentage shows the price move only. Rates are fetched after the batch (`fetch._late_fx`): right after a quote there isn't enough RAM for a second TLS handshake.
- ISINs are resolved through the Yahoo search and cached in the asset record (`sym`, `yname`).
- German WKNs become ISINs: `DE000` + WKN + check digit.

## Screens

`screens.py` turns numbers into text, `card.py` places it.

- Headline: change in percent over the period, in the biggest font that fits.
- Sub lines: price with trend arrow, change in money, own performance since purchase (% or amount, optional). Lines that don't fit are dropped.
- Each line comes as a list of variants from long to short, the first one that fits is used.
- Two size classes: small (width < 200 or height < 160) and big. Nothing ever scrolls.
- The portfolio total treats all assets with a quantity as one position, the own performance only those with a buy price. Left-out assets (no values, no exchange rate) put a `*` behind the own performance.
- Brightness: OLED contrast or TFT backlight pin if available, else the palette is darkened.

## Portal

| Request | Result |
|---|---|
| `GET /`, unknown paths | `www/index.html` |
| `GET /s.css` | stylesheet |
| `GET /cfg.json` | settings, asset lines, visible networks. For passwords only whether one is set |
| `POST /save` | body goes to `/pending.form`, then restart |

The form is a static file. A script loads `/cfg.json`, fills the fields and clones one row per asset. Save stays disabled until that worked. The form is sent by script and retried for about a minute while the display is busy; after any portal request the device holds back the next refresh for `WEB_HOLD_S` (a refresh restarts the VM and drops the web server). `net.save.apply_pending()` applies the stored form at the next boot, row by row.

## Storage

| File | Content | Factory reset |
|---|---|---|
| `/settings.json` | `ssid`, `show_total`, `show_assets`, `single`, `show_gain`, `gain`, `period`, `numfmt`, `cur`, `slide_s`, `total_s`, `fetch_s`, `bright` | removed |
| `/assets.jsonl` | per line: `id`, `ex`, `name`, `qty`, `buy`, `sym`, `yname` | removed |
| `/prices.bin` | per asset: price, base (f32), valid flag, currency, last error | removed |
| `/secret.bin` | AES: Wi-Fi password, salted hash of the page password | removed |
| `/ap.key` | AES: setup Wi-Fi password | kept |
| `/pending.form` | raw form body between save and restart | |

Files are written to `.tmp` and renamed. Secrets use AES-256-CBC with a key derived from the chip id: the files are useless on another device, but there is no protection against someone with USB access.

## Tools

| File | Purpose |
|---|---|
| `deploy.py` | compile, clean up the board, upload, restart |
| `mpr.py` | `mpremote` wrapper that keeps DTR/RTS low (otherwise the board stays in reset) |
| `sim.py` | renders all screens with the real ui code into `docs/img/` and checks the QR codes |
| `portal_shots.py` | screenshots of the real portal page with example data |
| `make_fonts.py` | TTF -> bitmap fonts |
| `diag/` | display diagnostics and a screenshot tool for the real panel |
