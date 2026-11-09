"""Data screens: one security, portfolio return. Turns app state into ui.card calls."""
from ui.fmt import num, signed, pct, cur, decimals

PERIOD = {"1d": "Heute", "5d": "1 Woche", "ytd": "YTD", "max": "Gesamt"}


def render(app) -> None:
    """Draw whatever the current mode wants."""
    items, mode = app.s["items"], app.s["mode"]
    if not items:
        app.ui.message("Keine Werte", ["FLASH kurz = Adresse"])
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
    """One security. ret=True: return since buy is the headline (if a buy price is set)."""
    u, it = app.ui, app.s["items"][i]
    q = app.q.get(it["id"], {})
    page = (i, len(app.s["items"])) if app.s["mode"] == "slide" else (0, 1)

    # no price yet: loading or the last error
    if "p" not in q:
        msg = q.get("err") or "Lade Kurs..."
        u.card(_labels(it, q), "-", "", u.dim, [([msg], u.dim, 0)], page)
        return

    # change over the configured period, longest text first, ui picks what fits
    p, b, unit = q["p"], q["b"], cur(q["cur"])
    dec = decimals(p)
    ch = p - b
    ch_pct = ch / b * 100 if b else 0
    lbl = PERIOD.get(app.s["period"], "")
    change = ([pct(ch_pct) + " (" + signed(ch, dec) + " " + unit + ") " + lbl,
               pct(ch_pct) + " " + lbl, pct(ch_pct)], u.tone(ch), ch)

    # single mode with buy price: return is the big number, price + change below
    buy = it.get("buy")
    if ret and buy:
        r = (p - buy) / buy * 100
        subs = [change, ([num(p, dec) + " " + unit], u.fg, 0)]
        u.card(_labels(it, q), signed(r), "%", u.tone(r), subs, page)
        return

    # default: price big, period change below, return since buy if known
    subs = [change]
    if buy:
        r = (p - buy) / buy * 100
        subs.append((["Seit Kauf " + pct(r), pct(r)], u.tone(r), 0))
    u.card(_labels(it, q), num(p, dec), unit, u.tone(ch), subs, page)


def portfolio(app) -> None:
    """Total return over all items with qty + buy price."""
    u = app.ui
    value = cost = 0.0
    unit = ""
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
        unit = unit or cur(q["cur"])

    # nothing to show yet
    if not cost:
        msg = "Lade Kurse..." if missing else "Stück + Kaufkurs fehlen"
        u.card(["Portfolio"], "-", "", u.dim, [([msg], u.dim, 0)])
        return

    # return big, gain with arrow, then total value
    gain = value - cost
    r = gain / cost * 100
    subs = [([signed(gain) + " " + unit], u.tone(gain), gain), (["Wert " + num(value) + " " + unit,
                                                                num(value) + " " + unit], u.fg, 0)]
    if missing:
        subs.append((["%d Kurs(e) fehlen" % missing], u.dim, 0))
    u.card(["Portfolio"], signed(r), "%", u.tone(r), subs)
