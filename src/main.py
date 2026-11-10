"""Entry point. Kept tiny: one-shot code lives in core.fetch / core.boot and is unloaded after.

Warm boot (refresh soft reset, marked in RTC memory): fetch prices first with an empty heap,
the display isn't touched and keeps its image. Cold boot: normal start, see core.boot.
Any crash ends in a chip reset instead of a dead screen at the REPL.
"""
import machine
import sys
import time

try:
    # warm boot? marker = b"W" + json, written by App.refresh() right before the soft reset
    rtc = machine.RTC()
    raw = rtc.memory()
    state = None
    if raw[:1] == b"W":
        rtc.memory(b"")
        import json
        try:
            state = json.loads(raw[1:])

            # ticks keep counting over a soft reset but restart on a chip reset:
            # a marker that isn't a few seconds old is stale -> cold boot (panel needs its init)
            if not 0 <= time.ticks_diff(time.ticks_ms(), state["t"]) < 15000:
                state = None
        except (ValueError, KeyError):
            state = None
    del rtc, raw

    # fetch phase: nothing else loaded yet, ~30 KB free for TLS
    if state is not None:
        try:
            from core import fetch
            state = fetch.run(state)
            del fetch
        except Exception as e:
            sys.print_exception(e)
        sys.modules.pop("core.fetch", None)
        sys.modules["core"].__dict__.pop("fetch", None)

    # display + app (+ on cold boot: pending save, setup decision, first refresh)
    print("boot:", "cold" if state is None else "warm")
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

except Exception as e:
    # SystemExit (= refresh) and Ctrl-C pass through; real errors: log, pause, chip reset
    sys.print_exception(e)
    time.sleep(5)
    machine.reset()
