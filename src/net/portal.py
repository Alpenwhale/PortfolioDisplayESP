"""Config web UI. Imported per request and unloaded after, RAM is tight.

Secrets are write-only: the page never contains a stored password.
Basic auth (if a portal password is set) applies on the home network, not in setup AP mode;
the AP itself is WPA2 with a random password shown only on the display.
"""
import binascii
import network

import config
from data import store

MODES = (("slide", "Slideshow"), ("port", "Portfolio-Rendite"), ("single", "Einzelwert"))
PERIODS = (("1d", "Tag"), ("5d", "Woche"), ("ytd", "Jahr (YTD)"), ("max", "All time"))

# value = yahoo suffix (see net.quotes.resolve), "auto" prefers xetra/frankfurt, "US" = no suffix
EXCHANGES = (("auto", "Automatisch"), (".DE", "Xetra"), (".F", "Frankfurt"), (".SG", "Stuttgart"),
             (".MU", "München"), ("US", "NYSE / Nasdaq"), (".L", "London"), (".AS", "Amsterdam"),
             (".PA", "Paris"), (".SW", "Schweiz"))
CSS = "/www/s.css"  # streamed from flash, not held in RAM


# --- tiny helpers (no str.partition / urllib on esp8266) ---

def cut(s, sep):
    """(before, after) at first sep."""
    i = s.find(sep)
    return (s, s[:0]) if i < 0 else (s[:i], s[i + len(sep):])


def esc(s) -> str:
    """HTML escape."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def unquote(s: str) -> str:
    """Form-urlencoded value -> str (utf-8)."""
    b = s.replace("+", " ").encode()
    out = bytearray()
    i = 0
    while i < len(b):
        if b[i] == 37 and i + 2 < len(b):  # %XX
            out.append(int(b[i + 1:i + 3].decode(), 16))
            i += 3
        else:
            out.append(b[i])
            i += 1
    return out.decode()


def parse_form(body: str) -> dict:
    """k=v&k=v -> dict."""
    f = {}
    for kv in body.split("&"):
        k, v = cut(kv, "=")
        if k:
            f[unquote(k)] = unquote(v).strip()
    return f


def to_float(s):
    """'1.234,5' / '1234.5' -> float, '' -> None."""
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fmt(v) -> str:
    """Float for an input value, '' for None."""
    return "" if v is None else ("%g" % v).replace(".", ",")


def options(cl, pairs, current) -> None:
    """<option>s for a select."""
    for k, v in pairs:
        cl.write('<option value="%s"%s>%s</option>' % (k, " selected" if k == current else "", v))


# --- http ---

def read_request(cl) -> tuple:
    """(method, path, headers, body). Body capped at 4 KB."""

    # headers until blank line
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 4096:
        chunk = cl.recv(512)
        if not chunk:
            break
        data += chunk
    head, body = cut(data, b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    method, path = (lines[0].split(" ") + ["", ""])[:2]
    hdr = {}
    for ln in lines[1:]:
        k, v = cut(ln, ":")
        hdr[k.strip().lower()] = v.strip()

    # rest of the body per content-length
    need = min(int(hdr.get("content-length", 0) or 0), 4096)
    while len(body) < need:
        chunk = cl.recv(512)
        if not chunk:
            break
        body += chunk
    return method, path, hdr, body.decode()


def authed(app, hdr: dict) -> bool:
    """Basic auth check. Open in AP mode or without portal password."""
    stored = app.sec.get("pp")
    if app.ap_mode or not stored:
        return True
    a = hdr.get("authorization", "")
    if not a.startswith("Basic "):
        return False
    try:
        pw = cut(binascii.a2b_base64(a[6:]).decode(), ":")[1]
    except Exception:
        return False
    return store.pw_check(pw, stored)


def send(cl, status: str, body: str = "", extra: str = "") -> None:
    """Small html response."""
    cl.write("HTTP/1.0 %s\r\nContent-Type: text/html; charset=utf-8\r\n%sConnection: close\r\n\r\n%s"
             % (status, extra, body))


# --- page ---

def page(cl, app, note: str = "") -> None:
    """Settings form, streamed in small writes."""
    s, sec = app.s, app.sec

    # visible networks for the ssid field
    try:
        nets = sorted({n[0].decode() for n in network.WLAN(network.STA_IF).scan() if n[0]})
    except Exception:
        nets = []

    # head
    send(cl, "200 OK", '<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">'
                       "<title>PortfolioDisplay</title><link rel=stylesheet href=/s.css><h1>PortfolioDisplay</h1>")
    if note:
        cl.write("<p>%s</p>" % note)

    # wifi, password never echoed
    cl.write('<form method=post action=/save><h2>WLAN</h2><label>Netzwerk</label>'
             '<input name=ssid list=nets value="%s" autocomplete=off><datalist id=nets>' % esc(s["ssid"]))
    for n in nets:
        cl.write('<option value="%s">' % esc(n))
    cl.write('</datalist><label>Passwort</label><input name=pw type=password autocomplete=new-password '
             'placeholder="%s">' % ("gespeichert - leer lassen = unverändert" if sec.get("pw") else ""))

    # display mode, period, timings
    cl.write("<h2>Anzeige</h2><label>Modus</label><select name=mode>")
    options(cl, MODES, s["mode"])
    cl.write("</select><label>Einzelwert</label><select name=single>")
    options(cl, [(str(i), esc(it.get("name") or it["id"])) for i, it in enumerate(s["items"])], str(s["single"]))
    cl.write("</select><label>Veränderung über</label><select name=period>")
    options(cl, PERIODS, s["period"])
    cl.write('</select><div class=g><div><label>Slide-Dauer (s)</label><input name=slide_s type=number '
             'min=3 value=%d></div><div><label>Abruf alle (s)</label><input name=fetch_s type=number '
             'min=60 value=%d></div></div>' % (s["slide_s"], s["fetch_s"]))

    # securities, one empty row for adding
    cl.write("<h2>Wertpapiere</h2><small>ISIN, WKN oder Ticker (z.B. SAP). Stück + Kaufkurs optional, "
             "nötig für Rendite.</small>")
    rows = s["items"] + ([{}] if len(s["items"]) < store.MAX_ITEMS else [])
    for i, it in enumerate(rows):
        sym = it.get("sym", "")
        cl.write('<div class=row><label>Kennung%s</label><input name=id%d value="%s">'
                 '<label>Börse</label><select name=ex%d>'
                 % (" &rarr; " + esc(sym) if sym and sym != it.get("id") else "", i, esc(it.get("id", "")), i))
        options(cl, EXCHANGES, it.get("ex", "auto"))
        cl.write('</select><label>Beschreibung</label><input name=name%d value="%s" placeholder="automatisch">'
                 '<div class=g><div><label>Stück</label><input name=qty%d inputmode=decimal value="%s"></div>'
                 '<div><label>Kaufkurs</label><input name=buy%d inputmode=decimal value="%s"></div></div>'
                 % (i, esc(it.get("name", "")), i, fmt(it.get("qty")), i, fmt(it.get("buy"))))
        if it:
            cl.write('<label><input class=cb type=checkbox name=del%d> entfernen</label>' % i)
        cl.write("</div>")

    # security: portal password + fresh setup-wifi password
    cl.write('<h2>Sicherheit</h2><label>Passwort für diese Seite im Heimnetz %s</label>'
             '<input name=pp type=password autocomplete=new-password placeholder="%s">'
             % ("(gesetzt)" if sec.get("pp") else "(optional)",
                "leer lassen = unverändert" if sec.get("pp") else ""))
    if sec.get("pp"):
        cl.write('<label><input class=cb type=checkbox name=ppdel> Schutz entfernen</label><br>')
    cl.write('<label><input class=cb type=checkbox name=apnew> Einrichtungs-WLAN-Passwort neu erzeugen</label>'
             "<p><small>Passwort vergessen? Beim Start FLASH halten = Einrichtung ohne Login. "
             "FLASH %d s halten = alles zurücksetzen.</small></p>"
             "<button>Speichern</button></form>" % config.RESET_HOLD_S)


# --- save ---

def apply(app, f: dict) -> bool:
    """Form -> settings/secrets. Returns True if a reboot is needed (wifi changed)."""
    s, sec = app.s, app.sec

    # wifi: new ssid or password -> reboot to rejoin
    ssid = f.get("ssid", "")
    reboot = ssid != s["ssid"] or bool(f.get("pw"))
    s["ssid"] = ssid
    if f.get("pw"):
        sec["pw"] = f["pw"]

    # portal password, setup ap password
    if f.get("pp"):
        sec["pp"] = store.pw_hash(f["pp"])
    elif f.get("ppdel"):
        sec.pop("pp", None)
    if f.get("apnew"):
        sec.pop("ap", None)  # setup mode makes a new one

    # display settings, clamped
    if f.get("mode") in [k for k, _ in MODES]:
        s["mode"] = f["mode"]
    old_period = s["period"]
    if f.get("period") in [k for k, _ in PERIODS]:
        s["period"] = f["period"]
    s["slide_s"] = max(3, min(3600, int(to_float(f.get("slide_s")) or 8)))
    s["fetch_s"] = max(60, min(86400, int(to_float(f.get("fetch_s")) or 300)))

    # securities: keep resolved symbol only if id + exchange unchanged
    old = {it["id"]: it for it in s["items"]}
    items = []
    for i in range(store.MAX_ITEMS + 1):
        ident = f.get("id%d" % i, "").upper()
        if not ident or f.get("del%d" % i) or len(items) >= store.MAX_ITEMS:
            continue
        ex = f.get("ex%d" % i, "auto")
        it = {"id": ident, "ex": ex, "name": f.get("name%d" % i, ""),
              "qty": to_float(f.get("qty%d" % i)), "buy": to_float(f.get("buy%d" % i))}
        prev = old.get(ident)
        if prev and prev.get("sym") and prev.get("ex", "auto") == ex:
            it["sym"], it["yname"] = prev["sym"], prev.get("yname", "")
        else:
            app.q.pop(ident, None)
        items.append(it)
    s["items"] = items
    s["single"] = max(0, min(len(items) - 1, int(to_float(f.get("single")) or 0)))

    # persist, refetch if the period moved
    store.save(s)
    store.save_secret(sec)
    if s["period"] != old_period:
        app.refetch_all()
    return reboot


def handle(cl, app) -> None:
    """One request."""
    cl.settimeout(5)
    method, path, hdr, body = read_request(cl)

    # css is public, everything else behind auth
    if path == "/s.css":
        cl.write("HTTP/1.0 200 OK\r\nContent-Type: text/css\r\nCache-Control: max-age=86400\r\n\r\n")
        with open(CSS, "rb") as fh:
            while True:
                b = fh.read(256)
                if not b:
                    break
                cl.write(b)
        return
    if not authed(app, hdr):
        send(cl, "401 Unauthorized", "Login nötig", 'WWW-Authenticate: Basic realm="PortfolioDisplay"\r\n')
        return

    # save: reboot page or back to the form
    if method == "POST" and path == "/save":
        if apply(app, parse_form(body)):
            send(cl, "200 OK", '<meta name=viewport content="width=device-width"><link rel=stylesheet '
                               "href=/s.css><h1>Gespeichert</h1><p>Gerät startet neu und verbindet "
                               "sich mit dem WLAN.</p>")
            app.reboot_soon()
        else:
            app.applied()
            send(cl, "303 See Other", "", "Location: /?ok\r\n")
        return
    page(cl, app, "Gespeichert." if path.endswith("?ok") else "")
