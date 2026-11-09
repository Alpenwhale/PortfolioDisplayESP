"""Entry point. Kept tiny: one-shot start code lives in core.boot and is unloaded before the loop."""
from core import boot
app, reason = boot.start()
del boot
from core.app import drop
drop("core.boot")

# setup mode (never returns) or normal mode
if reason:
    from core import setup as mode
    mode.run(app, reason)
from core import run as mode
mode.loop(app)
