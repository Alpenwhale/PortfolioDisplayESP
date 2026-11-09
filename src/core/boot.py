"""Start decision: setup mode or normal mode. Runs once, main.py unloads it afterwards."""
import gc
import time

import config
from net import wifi


def decide(app) -> tuple:
    """(setup?, reason). Joins the home wifi on the way if possible."""
    u = app.ui
    u.message("PortfolioDisplay", ["Starting..."])

    # FLASH pressed during the first 2 s -> setup mode (also how you get past a portal password)
    setup = False
    for _ in range(20):
        if not app.btn.value():
            setup = True
            break
        time.sleep_ms(100)
    reason = "FLASH pressed" if setup else ""

    # no wifi yet / wifi down -> setup mode
    if not setup and not app.s["ssid"]:
        setup, reason = True, "no Wi-Fi set"
    if not setup:
        u.message("Connecting", [app.s["ssid"]])
        app.ip = wifi.sta(app.s["ssid"], app.sec.get("pw", ""), config.WIFI_TIMEOUT_S)
        if not app.ip:
            setup, reason = True, "Wi-Fi not found"

    # wait for the button release so it isn't read as a reset hold
    while not app.btn.value():
        time.sleep_ms(50)
    gc.collect()
    return setup, reason
