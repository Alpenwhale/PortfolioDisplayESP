"""Config web UI. Imported per request and unloaded after, RAM is tight.

Secrets are write-only: the page never contains a stored password.
Basic auth (if a portal password is set) applies on the home network, not in setup AP mode;
the AP itself is WPA2 with a static per-device password shown only on the display.
"""
import binascii
import network

import config
from data import store

MODES = (("slide", "Slideshow"), ("port", "Portfolio return"), ("single", "Single security"))
PERIODS = (("1d", "Day"), ("5d", "Week"), ("ytd", "Year to date"), ("max", "All time"))
NUMFMTS = (("de", "German: 1.234,56 € / +0,73 %"), ("en", "English: €1,234.56 / +0.73%"))
CURRENCIES = (("EUR", "Euro (EUR)"), ("USD", "US Dollar (USD)"), ("GBP", "British Pound (GBP)"),
              ("CHF", "Swiss Franc (CHF)"), ("JPY", "Japanese Yen (JPY)"),
              ("native", "No conversion (exchange currency)"))

# value = yahoo suffix (see net.quotes.resolve). "auto" prefers Xetra, "US" = no suffix.
EXCHANGES = (("auto", "Automatic"), (".DE", "Xetra (DE)"), ("US", "NYSE / Nasdaq (US)"),
             (".L", "London (UK)"), (".PA", "Euronext Paris (FR)"), (".AS", "Euronext Amsterdam (NL)"),
             (".MI", "Borsa Italiana (IT)"), (".MC", "Madrid (ES)"), (".SW", "SIX Swiss (CH)"),
             (".TO", "Toronto (CA)"), (".T", "Tokyo (JP)"), (".HK", "Hong Kong (HK)"),
             (".AX", "Sydney (AU)"))
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
    """'1,234.5' / '1234,5' -> float, '' -> None. Last separator is the decimal point."""
    if not s:
        return None
    s = s.replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(",", "") if s.rfind(".") > s.rfind(",") else s.replace(".", "").replace(",", ".")
    else:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def fmt(v) -> str:
    """Float for an input value, '' for None."""
    return "" if v is None else "%g" % v


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
    send(cl, "200 OK", '<!doctype html><html lang=en><meta name=viewport content="width=device-width,'
                       'initial-scale=1"><title>PortfolioDisplay</title><link rel=stylesheet href=/s.css>'
                       "<h1>PortfolioDisplay</h1>")
    if note:
        cl.write("<p>%s</p>" % note)

    # wifi, password never echoed
    cl.write('<form method=post action=/save><h2>Wi-Fi</h2><label>Network</label>'
             '<input name=ssid list=nets value="%s" autocomplete=off><datalist id=nets>' % esc(s["ssid"]))
    for n in nets:
        cl.write('<option value="%s">' % esc(n))
    cl.write('</datalist><label>Password</label><input name=pw type=password autocomplete=new-password '
             'placeholder="%s">' % ("saved - leave empty to keep" if sec.get("pw") else ""))

    # display mode, period, timings
    cl.write("<h2>Display</h2><label>Mode</label><select name=mode>")
    options(cl, MODES, s["mode"])
    cl.write("</select><label>Single security</label><select name=single>")
    options(cl, [(str(i), esc(it.get("name") or it["id"])) for i, it in enumerate(s["items"])], str(s["single"]))
    cl.write("</select><label>Show change over</label><select name=period>")
    options(cl, PERIODS, s["period"])
    cl.write("</select><label>Number format</label><select name=numfmt>")
    options(cl, NUMFMTS, s["numfmt"])
    cl.write("</select><label>Currency (prices are converted at today's rate)</label><select name=cur>")
    options(cl, CURRENCIES, s["cur"])
    cl.write('</select><div class=g><div><label>Slide time (s)</label><input name=slide_s type=number '
             'min=3 value=%d></div><div><label>Refresh every (s)</label><input name=fetch_s type=number '
             'min=60 value=%d></div></div>' % (s["slide_s"], s["fetch_s"]))

    # securities, one empty row for adding
    cl.write("<h2>Securities</h2><small>ISIN, WKN or ticker (e.g. AAPL). Quantity + buy price are "
             "optional, needed for returns. Enter the buy price in the display currency above.</small>")
    rows = s["items"] + ([{}] if len(s["items"]) < store.MAX_ITEMS else [])
    for i, it in enumerate(rows):
        sym = it.get("sym", "")
        cl.write('<div class=row><label>Identifier%s</label><input name=id%d value="%s">'
                 '<label>Exchange</label><select name=ex%d>'
                 % (" &rarr; " + esc(sym) if sym and sym != it.get("id") else "", i, esc(it.get("id", "")), i))
        options(cl, EXCHANGES, it.get("ex", "auto"))
        cl.write('</select><label>Description</label><input name=name%d value="%s" placeholder="automatic">'
                 '<div class=g><div><label>Quantity</label><input name=qty%d inputmode=decimal value="%s"></div>'
                 '<div><label>Buy price</label><input name=buy%d inputmode=decimal value="%s"></div></div>'
                 % (i, esc(it.get("name", "")), i, fmt(it.get("qty")), i, fmt(it.get("buy"))))
        if it:
            cl.write('<label><input class=cb type=checkbox name=del%d> remove</label>' % i)
        cl.write("</div>")

    # security: portal password + setup wifi password
    cl.write('<h2>Security</h2><label>Password for this page on your network %s</label>'
             '<input name=pp type=password autocomplete=new-password placeholder="%s">'
             % ("(set)" if sec.get("pp") else "(optional)", "leave empty to keep" if sec.get("pp") else ""))
    if sec.get("pp"):
        cl.write('<label><input class=cb type=checkbox name=ppdel> remove password</label><br>')
    cl.write('<label><input class=cb type=checkbox name=apnew> new setup Wi-Fi password '
             "(normally it never changes)</label>"
             "<p><small>Forgot the password? Press FLASH while the display shows 'Starting...' "
             "= setup mode without login. Hold FLASH for %d s = factory reset.</small></p>"
             "<button>Save</button></form>" % config.RESET_HOLD_S)


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
        store.new_ap_password()

    # display settings, clamped
    if f.get("mode") in [k for k, _ in MODES]:
        s["mode"] = f["mode"]
    old = (s["period"], s["cur"])
    if f.get("period") in [k for k, _ in PERIODS]:
        s["period"] = f["period"]
    if f.get("numfmt") in [k for k, _ in NUMFMTS]:
        s["numfmt"] = f["numfmt"]
    if f.get("cur") in [k for k, _ in CURRENCIES]:
        s["cur"] = f["cur"]
    s["slide_s"] = max(3, min(3600, int(to_float(f.get("slide_s")) or 8)))
    s["fetch_s"] = max(60, min(86400, int(to_float(f.get("fetch_s")) or 300)))

    # securities: keep resolved symbol only if id + exchange unchanged
    prev_items = {it["id"]: it for it in s["items"]}
    items = []
    for i in range(store.MAX_ITEMS + 1):
        ident = f.get("id%d" % i, "").upper()
        if not ident or f.get("del%d" % i) or len(items) >= store.MAX_ITEMS:
            continue
        ex = f.get("ex%d" % i, "auto")
        it = {"id": ident, "ex": ex, "name": f.get("name%d" % i, ""),
              "qty": to_float(f.get("qty%d" % i)), "buy": to_float(f.get("buy%d" % i))}
        prev = prev_items.get(ident)
        if prev and prev.get("sym") and prev.get("ex", "auto") == ex:
            it["sym"], it["yname"] = prev["sym"], prev.get("yname", "")
        else:
            app.q.pop(ident, None)
        items.append(it)
    s["items"] = items
    s["single"] = max(0, min(len(items) - 1, int(to_float(f.get("single")) or 0)))

    # persist, refetch if period or currency moved
    store.save(s)
    store.save_secret(sec)
    if (s["period"], s["cur"]) != old:
        app.refetch_all()
    else:
        app.dirty = True  # number format is render-only
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
        send(cl, "401 Unauthorized", "Login required", 'WWW-Authenticate: Basic realm="PortfolioDisplay"\r\n')
        return

    # save: reboot page or back to the form
    if method == "POST" and path == "/save":
        if apply(app, parse_form(body)):
            send(cl, "200 OK", '<meta name=viewport content="width=device-width"><link rel=stylesheet '
                               "href=/s.css><h1>Saved</h1><p>The device restarts and joins your Wi-Fi.</p>")
            app.reboot_soon()
        else:
            app.applied()
            send(cl, "303 See Other", "", "Location: /?ok\r\n")
        return
    page(cl, app, "Saved." if path.endswith("?ok") else "")
