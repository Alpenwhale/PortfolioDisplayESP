"""Config web UI. Imported per request and unloaded after, RAM is tight.

Secrets are write-only: the page never contains a stored password.
Basic auth (if a portal password is set) applies on the home network, not in setup AP mode;
the AP itself is WPA2 with a random password shown on the display.
"""
import binascii
import network
import store

MODES = (("slide", "Slideshow"), ("port", "Portfolio-Rendite"), ("single", "Einzelwert"))
CSS = "/www/s.css"  # streamed from flash, not held in RAM


def cut(s, sep):
    """(before, after) at first sep. str.partition doesn't exist on esp8266."""
    i = s.find(sep)
    return (s, s[:0]) if i < 0 else (s[:i], s[i + len(sep):])


def esc(s) -> str:
    """HTML escape."""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def unquote(s: str) -> str:
    """application/x-www-form-urlencoded value -> str."""
    b = s.replace("+", " ").encode()
    out = bytearray()
    i = 0
    while i < len(b):
        if b[i] == 37 and i + 2 < len(b):  # '%'
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


def to_float(s: str):
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


def read_request(cl) -> tuple:
    """(method, path, headers, body). Body capped at 4 KB."""
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
    need = min(int(hdr.get("content-length", 0) or 0), 4096)
    while len(body) < need:
        chunk = cl.recv(512)
        if not chunk:
            break
        body += chunk
    return method, path, hdr, body.decode()


def authed(app, hdr: dict) -> bool:
    """Basic auth check, open in AP mode or without portal password."""
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


def send(cl, status: str, body_parts: list, extra: str = "") -> None:
    """Response with html body streamed in parts."""
    cl.write("HTTP/1.0 %s\r\nContent-Type: text/html; charset=utf-8\r\n%sConnection: close\r\n\r\n" % (status, extra))
    for p in body_parts:
        cl.write(p)


def page(cl, app, note: str = "") -> None:
    """Settings form."""
    s, sec = app.s, app.sec
    try:
        nets = sorted({n[0].decode() for n in network.WLAN(network.STA_IF).scan() if n[0]})
    except Exception:
        nets = []
    cl.write("HTTP/1.0 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nConnection: close\r\n\r\n")
    cl.write('<!doctype html><meta name=viewport content="width=device-width,initial-scale=1">'
             "<title>PortfolioDisplay</title><link rel=stylesheet href=/s.css><h1>PortfolioDisplay</h1>")
    if note:
        cl.write("<p>%s</p>" % note)
    cl.write('<form method=post action=/save><h2>WLAN</h2><label>Netzwerk</label>'
             '<input name=ssid list=nets value="%s" autocomplete=off><datalist id=nets>' % esc(s["ssid"]))
    for n in nets:
        cl.write('<option value="%s">' % esc(n))
    cl.write('</datalist><label>Passwort</label><input name=pw type=password autocomplete=new-password '
             'placeholder="%s">' % ("gespeichert - leer lassen = unverändert" if sec.get("pw") else ""))

    cl.write("<h2>Anzeige</h2><label>Modus</label><select name=mode>")
    for k, v in MODES:
        cl.write('<option value=%s%s>%s</option>' % (k, " selected" if s["mode"] == k else "", v))
    cl.write("</select><label>Einzelwert</label><select name=single>")
    for i, it in enumerate(s["items"]):
        cl.write('<option value=%d%s>%s</option>' % (i, " selected" if s["single"] == i else "",
                                                     esc(it.get("name") or it["id"])))
    cl.write('</select><div class=g><div><label>Slide-Dauer (s)</label><input name=slide_s type=number '
             'min=3 value=%d></div><div><label>Abruf alle (s)</label><input name=fetch_s type=number '
             'min=60 value=%d></div></div>' % (s["slide_s"], s["fetch_s"]))

    cl.write("<h2>Wertpapiere</h2><small>ISIN, WKN oder Yahoo-Ticker (z.B. EUNL.DE). "
             "Stück + Kaufkurs optional, nötig für Rendite.</small>")
    rows = s["items"] + ([{}] if len(s["items"]) < store.MAX_ITEMS else [])
    for i, it in enumerate(rows):
        sym = it.get("sym", "")
        cl.write('<div class=row><label>Kennung%s</label><input name=id%d value="%s">'
                 '<label>Beschreibung</label><input name=name%d value="%s" placeholder="automatisch">'
                 '<div class=g><div><label>Stück</label><input name=qty%d inputmode=decimal value="%s"></div>'
                 '<div><label>Kaufkurs</label><input name=buy%d inputmode=decimal value="%s"></div></div>'
                 % (" (%s)" % esc(sym) if sym and sym != it.get("id") else "", i, esc(it.get("id", "")),
                    i, esc(it.get("name", "")), i, fmt(it.get("qty")), i, fmt(it.get("buy"))))
        if it:
            cl.write('<label><input class=cb type=checkbox name=del%d> entfernen</label>' % i)
        cl.write("</div>")

    cl.write('<h2>Portal-Schutz</h2><label>Passwort für diese Seite im Heimnetz %s</label>'
             '<input name=pp type=password autocomplete=new-password placeholder="%s">'
             % ("(gesetzt)" if sec.get("pp") else "(optional)",
                "leer lassen = unverändert" if sec.get("pp") else ""))
    if sec.get("pp"):
        cl.write('<label><input class=cb type=checkbox name=ppdel> Schutz entfernen</label>')
    cl.write("<button>Speichern</button></form>")


def apply(app, f: dict) -> bool:
    """Form -> settings/secrets. Returns True if a reboot is needed (wifi changed)."""
    s, sec = app.s, app.sec
    reboot = False
    ssid = f.get("ssid", "")
    if ssid != s["ssid"] or f.get("pw"):
        reboot = True
    s["ssid"] = ssid
    if f.get("pw"):
        sec["pw"] = f["pw"]
    if f.get("pp"):
        sec["pp"] = store.pw_hash(f["pp"])
    elif f.get("ppdel"):
        sec.pop("pp", None)

    if f.get("mode") in [k for k, _ in MODES]:
        s["mode"] = f["mode"]
    s["slide_s"] = max(3, min(3600, int(to_float(f.get("slide_s")) or 8)))
    s["fetch_s"] = max(60, min(86400, int(to_float(f.get("fetch_s")) or 300)))

    old = {it["id"]: it for it in s["items"]}
    items = []
    for i in range(store.MAX_ITEMS + 1):
        ident = f.get("id%d" % i, "").upper()
        if not ident or f.get("del%d" % i) or len(items) >= store.MAX_ITEMS:
            continue
        it = {"id": ident, "name": f.get("name%d" % i, ""),
              "qty": to_float(f.get("qty%d" % i)), "buy": to_float(f.get("buy%d" % i))}
        if ident in old and old[ident].get("sym"):
            it["sym"] = old[ident]["sym"]
        items.append(it)
    s["items"] = items
    s["single"] = max(0, min(len(items) - 1, int(to_float(f.get("single")) or 0)))

    store.save(s)
    store.save_secret(sec)
    return reboot


def handle(cl, app) -> None:
    """One request."""
    cl.settimeout(5)
    method, path, hdr, body = read_request(cl)
    if not authed(app, hdr):
        send(cl, "401 Unauthorized", ["Login nötig"], 'WWW-Authenticate: Basic realm="PortfolioDisplay"\r\n')
        return
    if path == "/s.css":
        cl.write("HTTP/1.0 200 OK\r\nContent-Type: text/css\r\nCache-Control: max-age=86400\r\n\r\n")
        with open(CSS, "rb") as f:
            while True:
                b = f.read(256)
                if not b:
                    break
                cl.write(b)
        return
    if method == "POST" and path == "/save":
        if apply(app, parse_form(body)):
            send(cl, "200 OK", ['<meta name=viewport content="width=device-width"><link rel=stylesheet '
                                "href=/s.css><h1>Gespeichert</h1><p>Gerät startet neu und verbindet "
                                "sich mit dem WLAN.</p>"])
            app.reboot_soon()
        else:
            app.applied()
            send(cl, "303 See Other", [], "Location: /?ok\r\n")
        return
    page(cl, app, "Gespeichert." if path.endswith("?ok") else "")
