"""Normal mode loop: slideshow, info screen, web, button. No TLS here.

Prices come from /prices.bin (core.fetch, warm boot). When the refresh interval is up,
app.refresh() soft-resets into the next fetch phase; the screen stays frozen meanwhile.
"""
import gc
import time

import config
from core.app import later, due


def thawed(app) -> None:
    """First new image after a refresh: measure the freeze, schedule the next refresh from it.

    The configured interval runs from refresh to refresh (so it includes the reboot + fetch).
    Lower limit: FREEZE_FACTOR x the measured freeze, else a long asset list on a short
    interval would leave the screen frozen most of the time.
    """
    if app.t_refresh is None:
        return
    frozen = time.ticks_diff(time.ticks_ms(), app.t_refresh)
    every = max(app.s["fetch_s"] * 1000, config.FREEZE_FACTOR * frozen)
    app.next_fetch = time.ticks_add(app.t_refresh, every)
    app.t_refresh = None
    print("frozen %d ms, next refresh every %d s" % (frozen, every // 1000))


def loop(app) -> None:
    """Never returns."""
    print("loop: assets", app.n, "ip", app.ip)
    app.listen()
    app.info_until = later(config.INFO_S * 1000) if app.show_info else 0
    app.next_fetch = later(app.s["fetch_s"] * 1000)
    app.next_slide = later(app.s["slide_s"] * 1000)

    while True:
        app.serve()
        app.button()
        app.maybe_reboot()

        # refresh interval up -> fetch phase (not while the info screen, a button press or a reboot is pending)
        if app.n and due(app.next_fetch) and not (app.info_until or app._reboot or app._press):
            app.refresh()

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

        # redraw only on change, then free all drawing code again
        if app.dirty:
            app.dirty = False
            from core import screens
            screens.render(app)
            del screens
            app.release_ui()
            print("draw", app.s["mode"], app.slide, "free", gc.mem_free())
            thawed(app)
        time.sleep_ms(30)


def info(app) -> None:
    """Settings url page (rotates on small screens)."""
    from core import setup as s
    pages = s.info_page(app.ui, app.info_page, app.ip)
    del s
    app.release_ui()
    print("info page", app.info_page)
    thawed(app)

    # a single page (big screens) is drawn once, small screens rotate
    app.info_page = (app.info_page + 1) % pages
    app.info_flip = later(config.PAGE_S * 1000 if pages > 1 else 3600000)
