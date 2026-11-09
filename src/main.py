"""Entry point. Builds the display, applies a pending save, decides the mode, hands over.

One-shot code (display factory, save, boot decision) is unloaded before the long-running
loop starts, every KB counts on the ESP8266.
"""
import os
import sys

import config

# display driver, then forget the factory
from display import create_display
d = create_display(config)
del create_display
sys.modules.pop("display", None)

# shared state
from core.app import App, drop
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

# setup or normal? boot code goes away afterwards
from core import boot
setup, reason = boot.decide(app)
del boot
drop("core.boot")

# setup: open the AP, drop the setup code, loop in the app (pages load per flip)
if setup:
    from core import setup as mode
    ssid, pw = mode.start(app)
    del mode
    drop("core.setup")
    app.setup_loop(ssid, pw, reason)

# normal mode
from core import run as mode
mode.loop(app)
