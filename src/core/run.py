"""Normal mode loop: slideshow, info screen, web, button. No TLS here.

Prices come from /prices.bin (core.fetch, warm boot). When the refresh interval is up,
app.refresh() soft-resets into the next fetch phase; the screen stays frozen meanwhile.
"""
import gc
import time

import config
from core.app import later, due, drop


def every(app, frozen: int = 0) -> int:
    """Refresh interval in ms: the configured one, but at least one full slideshow pass
    and FREEZE_FACTOR x the measured freeze (else the screen would be frozen most of the time)."""
    s = app.s
    show = (app.total * s["total_s"] + (app.pages - app.total) * s["slide_s"]) * 1000 if app.pages > 1 else 0
    return max(s["fetch_s"] * 1000, show, config.FREEZE_FACTOR * frozen)


def thawed(app) -> None:
    """First new image after a refresh: measure the freeze, schedule the next refresh from it.

    The interval runs from refresh to refresh (so it includes the reboot + fetch).
    """
    if app.t_refresh is None:
        return
    frozen = time.ticks_diff(time.ticks_ms(), app.t_refresh)
    ms = every(app, frozen)
    app.next_fetch = time.ticks_add(app.t_refresh, ms)
    app.t_refresh = None
    print("frozen %d ms, next refresh every %d s" % (frozen, ms // 1000))


def loop(app) -> None:
    """Never returns."""
    print("loop: assets", app.n, "ip", app.ip)
    app.listen()
    app.info_until = later(config.INFO_S * 1000) if app.show_info else 0
    app.slide %= max(1, app.pages)
    app.next_fetch = later(every(app))
    app.next_slide = later(app.slide_ms())
    app.asleep = False

    while True:
        app.serve()
        app.button()
        app.maybe_reboot()

        # sleep window + power switch, checked twice a minute or right after the switch
        if not app.nap_at or due(app.nap_at):
            app.nap_at = later(30000)
            nap(app)

        # refresh interval up -> fetch phase (not while the info screen, a button press, a reboot or
        # the settings page is pending: the soft reset drops the web server)
        if app.web_until and due(app.web_until):
            app.web_until = 0
        if app.n and due(app.next_fetch) and not (app.info_until or app._reboot or app._press or app.web_until
                                                  or app.asleep):
            app.refresh()

        # info screen overrides everything while active
        if app.info_until and not due(app.info_until):
            if not app.info_flip or due(app.info_flip):
                info(app)
            time.sleep_ms(30)
            continue
        if app.info_until:
            app.info_until, app.dirty = 0, True

        # asleep: screen stays dark, nothing to draw
        if app.asleep:
            if app.dirty:
                app.dirty = False
                app.d.fill(0)
                app.d.show()
            time.sleep_ms(30)
            continue

        # slideshow
        if app.pages > 1 and due(app.next_slide):
            app.slide = (app.slide + 1) % app.pages
            app.next_slide = later(app.slide_ms())
            app.dirty = True

        # redraw only on change, then free all drawing code again
        if app.dirty:
            app.dirty = False
            from core import screens
            screens.render(app)
            del screens
            app.release_ui()
            print("draw", app.slide, "free", gc.mem_free())
            thawed(app)
        time.sleep_ms(30)


def nap(app) -> None:
    """Enter / leave the sleep window or the off state: screen dark (backlight / OLED off if
    possible), no refresh."""
    now = app.off
    if not now:
        from core import clock
        now = clock.asleep(app.s)
        del clock
        drop("core.clock")
    if now == app.asleep:
        return
    app.asleep = now
    print("sleep" if now else "wake")

    # dark screen; on waking redraw and get fresh prices right away
    app.d.power(not now)
    app.dirty = True
    if not now:
        app.next_fetch = later(0)


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
