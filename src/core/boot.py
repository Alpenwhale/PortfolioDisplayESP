"""Everything that runs once per boot. main.py unloads this module before the long-running loop.

Warm boot (after a refresh soft reset): re-attach the display without init (image stays),
load app state, straight into normal mode.
Cold boot: init display, apply a pending portal save, setup decision, join wifi, then a
first refresh soft reset to fetch prices with an empty heap.
"""
import os
import sys
import time

import config


def start(state):
    """(app, reason). reason '' = normal mode, else why we go into setup mode."""
    from core.app import App, drop
    warm = state is not None

    # display driver: warm = attach only, the panel keeps its image
    from display import create_display
    d = create_display(config, init=not warm)
    del create_display
    sys.modules.pop("display", None)
    app = App(d)
    del d

    # warm: carry the slideshow position over, done
    if warm:
        import network
        app.ip = network.WLAN(network.STA_IF).ifconfig()[0]
        app.slide = state.get("s", 0)
        app.offset = state.get("o", 0)
        app.cycle = state.get("c", 0)
        app.show_info = state.get("i", 0)
        app.t_refresh = state.get("t")  # when the screen froze, run.thawed() measures from here
        return app, ""

    # portal form saved before the last reboot? apply it now, the heap is still nearly empty
    try:
        os.stat("/pending.form")
        pending = True
    except OSError:
        pending = False
    if pending:
        app.message("Saving", ["Applying settings..."])

        # a broken form must not stop the boot; the file is removed either way
        try:
            from net import save
            save.apply_pending(app)
            del save
        except Exception as e:
            print("apply failed:", repr(e))
        drop("net.save", "data.store", "data.assets", "data.prices")

    # FLASH pressed during the first 2 s -> setup mode (also how you get past a portal password)
    app.message("PortfolioDisplay", ["Starting..."])
    reason = ""
    for _ in range(20):
        if not app.btn.value():
            reason = "FLASH pressed"
            break
        time.sleep_ms(100)

    # no wifi yet / wifi down -> setup mode
    if not reason and not app.s["ssid"]:
        reason = "no Wi-Fi set"
    if not reason:
        app.message("Connecting", [app.s["ssid"]])
        from net import wifi
        app.ip = wifi.sta(app.s["ssid"], app.sec.get("pw", ""), config.WIFI_TIMEOUT_S)
        del wifi
        drop("net.wifi")
        if not app.ip:
            reason = "Wi-Fi not found"

    # wait for the button release so it isn't read as a reset hold
    while not app.btn.value():
        time.sleep_ms(50)

    # connected: first prices via a refresh soft reset (this message stays up meanwhile).
    # without assets there's nothing to fetch, go straight to the loop + settings url
    if not reason and app.n:
        app.message("Loading prices", [])
        app.refresh(info=1)
    app.show_info = 1
    return app, reason
