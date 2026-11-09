"""Yahoo Finance quotes, public, no key. Imported per fetch and unloaded after, RAM is tight.

Symbol lookup (ISIN/WKN search) lives in net.search, it's needed only once per asset.
Responses are scanned while streaming instead of json-parsing them whole:
a 'max' chart is tens of KB, the ESP8266 has only a few KB left during TLS.
"""
import json
import requests

_HDR = {"User-Agent": "Mozilla/5.0"}  # yahoo 429s without one
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=%s"

# period -> (range, interval). coarse intervals keep the payload small.
RANGES = {"1d": ("1d", "1d"), "5d": ("5d", "1d"), "ytd": ("ytd", "1mo"), "max": ("max", "3mo")}


def _q(s: str) -> str:
    """Minimal url-encode for tickers like ^GDAXI or BTC-EUR."""
    return s.replace("%", "%25").replace("^", "%5E").replace(" ", "%20").replace("&", "%26")


def _open(url: str):
    """GET, raises OSError on non-200. Caller closes."""
    r = requests.get(url, headers=_HDR)
    if r.status_code != 200:
        r.close()
        raise OSError("HTTP %d" % r.status_code)
    return r


def _chunks(r, n: int = 256):
    """Body in small pieces straight off the TLS socket."""
    while True:
        c = r.raw.read(n)
        if not c:
            return
        yield c


def _obj_end(buf: bytes, i: int) -> int:
    """Index after the {...} starting at buf[i], -1 if not complete yet."""
    depth, in_str, esc = 0, False, False
    for j in range(i, len(buf)):
        c = buf[j]
        if in_str:
            if esc:
                esc = False
            elif c == 92:      # backslash
                esc = True
            elif c == 34:      # quote
                in_str = False
        elif c == 34:
            in_str = True
        elif c == 123:         # {
            depth += 1
        elif c == 125:         # }
            depth -= 1
            if not depth:
                return j + 1
    return -1


def _first_open(tail: bytes):
    """First non-null number of an '"open":[' array tail, None if none."""
    end = tail.find(b"]")
    toks = (tail[:end] if end >= 0 else tail).split(b",")
    if end < 0:
        toks = toks[:-1]  # last one may be cut off
    for t in toks:
        t = t.strip()
        if t and t != b"null":
            return float(t)
    return None


def _chart(r, want_open: bool) -> tuple:
    """(meta dict, first open or None) from a streamed chart response."""
    buf, meta = b"", None
    for c in _chunks(r):
        buf += c

        # meta object comes first, cut it out and parse just that
        if meta is None:
            i = buf.find(b'"meta":')
            if i < 0:
                buf = buf[-8:]
                continue
            j = _obj_end(buf, i + 7)
            if j < 0:
                if len(buf) > 6000:
                    raise OSError("response too big")
                continue
            meta = json.loads(buf[i + 7:j])
            buf = buf[j:]
            if not want_open:
                return meta, None

        # 'max' needs the very first open of the series
        k = buf.find(b'"open":[')
        if k < 0:
            buf = buf[-8:]
            continue
        tail = buf[k + 8:]
        if b"]" in tail or len(tail) > 200:
            return meta, _first_open(tail)
        buf = buf[k:]

    if meta is None:
        raise OSError("no data")
    return meta, None


def fx(src: str, dst: str) -> float:
    """Price of 1 src in dst, via yahoo's SRCDST=X pairs."""
    return quote(src + dst + "=X")["p"]


def quote(sym: str, period: str = "1d") -> dict:
    """{p: price, b: base price for the period, cur, n: name}."""
    rng, iv = RANGES.get(period, RANGES["1d"])
    r = _open(_CHART % (_q(sym), rng, iv))
    try:
        meta, first = _chart(r, period == "max")
    finally:
        r.close()

    # chartPreviousClose = close right before the range -> day/week/ytd base
    p = meta["regularMarketPrice"]
    base = first if period == "max" else meta.get("chartPreviousClose") or meta.get("previousClose")
    return {
        "p": p,
        "b": base or p,
        "cur": meta.get("currency", ""),
        "n": meta.get("shortName") or meta.get("longName") or "",
    }

