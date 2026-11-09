"""Entry point. Builds the display, decides the mode, hands over. Never returns.

One-shot code (display factory, boot decision) is unloaded before the long-running
loop starts, every KB counts on the ESP8266.
"""
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

# setup or normal? boot code goes away afterwards
from core import boot
setup, reason = boot.decide(app)
del boot
drop("core.boot")

# each mode loads only its own code
if setup:
    from core import setup as mode
    mode.run(app, reason)
from core import run as mode
mode.loop(app)
