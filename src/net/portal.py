"""Config web UI backend. Imported per request and unloaded after, RAM is tight.

The form itself is static (/www/index.html + s.css, streamed from flash); a little JS
fills it from /cfg.json. So this module holds no HTML and stays small.
Secrets are write-only: /cfg.json only says *whether* a password is set.
Basic auth (if a portal password is set) applies on the home network, not in setup AP mode.
"""
import binascii
import gc
import json
import network

import config
from data import store

STATIC = {"/": ("/www/index.html", "text/html; charset=utf-8"), "/s.css": ("/www/s.css", "text/css")}
MODES = ("slide", "port", "single")
PERIODS = ("1d", "5d", "ytd", "max")
NUMFMTS = ("de", "en")
CURRENCIES = ("EUR", "USD", "GBP", "CHF", "JPY", "native")


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


def head(cl, status: str, ctype: str = "text/plain", extra: str = "") -> None:
    """Status line + headers."""
    cl.write("HTTP/1.0 %s\r\nContent-Type: %s\r\n%sConnection: close\r\n\r\n" % (status, ctype, extra))


def send_file(cl, path: str, ctype: str) -> None:
    """Stream a flash file in small chunks."""
    head(cl, "200 OK", ctype)
    with open(path, "rb") as fh:
        while True:
            b = fh.read(512)
            if not b:
                break
            cl.write(b)


def send_cfg(cl, app) -> None:
    """Settings as json for the form. Only flags for secrets."""

    # visible networks for the ssid field
    try:
        nets = sorted({n[0].decode() for n in network.WLAN(network.STA_IF).scan() if n[0]})
    except Exception:
        nets = []

    head(cl, "200 OK", "application/json", "Cache-Control: no-store\r\n")
    cl.write(json.dumps({"s": app.s, "pw": bool(app.sec.get("pw")), "pp": bool(app.sec.get("pp")),
                         "nets": nets, "max": store.MAX_ITEMS, "reset_s": config.RESET_HOLD_S}))


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

    # display settings, only known values, numbers clamped
    old = (s["period"], s["cur"])
    for key, allowed in (("mode", MODES), ("period", PERIODS), ("numfmt", NUMFMTS), ("cur", CURRENCIES)):
        if f.get(key) in allowed:
            s[key] = f[key]
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

    # persist (collect first, AES needs a few contiguous blocks), refetch if period or currency moved
    f.clear()  # caller still holds the dict, empty it so the strings can go
    del prev_items
    gc.collect()
    store.save(s)
    gc.collect()
    store.save_secret(sec)
    if (s["period"], s["cur"]) != old:
        app.refetch_all()
    return reboot


def handle(cl, app) -> None:
    """One request."""
    cl.settimeout(5)
    method, path, hdr, body = read_request(cl)
    path = cut(path, "?")[0]

    # css is public, everything else behind auth
    if path == "/s.css":
        send_file(cl, *STATIC[path])
        return
    if not authed(app, hdr):
        head(cl, "401 Unauthorized", extra='WWW-Authenticate: Basic realm="PortfolioDisplay"\r\n')
        cl.write("Login required")
        return

    # save: reboot page or back to the form
    if method == "POST" and path == "/save":
        f = parse_form(body)
        body = hdr = None
        gc.collect()
        if apply(app, f):
            head(cl, "200 OK", "text/html; charset=utf-8")
            cl.write('<meta name=viewport content="width=device-width"><link rel=stylesheet href=/s.css>'
                     "<h1>Saved</h1><p>The device restarts and joins your Wi-Fi.</p>")
            app.reboot_soon()
        else:
            app.applied()
            head(cl, "303 See Other", extra="Location: /?ok\r\n")
        return

    # form + its data, anything else (captive portal probes etc.) gets the form too
    if path == "/cfg.json":
        send_cfg(cl, app)
    else:
        send_file(cl, *STATIC["/"])
