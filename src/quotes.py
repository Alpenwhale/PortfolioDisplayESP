"""Yahoo Finance, public, no key. Imported on demand and unloaded after, RAM is tight."""
import requests

_HDR = {"User-Agent": "Mozilla/5.0"}  # yahoo 429s without one
_SEARCH = "https://query2.finance.yahoo.com/v1/finance/search?q=%s&quotesCount=6&newsCount=0&listsCount=0"
_CHART = "https://query1.finance.yahoo.com/v8/finance/chart/%s?range=1d&interval=1d"
PREFER = (".DE", ".F")  # xetra, frankfurt -> EUR prices


def _q(s: str) -> str:
    """Minimal url-encode for tickers like ^GDAXI or BTC-EUR."""
    return s.replace("%", "%25").replace("^", "%5E").replace(" ", "%20").replace("&", "%26")


def _get(url: str) -> dict:
    """GET + json, raises OSError on HTTP errors."""
    r = requests.get(url, headers=_HDR)
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d" % r.status_code)
        return r.json()
    finally:
        r.close()


def is_code(ident: str) -> bool:
    """ISIN (12, CC + 9 + check digit) or WKN (6 alnum with a digit)."""
    if len(ident) == 12 and ident[:2].isalpha() and ident[-1].isdigit():
        return True
    return len(ident) == 6 and "." not in ident and any(c.isdigit() for c in ident)


def resolve(ident: str) -> tuple:
    """ISIN/WKN -> (symbol, name). Tickers pass through, name filled by quote()."""
    if not is_code(ident):
        return ident, ""
    hits = _get(_SEARCH % _q(ident)).get("quotes") or []
    if not hits:
        raise OSError("nicht gefunden")
    best = hits[0]
    for suf in PREFER:
        m = [h for h in hits if h.get("symbol", "").endswith(suf)]
        if m:
            best = m[0]
            break
    return best["symbol"], best.get("shortname") or best.get("longname") or ""


def quote(sym: str) -> dict:
    """{p: price, c: prev close, cur: currency, n: name}."""
    m = _get(_CHART % _q(sym))["chart"]["result"][0]["meta"]
    return {
        "p": m["regularMarketPrice"],
        "c": m.get("chartPreviousClose") or m.get("previousClose") or m["regularMarketPrice"],
        "cur": m.get("currency", ""),
        "n": m.get("shortName") or m.get("longName") or "",
    }
