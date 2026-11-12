"""Config web UI router: static files, auth, GET /cfg.json (net.cfg), POST /save.

Imported per request and unloaded after, RAM is tight; only the one handler a request
needs is loaded on top. The form is static (/www/index.html + s.css, streamed from flash),
a little JS fills it from /cfg.json. POST /save only dumps the body to flash and reboots,
net.save applies it at the next boot. Secrets are write-only: /cfg.json only says
*whether* a password is set. Basic auth (if a portal password is set) applies on the
home network, not in setup AP mode.
"""
import gc

STATIC = {"/": "/www/index.html", "/s.css": "/www/s.css", "/saved": "/www/saved.html"}
TYPES = {"html": "text/html; charset=utf-8", "css": "text/css"}
PENDING = "/pending.form"  # same path as net.save.PENDING
MAX_BODY = 32768           # guards against garbage, 50 assets are ~4 KB


def cut(s, sep):
    """(before, after) at first sep. No str.partition on esp8266."""
    i = s.find(sep)
    return (s, s[:0]) if i < 0 else (s[:i], s[i + len(sep):])


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
    return method, cut(path, "?")[0], hdr, rest


def authed(app, hdr: dict) -> bool:
    """Basic auth check. Open in AP mode or without portal password."""
    stored = app.sec.get("pp")
    if app.ap_mode or not stored:
        return True
    a = hdr.get("authorization", "")
    if not a.startswith("Basic "):
        return False

    # only now we need base64 + the hash check
    import binascii
    from data import store
    try:
        pw = cut(binascii.a2b_base64(a[6:]).decode(), ":")[1]
    except Exception:
        return False
    return store.pw_check(pw, stored)


def head(cl, status: str, ctype: str = "text/plain", extra: str = "") -> None:
    """Status line + headers."""
    cl.write("HTTP/1.0 %s\r\nServer: PortfolioDisplay (Alpenwhale, PUNCL-1.0)\r\nContent-Type: %s\r\n%sConnection: close\r\n\r\n"
             % (status, ctype, extra))


def send_file(cl, path: str) -> None:
    """Stream a flash file through one small reused buffer."""
    head(cl, "200 OK", TYPES[path[path.rfind(".") + 1:]])
    buf = bytearray(256)
    mv = memoryview(buf)
    with open(path, "rb") as fh:
        while True:
            n = fh.readinto(buf)
            if not n:
                break
            cl.write(mv[:n])


def dump_body(cl, rest: bytes, length: int) -> None:
    """Stream the POST body to PENDING through a small buffer."""
    left = min(length, MAX_BODY) - len(rest)
    with open(PENDING + ".tmp", "wb") as f:
        f.write(rest)
        while left > 0:
            chunk = cl.recv(min(512, left))
            if not chunk:
                break
            f.write(chunk)
            left -= len(chunk)

    # only a complete dump replaces the pending file
    import os
    try:
        os.remove(PENDING)
    except OSError:
        pass
    os.rename(PENDING + ".tmp", PENDING)


def handle(cl, app) -> None:
    """One request."""
    cl.settimeout(5)
    method, path, hdr, rest = read_head(cl)

    # css is public, everything else behind auth
    if path == "/s.css":
        send_file(cl, STATIC[path])
        return
    if not authed(app, hdr):
        head(cl, "401 Unauthorized", extra='WWW-Authenticate: Basic realm="PortfolioDisplay"\r\n')
        cl.write("Login required")
        return

    # save: dump the raw body to flash and reboot; net.save applies it at the next boot,
    # when the heap is nearly empty (not enough RAM to do it here)
    if method == "POST" and path == "/save":
        dump_body(cl, rest, int(hdr.get("content-length", 0) or 0))
        rest = None
        gc.collect()
        app.just_saved = True  # App.serve reboots once this module is gone
        send_file(cl, STATIC["/saved"])
        return

    # power switch: off = dark like the sleep window, kept in a flag file, applied right away
    if method == "POST" and path in ("/on", "/off"):
        import os
        app.off = path == "/off"
        try:
            if app.off:
                open("/off", "w").close()
            else:
                os.remove("/off")
        except OSError:
            pass
        app.nap_at = 0  # checked on the next loop pass
        head(cl, "200 OK", "application/json")
        cl.write('{"off":%s}' % ("true" if app.off else "false"))
        return

    # form data (own module), anything else (captive portal probes etc.) gets the form
    if path == "/cfg.json":
        from net import cfg
        cfg.send(cl, app, head)
    else:
        send_file(cl, STATIC["/"])
