"""Yahoo Finance, public, no key. Imported on demand and unloaded after, RAM is tight.

Responses are scanned while streaming instead of json-parsing them whole:
a 'max' chart is tens of KB, the ESP8266 has ~15 KB left during TLS.
"""
import json
import requests

_HDR = {"User-Agent": "Mozilla/5.0"}  # yahoo 429s without one
_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search?q=%s&quotesCount=10&newsCount=0&listsCount=0"
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=%s&interval=%s"

# period -> (range, interval). coarse intervals keep the payload small.
RANGES = {"1d": ("1d", "1d"), "5d": ("5d", "1d"), "ytd": ("ytd", "1mo"), "max": ("max", "3mo")}

# exchange = yahoo suffix (list lives in net.portal). "auto" prefers german venues.
AUTO = (".DE", ".F")


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


def is_code(ident: str) -> bool:
    """ISIN (12, CC + 9 + check digit) or WKN (6 alnum with a digit)."""
    if len(ident) == 12 and ident[:2].isalpha() and ident[-1].isdigit():
        return True
    return len(ident) == 6 and "." not in ident and any(c.isdigit() for c in ident)


def _hits(r) -> list:
    """[(symbol, shortname)] from a search response, streamed."""
    out, name, buf = [], b"", b""
    for c in _chunks(r):
        buf += c

        # walk "key":"value" pairs, keep only what we need
        while True:
            i = buf.find(b'":"')
            j = buf.find(b'"', i + 3) if i >= 0 else -1
            if j < 0:
                break
            k = buf.rfind(b'"', 0, i)
            key, val = buf[k + 1:i], buf[i + 3:j]
            if key == b"shortname":
                name = val
            elif key == b"symbol":
                out.append((val.decode(), name.decode()))
                name = b""
            buf = buf[j + 1:]

        # unfinished pair stays, junk gets dropped
        if len(buf) > 512:
            buf = buf[-128:]
    return out


def resolve(ident: str, ex: str = "auto") -> tuple:
    """ISIN/WKN/ticker + exchange -> (yahoo symbol, name)."""

    # plain tickers: optionally glue the exchange suffix on
    if not is_code(ident):
        if "." in ident or ex in ("auto", "US"):
            return ident, ""
        return ident + ex, ""

    # codes: yahoo search, then pick the listing on the wanted exchange
    r = _open(_SEARCH % _q(ident))
    try:
        hits = _hits(r)
    finally:
        r.close()
    if not hits:
        raise OSError("nicht gefunden")

    if ex == "auto":
        for suf in AUTO:
            for h in hits:
                if h[0].endswith(suf):
                    return h
        return hits[0]
    for h in hits:
        if (ex == "US" and "." not in h[0]) or (ex != "US" and h[0].endswith(ex)):
            return h
    raise OSError("nicht an dieser Börse")


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
                    raise OSError("meta zu gross")
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
        raise OSError("keine Daten")
    return meta, None


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
