"""Config web UI backend. Imported per request and unloaded after, RAM is tight.

The form itself is static (/www/index.html + s.css, streamed from flash); a little JS
fills it from /cfg.json. Both directions stream: /cfg.json copies asset lines straight
from flash, POST /save writes each asset row to the new file as soon as it arrives.
So RAM use doesn't grow with the number of assets.
Secrets are write-only: /cfg.json only says *whether* a password is set.
Basic auth (if a portal password is set) applies on the home network, not in setup AP mode.
"""
import binascii
import gc
import json
import network

import config
from data import assets, store

STATIC = {"/": "/www/index.html", "/s.css": "/www/s.css", "/saved": "/www/saved.html"}
TYPES = {"html": "text/html; charset=utf-8", "css": "text/css"}
MODES = ("slide", "port", "single")
PERIODS = ("1d", "5d", "ytd", "max")
NUMFMTS = ("de", "en")
CURRENCIES = ("EUR", "USD", "GBP", "CHF", "JPY", "native")
ROW_FIELDS = ("id", "ex", "name", "qty", "buy", "sym", "yname")
MAX_BODY = 32768  # streamed, so this only guards against garbage


# --- tiny helpers (no str.partition / urllib on esp8266) ---

def cut(s, sep):
    """(before, after) at first sep."""
    i = s.find(sep)
    return (s, s[:0]) if i < 0 else (s[:i], s[i + len(sep):])


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


# --- http ---

def read_head(cl) -> tuple:
    """(method, path, headers we care about, body bytes already received)."""

    # headers until blank line
    data = b""
    while b"\r\n\r\n" not in data and len(data) < 4096:
        chunk = cl.recv(512)
        if not chunk:
            break
        data += chunk
    head, rest = cut(data, b"\r\n\r\n")
    lines = head.decode().split("\r\n")
    method, path = (lines[0].split(" ") + ["", ""])[:2]

    # browsers send ~1 KB of headers, keep only two
    hdr = {}
    for ln in lines[1:]:
        k, v = cut(ln, ":")
        k = k.strip().lower()
        if k in ("content-length", "authorization"):
            hdr[k] = v.strip()
    return method, path, hdr, rest


def pairs(cl, buf: bytes, length: int):
    """Yield (key, value) of a urlencoded body while it streams in. Never holds the whole body."""
    left = min(length, MAX_BODY) - len(buf)
    while True:

        # every complete pair right away
        while b"&" in buf:
            kv, buf = cut(buf, b"&")
            k, v = cut(kv.decode(), "=")
            if k:
                yield unquote(k), unquote(v).strip()
        if left <= 0:
            break

        # next chunk off the socket
        chunk = cl.recv(min(512, left))
        if not chunk:
            break
        left -= len(chunk)
        buf += chunk

    # last pair has no trailing &
    k, v = cut(buf.decode(), "=")
    if k:
        yield unquote(k), unquote(v).strip()


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


def head(cl, status: str, ctype: str = "text/plain", extra: str = "") -> None:
    """Status line + headers."""
    cl.write("HTTP/1.0 %s\r\nContent-Type: %s\r\n%sConnection: close\r\n\r\n" % (status, ctype, extra))


def send_file(cl, path: str) -> None:
    """Stream a flash file in small chunks."""
    head(cl, "200 OK", TYPES[path.rsplit(".", 1)[1]])
    with open(path, "rb") as fh:
        while True:
            b = fh.read(512)
            if not b:
                break
            cl.write(b)


def send_cfg(cl, app) -> None:
    """Settings + asset lines as json for the form. Only flags for secrets."""

    # visible networks for the ssid field
    try:
        nets = sorted({n[0].decode() for n in network.WLAN(network.STA_IF).scan() if n[0]})
    except Exception:
        nets = []

    # assets copied line by line from flash, never parsed
    head(cl, "200 OK", "application/json", "Cache-Control: no-store\r\n")
    cl.write('{"s":')
    cl.write(json.dumps(app.s))
    cl.write(',"items":[')
    sep = ""
    for ln in assets.lines():
        cl.write(sep)
        cl.write(ln)
        sep = ","
    cl.write('],"pw":%s,"pp":%s,"max":%d,"reset_s":%d,"nets":%s}' % (
        "true" if app.sec.get("pw") else "false", "true" if app.sec.get("pp") else "false",
        assets.MAX, config.RESET_HOLD_S, json.dumps(nets)))


# --- save ---

def _row(w, r: dict) -> None:
    """One form row -> asset record. Empty identifier = row dropped."""
    ident = r.get("id", "").upper()
    if not ident:
        return
    rec = {"id": ident, "ex": r.get("ex") or "auto", "name": r.get("name", ""),
           "qty": to_float(r.get("qty")), "buy": to_float(r.get("buy"))}

    # the page only sends sym/yname back if id + exchange are unchanged
    if r.get("sym"):
        rec["sym"], rec["yname"] = r["sym"], r.get("yname", "")
    w.add(rec)


def save(app, cl, rest: bytes, length: int) -> bool:
    """Stream the form into settings/secrets/assets. Returns True if a reboot is needed."""
    s, sec = app.s, app.sec
    g = {}            # global fields, a dozen small strings
    row, idx = {}, None
    w = assets.Writer()

    # rows arrive in page order: id0 ex0 ... buy0 id1 ...; flush when the index changes
    try:
        for k, v in pairs(cl, rest, length):
            name = k.rstrip("0123456789")
            if name in ROW_FIELDS and name != k:
                i = k[len(name):]
                if i != idx:
                    _row(w, row)
                    row, idx = {}, i
                row[name] = v
            else:
                g[k] = v
        _row(w, row)
    except Exception:
        w.abort()
        raise
    w.commit()
    del row
    gc.collect()

    # wifi: new ssid or password -> reboot to rejoin
    ssid = g.get("ssid", "")
    reboot = ssid != s["ssid"] or bool(g.get("pw"))
    s["ssid"] = ssid
    if g.get("pw"):
        sec["pw"] = g["pw"]

    # portal password, setup ap password
    if g.get("pp"):
        sec["pp"] = store.pw_hash(g["pp"])
    elif g.get("ppdel"):
        sec.pop("pp", None)
    if g.get("apnew"):
        store.new_ap_password()

    # display settings, only known values, numbers clamped
    old = (s["period"], s["cur"])
    for key, allowed in (("mode", MODES), ("period", PERIODS), ("numfmt", NUMFMTS), ("cur", CURRENCIES)):
        if g.get(key) in allowed:
            s[key] = g[key]
    s["slide_s"] = max(3, min(3600, int(to_float(g.get("slide_s")) or 8)))
    s["fetch_s"] = max(60, min(86400, int(to_float(g.get("fetch_s")) or 300)))
    s["single"] = max(0, min(w.n - 1, int(to_float(g.get("single")) or 0)))

    # persist (collect first, AES needs a few contiguous blocks)
    g = None
    gc.collect()
    store.save(s)
    gc.collect()
    store.save_secret(sec)
    if (s["period"], s["cur"]) != old:
        app.fx = {}
    return reboot


def handle(cl, app) -> None:
    """One request."""
    cl.settimeout(5)
    method, path, hdr, rest = read_head(cl)
    path = cut(path, "?")[0]

    # css is public, everything else behind auth
    if path == "/s.css":
        send_file(cl, STATIC[path])
        return
    if not authed(app, hdr):
        head(cl, "401 Unauthorized", extra='WWW-Authenticate: Basic realm="PortfolioDisplay"\r\n')
        cl.write("Login required")
        return

    # save: reboot page or back to the form, feedback on the display either way
    if method == "POST" and path == "/save":
        reboot = save(app, cl, rest, int(hdr.get("content-length", 0) or 0))
        rest = None
        if reboot:
            send_file(cl, STATIC["/saved"])
        else:
            head(cl, "303 See Other", extra="Location: /?ok\r\n")
        app.saved(reboot)
        return

    # form + its data, anything else (captive portal probes etc.) gets the form too
    if path == "/cfg.json":
        send_cfg(cl, app)
    else:
        send_file(cl, STATIC["/"])
