"""ISIN/WKN -> Yahoo symbol. Needed once per asset, so it lives apart from net.quotes (RAM).

ISIN: Yahoo search. WKN: Yahoo doesn't know them, so German ones are turned into their ISIN
(DE000 + WKN + check digit); foreign funds (e.g. IE...) need the ISIN. OpenFIGI would know
WKNs, but its TLS (ECDHE only) fails on the ESP8266 (-40), and it doesn't allow browser CORS.
Self-contained on purpose: during its TLS handshake net.quotes must not be loaded too.
"""
import requests

_HDR = {"User-Agent": "Mozilla/5.0"}  # yahoo 429s without one
_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search?q=%s&quotesCount=10&newsCount=0&listsCount=0"
AUTO = (".DE", ".F")  # "auto" exchange prefers Xetra, then Frankfurt


def _q(s: str) -> str:
    """Minimal url-encode."""
    return s.replace("%", "%25").replace(" ", "%20").replace("&", "%26")


def _open(url: str):
    """GET, raises OSError on non-200. Caller closes."""
    r = requests.get(url, headers=_HDR, timeout=10)
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


def _pairs(r):
    """Yield (key, value) bytes of every "key":"value" string pair in a streamed json body."""
    buf = b""
    for c in _chunks(r):
        buf += c

        # complete pairs right away
        while True:
            i = buf.find(b'":"')
            j = buf.find(b'"', i + 3) if i >= 0 else -1
            if j < 0:
                break
            k = buf.rfind(b'"', 0, i)
            yield buf[k + 1:i], buf[i + 3:j]
            buf = buf[j + 1:]

        # unfinished pair stays, junk gets dropped
        if len(buf) > 512:
            buf = buf[-128:]


def _yahoo_hits(ident: str) -> list:
    """[(symbol, name)] from Yahoo's search. Works for ISINs and tickers, not for WKNs."""
    out, name = [], b""
    r = _open(_SEARCH % _q(ident))
    try:
        for key, val in _pairs(r):
            if key == b"shortname":
                name = val
            elif key == b"symbol":
                out.append((val.decode(), name.decode()))
                name = b""
    finally:
        r.close()
    return out


def wkn_to_isin(wkn: str) -> str:
    """German securities: ISIN = DE000 + WKN + check digit (Luhn over the letters-as-numbers)."""
    base = "DE000" + wkn
    digits = "".join(str(int(c, 36)) for c in base)

    # luhn: double every second digit from the right
    total = 0
    for k, ch in enumerate(reversed(digits)):
        n = int(ch) * (2 if k % 2 == 0 else 1)
        total += n // 10 + n % 10
    return base + str((10 - total % 10) % 10)


def resolve(ident: str, ex: str = "auto") -> tuple:
    """ISIN/WKN/ticker + exchange -> (yahoo symbol, name)."""

    # plain tickers: optionally glue the exchange suffix on
    if not is_code(ident):
        if "." in ident or ex in ("auto", "US"):
            return ident, ""
        return ident + ex, ""

    # yahoo doesn't know WKNs: try the German ISIN built from it (works for DE securities only)
    if len(ident) == 12:
        hits = _yahoo_hits(ident)
    else:
        hits = _yahoo_hits(wkn_to_isin(ident))
        if not hits:
            raise OSError("WKN: use the ISIN")
    if not hits:
        raise OSError("not found")

    if ex == "auto":
        for suf in AUTO:
            for h in hits:
                if h[0].endswith(suf):
                    return h
        return hits[0]
    for h in hits:
        if (ex == "US" and "." not in h[0]) or (ex != "US" and h[0].endswith(ex)):
            return h
    raise OSError("not on this exchange")
