"""Data screens: one asset, portfolio total. Turns app state into card() calls.

Numbers come from the app's float arrays (price/base/qty/buy, NaN = not fetched yet),
names from the asset record on flash (only the one on screen is read).
Both pages look the same: change over the configured period as the headline, price/value
below, then the change in money and (optional) the own performance since purchase.
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


def _since(app, gain: float, cost: float, code: str, dec: int, partial: bool):
    """Own performance since purchase as sub line, None if switched off or unknown.

    gain/cost in money. * = not every asset had the values for it (qty + buy price).
    """
    if not app.s["show_gain"] or not cost:
        return None
    s = (money_str(gain, code, dec, True) if app.s["gain"] == "abs" else pct(gain / cost * 100)) + \
        ("*" if partial else "")
    return ["Since purchase " + s, s], app.ui.tone(gain), 0


def _card(app, labels: list, ch: float, start: float, worth: str, gain: str, since, page: tuple,
          extra=None) -> None:
    """Shared layout: headline = change in % over the period, value with arrow, change in money, own performance."""
    u = app.ui
    lbl = PERIOD.get(app.s["period"], "")

    # small screens only fit one line, so the period label rides along with the value
    subs = [([worth + " " + lbl, worth] if u.small else [worth], u.fg, ch),
            ([gain + " " + lbl, gain], u.tone(ch), 0)]
    if since:
        subs.append(since)
    if extra:
        subs.append(extra)
    card(u, labels, signed(ch / start * 100 if start else 0), pct_unit(), u.tone(ch), subs, page)


def item(app, i: int) -> None:
    """One asset."""
    u, rec = app.ui, app.asset(i)
    page = (app.slide, app.pages)
    p = app.price[i]

    # no price yet (NaN != NaN): loading or the last error
    if p != p:
        msg = app.err.get(i) or "Loading..."
        card(u, _labels(rec), "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    # amount needs the quantity, without it the per-unit gain is shown (marked)
    b, code = app.base[i], app.curs[app.cur[i]]
    dec = decimals(p)
    buy, qty = app.buy[i], app.qty[i]
    k = qty or 1
    since = _since(app, (p - buy) * k, buy * k, code, dec, app.s["gain"] == "abs" and not qty) if buy else None
    _card(app, _labels(rec), p - b, b, money_str(p, code, dec), money_str(p - b, code, dec, True), since, page)


def portfolio(app) -> None:
    """All holdings as one position, same layout as an asset. Arrays only, no flash reads."""
    u = app.ui
    page = (app.slide, app.pages)
    value = start = cost = paid = 0.0
    code = ""
    missing = 0
    partial = False

    # assets without qty (period change) or buy price (own performance) are left out, * marks that
    for i in range(app.n):
        qty, buy, p = app.qty[i], app.buy[i], app.price[i]
        if not (qty and buy):
            partial = True
        if not qty:
            continue
        if p != p:
            missing += 1
            continue

        # no exchange rate this time: never add up two currencies
        c = app.curs[app.cur[i]]
        if code and c != code:
            partial = True
            continue
        code = c
        value += qty * p
        start += qty * app.base[i]
        if buy:
            cost += qty * buy
            paid += qty * p

    # nothing to show yet
    if not start:
        msg = "Loading..." if missing else "Add quantities"
        card(u, ["Portfolio"], "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    ch = value - start
    since = _since(app, paid - cost, cost, code, 2, partial)
    extra = (["%d price(s) missing" % missing], u.dim, 0) if missing else None
    _card(app, ["Portfolio"], ch, start, money_str(value, code), money_str(ch, code, 2, True), since, page, extra)
