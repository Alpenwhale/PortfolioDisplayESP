"""Everything that runs once at power-up. main.py unloads this module before the long-running loop.

Display + app state, a pending portal save, then the decision: setup mode or normal mode.
"""
import os
import sys
import time

import config


def start():
    """(app, reason). reason '' = normal mode, else why we go into setup mode."""
    from core.app import App, drop

    # display driver, then forget the factory
    from display import create_display
    d = create_display(config)
    del create_display
    sys.modules.pop("display", None)

    # shared state
    app = App(d)
    del d

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
        drop("net.save", "data.store", "data.assets")
        app.load_assets()

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
    return app, reason
