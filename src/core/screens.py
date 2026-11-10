"""Data screens: one asset, portfolio return. Turns app state into card() calls.

Numbers come from the app's float arrays (price/base/qty/buy, NaN = not fetched yet),
names from the asset record on flash (only the one on screen is read).
"""
from ui import fmt
from ui.card import card
from ui.fmt import signed, pct, pct_unit, money, money_str, decimals

PERIOD = {"1d": "Today", "5d": "1 week", "ytd": "YTD", "max": "All time"}


def render(app) -> None:
    """Draw whatever the current mode wants."""
    fmt.STYLE = app.s["numfmt"]
    mode = app.s["mode"]
    if not app.n:
        app.ui.message("No assets", ["Press FLASH", "for settings"])
    elif mode == "port":
        portfolio(app)
    elif mode == "single":
        item(app, min(app.s["single"], app.n - 1), True)
    else:
        item(app, app.slide % app.n, False)


def _labels(rec: dict) -> list:
    """Name if it fits, else the id (ISIN/WKN/ticker)."""
    # yahoo pads names and appends a share class after a run of spaces ("KION GROUP AG      I")
    name = (rec.get("name") or rec.get("yname") or "").split("  ")[0].strip()
    return [name, rec.get("id", "?")] if name else [rec.get("id", "?")]


def item(app, i: int, ret: bool) -> None:
    """One asset. ret=True: return since purchase is the headline (if a buy price is set)."""
    u, rec = app.ui, app.asset(i)
    page = (i, app.n) if app.s["mode"] == "slide" else (0, 1)
    p = app.price[i]

    # no price yet (NaN != NaN): loading or the last error
    if p != p:
        msg = app.err.get(i) or "Loading..."
        card(u, _labels(rec), "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    # change over the configured period, longest text first, ui picks what fits
    b, code = app.base[i], app.curs[app.cur[i]]
    dec = decimals(p)
    ch = p - b
    ch_pct = ch / b * 100 if b else 0
    lbl = PERIOD.get(app.s["period"], "")
    change = ([pct(ch_pct) + " (" + money_str(ch, code, dec, True) + ") " + lbl,
               pct(ch_pct) + " " + lbl, pct(ch_pct)], u.tone(ch), ch)

    # single mode with buy price: return is the big number, change + price below
    buy = app.buy[i]
    if ret and buy:
        r = (p - buy) / buy * 100
        subs = [change, ([money_str(p, code, dec)], u.fg, 0)]
        card(u, _labels(rec), signed(r), pct_unit(), u.tone(r), subs, page)
        return

    # default: price big, period change below, return since purchase if known
    subs = [change]
    if buy:
        r = (p - buy) / buy * 100
        subs.append((["Since purchase " + pct(r), pct(r)], u.tone(r), 0))
    value, unit = money(p, code, dec)
    card(u, _labels(rec), value, unit, u.tone(ch), subs, page)


def portfolio(app) -> None:
    """Total return over all assets with qty + buy price. Arrays only, no flash reads."""
    u = app.ui
    value = cost = 0.0
    code = ""
    missing = 0

    # sum up holdings that have a price
    for i in range(app.n):
        qty, buy, p = app.qty[i], app.buy[i], app.price[i]
        if not (qty and buy):
            continue
        if p != p:
            missing += 1
            continue
        value += qty * p
        cost += qty * buy
        code = code or app.curs[app.cur[i]]

    # nothing to show yet
    if not cost:
        msg = "Loading..." if missing else "Add qty + buy price"
        card(u, ["Portfolio"], "-", "", u.dim, [([msg], u.dim, 0)])
        return

    # return big, gain with arrow, then total value
    gain = value - cost
    r = gain / cost * 100
    worth = money_str(value, code)
    subs = [([money_str(gain, code, 2, True)], u.tone(gain), gain), (["Value " + worth, worth], u.fg, 0)]
    if missing:
        subs.append((["%d price(s) missing" % missing], u.dim, 0))
    card(u, ["Portfolio"], signed(r), pct_unit(), u.tone(r), subs)
