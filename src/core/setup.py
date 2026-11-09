"""Setup mode (WPA2 AP + portal) and the 'where are my settings' info screen.

Both show QR codes so a phone can join/open without typing. Small screens get rotating
pages (QR wifi, QR url, plain text), big screens get everything at once.
Imported only when needed, then unloaded.
"""
import gc
import sys
import time

import config
from net import wifi


def _qr(text: str) -> tuple:
    """Encode, then drop the encoder module again."""
    from ui import qr
    try:
        return qr.encode(text)
    finally:
        sys.modules.pop("ui.qr", None)
        gc.collect()


def _qr_panel(ui, text: str, caption: list) -> None:
    """QR left (as big as the height allows), caption lines right."""
    d = ui.d
    mat, n = _qr(text)
    quiet = 1 if ui.small else 2

    # biggest integer scale within full height and half the width
    scale = max(1, min(d.height, d.width // 2) // (n + 2 * quiet))
    side = (n + 2 * quiet) * scale
    d.fill(ui.bg)
    ui.qr(mat, n, 0, (d.height - side) // 2, scale, quiet)
    ui.column(caption, side, d.width - side)
    d.show()


def setup_page(ui, page: int, ssid: str, pw: str, ip: str, reason: str) -> int:
    """Draw setup page, returns page count."""
    wifi_qr = "WIFI:T:WPA;S:%s;P:%s;;" % (ssid, pw)

    # big: one static screen
    if not ui.small:
        _qr_panel(ui, wifi_qr, [("Einrichtung", ui.fg), ("WLAN", ui.dim), (ssid, ui.fg),
                                ("Passwort", ui.dim), (pw, ui.fg), ("http://" + ip, ui.fg),
                                (reason, ui.dim)])
        return 1

    # small: three fixed pages, nothing scrolls
    if page == 0:
        _qr_panel(ui, wifi_qr, [("WLAN", ui.fg), ("scannen", ui.dim)])
    elif page == 1:
        _qr_panel(ui, "http://" + ip, [("Seite", ui.fg), ("öffnen", ui.dim)])
    else:
        ui.d.fill(ui.bg)
        ui.column([("WLAN:", ui.dim), (ssid, ui.fg), ("Passwort:", ui.dim), (pw, ui.fg), (ip, ui.fg)],
                  names=("b8",))
        ui.d.show()
    return 3


def info_page(ui, page: int, ip: str) -> int:
    """Settings address while running. Returns page count."""
    url = "http://" + ip
    if not ui.small:
        _qr_panel(ui, url, [("Einstellungen", ui.fg), (url, ui.fg), ("im selben WLAN", ui.dim)])
        return 1
    if page == 0:
        _qr_panel(ui, url, [("Setup", ui.fg), ("scannen", ui.dim)])
    else:
        ui.message("Einstellungen", [ip])
    return 2


def run(app, reason: str) -> None:
    """Setup loop, never returns. Saving wifi in the portal reboots."""
    app.ap_mode = True

    # AP password: random once, kept encrypted, shown only on the display
    pw = app.sec.get("ap")
    if not pw:
        from data import store
        pw = app.sec["ap"] = store.random_pw()
        store.save_secret(app.sec)
        del store
        sys.modules.pop("data.store", None)
    ssid = wifi.ap_name(config.AP_PREFIX)
    app.ip = wifi.ap(ssid, pw)
    app.listen()

    # page rotation + idle reboot (maybe the router is back)
    page, pages = 0, 1
    flip = idle = 0
    while True:
        now = time.ticks_ms()
        if app.serve():
            idle = 0
        if not flip or time.ticks_diff(now, flip) >= 0:
            pages = setup_page(app.ui, page, ssid, pw, app.ip, reason)
            page = (page + 1) % pages
            flip = time.ticks_add(now, config.PAGE_S * 1000) if pages > 1 else time.ticks_add(now, 3600000)
        if not idle:
            idle = time.ticks_add(now, config.SETUP_IDLE_S * 1000)
        if app.s["ssid"] and time.ticks_diff(now, idle) >= 0:
            app.reboot_soon(0)
        app.button()
        app.maybe_reboot()
        time.sleep_ms(50)
