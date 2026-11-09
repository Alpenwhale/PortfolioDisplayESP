"""ISIN/WKN -> Yahoo symbol. Needed once per asset, so it lives apart from net.quotes (RAM)."""
from net.quotes import _open, _q, _chunks

_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search?q=%s&quotesCount=10&newsCount=0&listsCount=0"
AUTO = (".DE", ".F")  # "auto" exchange prefers Xetra, then Frankfurt


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
