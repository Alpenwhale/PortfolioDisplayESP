"""Data screens: one asset, portfolio total. Turns app state into card() calls.

Numbers come from the app's float arrays (price/base/qty/buy, NaN = not fetched yet),
names from the asset record on flash (only the one on screen is read).
The change over the configured period is always the headline, the price sits below.
"""
from ui import fmt
from ui.card import card
from ui.fmt import signed, pct, pct_unit, money_str, decimals

PERIOD = {"1d": "Today", "5d": "1 week", "ytd": "YTD", "max": "All time"}


def render(app) -> None:
    """Draw the current slide: total page first (if enabled), then the assets."""
    fmt.STYLE = app.s["numfmt"]
    if not app.n:
        app.ui.message("No assets", ["Press FLASH", "for settings"])
    elif app.slide < app.total:
        portfolio(app)
    else:
        item(app, min(app.slide - app.total, app.n - 1))


def _labels(rec: dict) -> list:
    """Name if it fits, else the id (ISIN/WKN/ticker)."""
    # yahoo pads names and appends a share class after a run of spaces ("KION GROUP AG      I")
    name = (rec.get("name") or rec.get("yname") or "").split("  ")[0].strip()
    return [name, rec.get("id", "?")] if name else [rec.get("id", "?")]


def _subs(u, lbl: str, worth: str, ch: float, gain: str, r) -> list:
    """Lines below the headline: value with trend arrow, change in money, return since purchase."""

    # small screens only fit one line, so the period label rides along with the value
    subs = [([worth + " " + lbl, worth] if u.small else [worth], u.fg, ch),
            ([gain + " " + lbl, gain], u.tone(ch), 0)]
    if r is not None:
        subs.append((["Since purchase " + pct(r), pct(r)], u.tone(r), 0))
    return subs


def item(app, i: int) -> None:
    """One asset: change in percent big, price small."""
    u, rec = app.ui, app.asset(i)
    page = (app.slide, app.pages)
    p = app.price[i]

    # no price yet (NaN != NaN): loading or the last error
    if p != p:
        msg = app.err.get(i) or "Loading..."
        card(u, _labels(rec), "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    # change over the configured period
    b, code = app.base[i], app.curs[app.cur[i]]
    dec = decimals(p)
    ch = p - b
    buy = app.buy[i]
    subs = _subs(u, PERIOD.get(app.s["period"], ""), money_str(p, code, dec), ch,
                 money_str(ch, code, dec, True), (p - buy) / buy * 100 if buy else None)
    card(u, _labels(rec), signed(ch / b * 100 if b else 0), pct_unit(), u.tone(ch), subs, page)


def portfolio(app) -> None:
    """All holdings (assets with a quantity) as one position. Arrays only, no flash reads."""
    u = app.ui
    page = (app.slide, app.pages)
    value = start = cost = paid = 0.0
    code = ""
    missing = 0

    # sum up holdings that have a price
    for i in range(app.n):
        qty, buy, p = app.qty[i], app.buy[i], app.price[i]
        if not qty:
            continue
        if p != p:
            missing += 1
            continue
        value += qty * p
        start += qty * app.base[i]
        code = code or app.curs[app.cur[i]]

        # return since purchase only over the assets that have a buy price
        if buy:
            cost += qty * buy
            paid += qty * p

    # nothing to show yet
    if not start:
        msg = "Loading..." if missing else "Add quantities"
        card(u, ["Portfolio"], "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    # same layout as an asset
    ch = value - start
    subs = _subs(u, PERIOD.get(app.s["period"], ""), money_str(value, code), ch,
                 money_str(ch, code, 2, True), (paid - cost) / cost * 100 if cost else None)
    if missing:
        subs.append((["%d price(s) missing" % missing], u.dim, 0))
    card(u, ["Portfolio"], signed(ch / start * 100), pct_unit(), u.tone(ch), subs, page)
