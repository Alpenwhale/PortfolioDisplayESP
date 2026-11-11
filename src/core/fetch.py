"""Warm-boot fetch phase: the first thing main.py runs after a refresh soft reset.

The heap is nearly empty here (~30 KB), which is the only moment the ESP8266 has enough
RAM for a Yahoo TLS handshake (~18-22 KB peak). The display is not touched at all, so
it keeps showing the last screen (frozen) while this runs.
Fetches the next batch of assets (config.FETCH_BATCH) into /prices.bin.
"""
import gc
import json
import sys
import time

import config

PERMANENT = ("not found", "WKN: use the ISIN", "not on this exchange")  # errors of net.search.resolve
RETRY_EVERY = 12  # such assets are tried again every 12th refresh (and on every cold boot)


def _drop(*names: str) -> None:
    """Unload modules (also from the parent package) and collect."""
    for n in names:
        sys.modules.pop(n, None)
        i = n.rfind(".")
        parent = sys.modules.get(n[:i]) if i > 0 else None
        if parent:
            parent.__dict__.pop(n[i + 1:], None)
    gc.collect()


def _need_ram() -> None:
    """Too little RAM for TLS = hard crash + reboot loop, so raise instead."""
    gc.collect()
    if gc.mem_free() < config.TLS_MIN_FREE:
        raise OSError("low RAM %d" % gc.mem_free())


def _convert(q: dict, want: str, fx: dict) -> bool:
    """Scale p/b into the display currency with a known rate. False = rate still missing (see _late_fx)."""

    # london quotes in pence
    if q["cur"] in ("GBp", "GBX"):
        q["p"], q["b"], q["cur"] = q["p"] / 100, q["b"] / 100, "GBP"
    if want == "native" or not q["cur"] or q["cur"] == want:
        return True
    rate = fx.get(q["cur"])
    if rate is None:
        return False
    q["p"], q["b"], q["cur"] = q["p"] * rate, q["b"] * rate, want
    return True


def _late_fx(late: list, want: str, fx: dict) -> None:
    """Convert records stored in their native currency.

    Runs after the batch: inside _one the asset modules + quote leave too little RAM for a
    second TLS handshake, here only data.prices is loaded. One rate per currency per batch.
    """
    from data import prices
    for i, cur in late:
        try:
            rate = fx.get(cur)
            if rate is None:
                from net import quotes
                _need_ram()
                rate = fx[cur] = quotes.fx(cur, want)
        except Exception as e:
            print("fx", cur, want, repr(e))
            continue
        finally:
            _drop("net.quotes")
        r = prices.read(i)
        prices.write(i, r[0] * rate, r[1] * rate, r[2], want, r[4])
    del prices
    _drop("data.prices")


def _one(i: int, period: str, want: str, fx: dict, retry: bool, late: list) -> None:
    """Resolve (once) + quote asset i into its prices.bin record. Keeps the last good price on errors."""
    from data import assets, prices
    rec = assets.read(i)

    # an identifier yahoo doesn't know won't work a minute later either: skip it (no network,
    # no freeze time) except every RETRY_EVERY-th cycle. Saving in the portal clears the mark.
    if rec.get("nf") and not retry:
        return
    old = prices.read(i)
    try:

        # isin/wkn -> yahoo symbol once, cached in the asset file
        if not rec.get("sym"):
            from net import search
            _need_ram()
            sym, name = search.resolve(rec["id"], rec.get("ex", "auto"))
            del search
            _drop("net.search")

            # yahoo pads names and appends a share class after a run of spaces ("KION GROUP AG      I")
            rec["sym"], rec["yname"] = sym, name.split("  ")[0].strip()
            assets.update(i, sym=sym, yname=rec["yname"])

        # price + base for the period, then into the display currency
        from net import quotes
        _need_ram()
        q = quotes.quote(rec["sym"], period)
        del quotes
        _drop("net.quotes")
        if not _convert(q, want, fx):
            late.append((i, q["cur"]))
        prices.write(i, q["p"], q["b"], 1, q["cur"], "")
        if not rec.get("yname") and q["n"]:
            assets.update(i, yname=q["n"].split("  ")[0].strip())
        if rec.get("nf"):
            assets.update(i, nf=0)
        print("fetch", rec.get("id"), q["p"], q["cur"])
    except Exception as e:
        msg = str(e) or e.__class__.__name__
        print("fetch", rec.get("id"), msg)
        prices.write(i, old[0], old[1], old[2], old[3], msg)
        if msg in PERMANENT and not rec.get("nf"):
            assets.update(i, nf=1)
    finally:
        _drop("net.search", "net.quotes")


def run(state: dict) -> dict:
    """Fetch the next batch, return the state with the new batch offset."""

    # settings straight from json, no store module needed here
    try:
        with open("/settings.json") as f:
            s = json.load(f)
    except (OSError, ValueError):
        s = {}
    period, want, ntp = s.get("period", "1d"), s.get("cur", "EUR"), s.get("sleep")
    del s

    # wifi survives the soft reset, give the SDK a moment if it dropped
    import network
    sta = network.WLAN(network.STA_IF)
    end = time.ticks_add(time.ticks_ms(), 10000)
    while not sta.isconnected() and time.ticks_diff(end, time.ticks_ms()) > 0:
        time.sleep_ms(200)
    if not sta.isconnected():
        return state

    # utc clock for the sleep window (rtc drifts, so on every refresh)
    if ntp:
        try:
            import ntptime
            ntptime.settime()
        except Exception as e:
            print("ntp", repr(e))
        sys.modules.pop("ntptime", None)

    # next batch, wrapping around the list
    from data import assets
    n = assets.count()
    del assets
    _drop("data.assets")
    if not n:
        return state
    start, count = state.get("o", 0) % n, min(config.FETCH_BATCH, n)
    gc.collect()
    print("fetch phase: %d of %d assets from #%d, free %d" % (count, n, start, gc.mem_free()))

    # the screen is frozen while this runs, so the whole batch has a time budget
    fx, late = {}, []
    t0 = time.ticks_ms()
    done = 0
    retry = state.get("c", 0) % RETRY_EVERY == 0
    state["c"] = state.get("c", 0) + 1
    for k in range(count):
        _one((start + k) % n, period, want, fx, retry, late)
        _drop("data.assets", "data.prices")
        done += 1
        if time.ticks_diff(time.ticks_ms(), t0) > config.FETCH_MAX_S * 1000:
            print("fetch phase: time budget used up")
            break
    _late_fx(late, want, fx)
    state["o"] = (start + done) % n
    return state
