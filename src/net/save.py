"""Apply a saved portal form: settings, secrets and the asset file.

The portal only dumps the raw POST body to /pending.form and reboots. This runs at the
next boot (main.py), when nearly the whole heap is free; at runtime there isn't enough
RAM for this code + store + assets on top of the running app.
Rows are written to the new asset file as they are parsed, so RAM doesn't grow with the list.
"""
import gc
import os

from data import assets, store

PENDING = "/pending.form"
MODES = ("slide", "port", "single")
PERIODS = ("1d", "5d", "ytd", "max")
NUMFMTS = ("de", "en")
CURRENCIES = ("EUR", "USD", "GBP", "CHF", "JPY", "native")
ROW_FIELDS = ("id", "ex", "name", "qty", "buy", "sym", "yname")


def _cut(s, sep):
    """(before, after) at first sep. No str.partition on esp8266."""
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


def pairs(read):
    """Yield (key, value) of a urlencoded body, read in 512 byte pieces. Never holds the whole body."""
    buf = b""
    while True:

        # every complete pair right away
        while b"&" in buf:
            kv, buf = _cut(buf, b"&")
            k, v = _cut(kv.decode(), "=")
            if k:
                yield unquote(k), unquote(v).strip()

        # next piece
        chunk = read(512)
        if not chunk:
            break
        buf += chunk

    # last pair has no trailing &
    k, v = _cut(buf.decode(), "=")
    if k:
        yield unquote(k), unquote(v).strip()


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


def apply_pending(app) -> bool:
    """Boot step: apply a form saved by the portal before the last reboot. True if there was one."""
    try:
        f = open(PENDING, "rb")
    except OSError:
        return False
    try:
        with f:
            save(app, f.read)
    finally:
        os.remove(PENDING)
    return True


def save(app, read) -> None:
    """Stream the form into settings/secrets/assets."""
    s, sec = app.s, app.sec
    g = {}            # global fields, a dozen small strings
    row, idx = {}, None
    w = assets.Writer()

    # rows arrive in page order: id0 ex0 ... buy0 id1 ...; flush when the index changes
    try:
        for k, v in pairs(read):
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

    # new list = indexes moved, old prices would land on the wrong assets
    from data import prices
    prices.clear()
    gc.collect()

    # wifi, empty password field = keep the stored one
    s["ssid"] = g.get("ssid", "")
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
