"""Normal mode: fetch loop, slideshow, info screen, currency conversion. Never loaded in setup mode."""
import gc
import time

import config
from core.app import later, due, drop
from net import wifi


def loop(app) -> None:
    """Connected: show the settings url briefly, then fetch + render forever."""
    app.listen()
    app.info_until = later(config.INFO_S * 1000)
    app.queue = list(range(app.n))
    app.next_fetch = later(app.s["fetch_s"] * 1000)
    app.next_slide = app.info_until

    while True:
        app.serve()
        app.button()
        app.maybe_reboot()

        # one fetch per loop pass keeps web + button responsive
        if app.queue:
            if wifi.connected():
                fetch(app, app.queue.pop(0))
        elif due(app.next_fetch):
            app.queue = list(range(app.n))
            app.next_fetch = later(app.s["fetch_s"] * 1000)
            app.fx = {}  # fresh exchange rates every cycle

        # info screen overrides everything while active
        if app.info_until and not due(app.info_until):
            if not app.info_flip or due(app.info_flip):
                info(app)
            time.sleep_ms(30)
            continue
        if app.info_until:
            app.info_until, app.dirty = 0, True

        # slideshow
        if app.s["mode"] == "slide" and app.n > 1 and due(app.next_slide):
            app.slide = (app.slide + 1) % app.n
            app.next_slide = later(app.s["slide_s"] * 1000)
            app.dirty = True

        # redraw only on change, then free all drawing code for the next TLS fetch
        if app.dirty:
            app.dirty = False
            from core import screens
            screens.render(app)
            del screens
            app.release_ui()
        time.sleep_ms(30)


def info(app) -> None:
    """Settings url page (rotates on small screens)."""
    from core import setup as s
    pages = s.info_page(app.ui, app.info_page, app.ip)
    del s
    app.release_ui()
    app.info_page = (app.info_page + 1) % pages
    app.info_flip = later(config.PAGE_S * 1000)


def fetch(app, i: int) -> None:
    """Resolve (once) + quote one asset. Keeps the last good price on errors."""
    if i >= app.n:
        return
    rec = app.asset(i)
    gc.collect()
    try:
        from net import quotes

        # isin/wkn -> yahoo symbol once, cached in the asset file
        if not rec.get("sym"):
            from net import search
            rec["sym"], rec["yname"] = search.resolve(rec["id"], rec.get("ex", "auto"))
            del search
            drop("net.search")
            _remember(i, sym=rec["sym"], yname=rec["yname"])

        # price + base for the configured period, then into the display currency
        q = convert(app, quotes, quotes.quote(rec["sym"], app.s["period"]))
        app.set_quote(i, q["p"], q["b"], q["cur"])
        if not rec.get("yname") and q["n"]:
            _remember(i, yname=q["n"])
    except Exception as e:
        print("fetch", rec.get("id"), repr(e))
        app.err[i] = str(e) or e.__class__.__name__
    finally:
        drop("net.search", "net.quotes", "data.assets")

    # redraw if this asset is on screen
    m = app.s["mode"]
    if m == "port" or (m == "slide" and app.slide == i) or (m == "single" and app.s["single"] == i):
        app.dirty = True


def _remember(i: int, **kv) -> None:
    """Write resolved fields back to the asset file (once per asset)."""
    from data import assets
    assets.update(i, **kv)


def convert(app, quotes, q: dict) -> dict:
    """Scale p/b into the display currency. FX failure -> keep native, don't lose the quote."""

    # london quotes in pence
    if q["cur"] in ("GBp", "GBX"):
        q["p"], q["b"], q["cur"] = q["p"] / 100, q["b"] / 100, "GBP"

    # nothing to do
    want = app.s["cur"]
    if want == "native" or not q["cur"] or q["cur"] == want:
        return q

    # one rate per currency per fetch cycle
    try:
        rate = app.fx.get(q["cur"])
        if rate is None:
            rate = app.fx[q["cur"]] = quotes.fx(q["cur"], want)
    except Exception as e:
        print("fx", q["cur"], want, repr(e))
        return q
    q["p"], q["b"], q["cur"] = q["p"] * rate, q["b"] * rate, want
    return q
