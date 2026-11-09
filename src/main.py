"""Entry point. Kept tiny: one-shot code lives in core.fetch / core.boot and is unloaded after.

Warm boot (refresh soft reset, marked in RTC memory): fetch prices first with an empty heap,
the display isn't touched and keeps its image. Cold boot: normal start, see core.boot.
"""
import machine
import sys

# warm boot? RTC memory survives the soft reset: b"W" + json state
rtc = machine.RTC()
raw = rtc.memory()
state = None
if raw[:1] == b"W":
    import json
    state = json.loads(raw[1:])
    rtc.memory(b"")
    try:
        from core import fetch
        state = fetch.run(state)
        del fetch
    except Exception as e:
        print("fetch phase:", repr(e))
    sys.modules.pop("core.fetch", None)
    sys.modules["core"].__dict__.pop("fetch", None)
del rtc, raw

# display + app (+ on cold boot: pending save, setup decision, first refresh)
from core import boot
app, reason = boot.start(state)
del boot, state
from core.app import drop
drop("core.boot")

# setup mode (never returns) or normal mode
if reason:
    from core import setup as mode
    mode.run(app, reason)
from core import run as mode
mode.loop(app)
