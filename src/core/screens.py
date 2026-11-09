"""Data screens: one security, portfolio return. Turns app state into ui.card calls."""
from ui import fmt
from ui.fmt import signed, pct, pct_unit, money, money_str, decimals

PERIOD = {"1d": "Today", "5d": "1 week", "ytd": "YTD", "max": "All time"}


def render(app) -> None:
    """Draw whatever the current mode wants."""
    fmt.STYLE = app.s["numfmt"]
    items, mode = app.s["items"], app.s["mode"]
    if not items:
        app.ui.message("No securities", ["Press FLASH", "for settings"])
    elif mode == "port":
        portfolio(app)
    elif mode == "single":
        item(app, min(app.s["single"], len(items) - 1), True)
    else:
        item(app, app.slide % len(items), False)


def _labels(it: dict, q: dict) -> list:
    """Name if it fits, else the id (ISIN/WKN/ticker)."""
    name = it.get("name") or q.get("n") or it.get("yname") or ""
    return [name, it["id"]] if name else [it["id"]]


def item(app, i: int, ret: bool) -> None:
    """One security. ret=True: return since purchase is the headline (if a buy price is set)."""
    u, it = app.ui, app.s["items"][i]
    q = app.q.get(it["id"], {})
    page = (i, len(app.s["items"])) if app.s["mode"] == "slide" else (0, 1)

    # no price yet: loading or the last error
    if "p" not in q:
        msg = q.get("err") or "Loading..."
        u.card(_labels(it, q), "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    # change over the configured period, longest text first, ui picks what fits
    p, b, code = q["p"], q["b"], q["cur"]
    dec = decimals(p)
    ch = p - b
    ch_pct = ch / b * 100 if b else 0
    lbl = PERIOD.get(app.s["period"], "")
    change = ([pct(ch_pct) + " (" + money_str(ch, code, dec, True) + ") " + lbl,
               pct(ch_pct) + " " + lbl, pct(ch_pct)], u.tone(ch), ch)

    # single mode with buy price: return is the big number, change + price below
    buy = it.get("buy")
    if ret and buy:
        r = (p - buy) / buy * 100
        subs = [change, ([money_str(p, code, dec)], u.fg, 0)]
        u.card(_labels(it, q), signed(r), pct_unit(), u.tone(r), subs, page)
        return

    # default: price big, period change below, return since purchase if known
    subs = [change]
    if buy:
        r = (p - buy) / buy * 100
        subs.append((["Since purchase " + pct(r), pct(r)], u.tone(r), 0))
    value, unit = money(p, code, dec)
    u.card(_labels(it, q), value, unit, u.tone(ch), subs, page)


def portfolio(app) -> None:
    """Total return over all items with qty + buy price."""
    u = app.ui
    value = cost = 0.0
    code = ""
    missing = 0

    # sum up holdings that have a price
    for it in app.s["items"]:
        if not (it.get("qty") and it.get("buy")):
            continue
        q = app.q.get(it["id"], {})
        if "p" not in q:
            missing += 1
            continue
        value += it["qty"] * q["p"]
        cost += it["qty"] * it["buy"]
        code = code or q["cur"]

    # nothing to show yet
    if not cost:
        msg = "Loading..." if missing else "Add qty + buy price"
        u.card(["Portfolio"], "-", "", u.dim, [([msg], u.dim, 0)])
        return

    # return big, gain with arrow, then total value
    gain = value - cost
    r = gain / cost * 100
    worth = money_str(value, code)
    subs = [([money_str(gain, code, 2, True)], u.tone(gain), gain), (["Value " + worth, worth], u.fg, 0)]
    if missing:
        subs.append((["%d price(s) missing" % missing], u.dim, 0))
    u.card(["Portfolio"], signed(r), pct_unit(), u.tone(r), subs)
