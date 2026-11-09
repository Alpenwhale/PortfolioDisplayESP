"""Setup mode (WPA2 AP + portal) and the 'where are my settings' info screen.

Both show QR codes so a phone can join/open without typing. Small screens get rotating
pages (QR wifi, QR url, plain text), big screens get everything at once.
Imported only when needed, then unloaded.
"""
import config
from core.app import drop
from net import wifi


def _qr(text: str) -> tuple:
    """Encode, then drop the encoder module again."""
    from ui import qr
    try:
        return qr.encode(text)
    finally:
        del qr
        drop("ui.qr")


def _draw_qr(ui, mat, n: int, x: int, y: int, scale: int, quiet: int) -> None:
    """QR matrix as dark-on-light, one module row per blit."""
    side = (n + 2 * quiet) * scale
    rb = (side + 7) // 8
    for my in range(-quiet, n + quiet):

        # 1-bit line of this module row
        row = bytearray(rb)
        if 0 <= my < n:
            for mx in range(n):
                if mat[my * n + mx]:
                    for k in range(scale):
                        px = (mx + quiet) * scale + k
                        row[px >> 3] |= 0x80 >> (px & 7)

        # repeat it scale times (bytearray * int doesn't exist on esp8266)
        buf = bytearray(rb * scale)
        for k in range(scale):
            buf[k * rb:(k + 1) * rb] = row
        ui.d.blit_mono(buf, side, scale, x, y + (my + quiet) * scale, ui.bg, ui.fg)


def _qr_panel(ui, text: str, caption: list) -> None:
    """QR left (as big as the height allows), caption lines right."""
    d = ui.d
    mat, n = _qr(text)
    quiet = 1 if ui.small else 2

    # biggest integer scale within full height and half the width
    scale = max(1, min(d.height, d.width // 2) // (n + 2 * quiet))
    side = (n + 2 * quiet) * scale
    d.fill(ui.bg)
    _draw_qr(ui, mat, n, 0, (d.height - side) // 2, scale, quiet)
    ui.column(caption, side, d.width - side)
    d.show()


def setup_page(ui, page: int, ssid: str, pw: str, ip: str, reason: str) -> int:
    """Draw setup page, returns page count."""
    wifi_qr = "WIFI:T:WPA;S:%s;P:%s;;" % (ssid, pw)

    # big: one static screen
    if not ui.small:
        _qr_panel(ui, wifi_qr, [("Setup", ui.fg), ("Wi-Fi", ui.dim), (ssid, ui.fg),
                                ("Password", ui.dim), (pw, ui.fg), ("http://" + ip, ui.fg),
                                (reason, ui.dim)])
        return 1

    # small: three fixed pages, nothing scrolls
    if page == 0:
        _qr_panel(ui, wifi_qr, [("Scan to", ui.dim), ("join", ui.fg), ("Wi-Fi", ui.fg)])
    elif page == 1:
        _qr_panel(ui, "http://" + ip, [("Scan to", ui.dim), ("open", ui.fg), ("setup", ui.fg)])
    else:
        ui.d.fill(ui.bg)
        ui.column([("Wi-Fi:", ui.dim), (ssid, ui.fg), ("Password:", ui.dim), (pw, ui.fg), (ip, ui.fg)],
                  names=("b8",))
        ui.d.show()
    return 3


def info_page(ui, page: int, ip: str) -> int:
    """Settings address while running. Returns page count."""
    url = "http://" + ip
    if not ui.small:
        _qr_panel(ui, url, [("Settings", ui.fg), (url, ui.fg), ("same Wi-Fi only", ui.dim)])
        return 1
    if page == 0:
        _qr_panel(ui, url, [("Scan for", ui.dim), ("settings", ui.fg)])
    else:
        ui.message("Settings", [ip])
    return 2


def start(app) -> tuple:
    """Open the WPA2 setup AP + http server. Returns (ssid, pw); the loop is App.setup_loop."""
    app.ap_mode = True

    # AP password: random once per flash, then static, shown only on the display
    from data import store
    pw = store.ap_password()
    del store
    drop("data.store")

    # AP named after the chip, portal on 192.168.4.1
    ssid = wifi.ap_name(config.AP_PREFIX)
    app.ip = wifi.ap(ssid, pw)
    app.listen()
    return ssid, pw
