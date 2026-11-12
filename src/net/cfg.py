"""GET /cfg.json: settings + asset lines for the form. Only flags for secrets. Loaded per request."""
import json
import network

import config
from data import assets


def send(cl, app, head) -> None:
    """Stream the json. head = portal.head (status line writer)."""

    # visible networks for the ssid field
    try:
        nets = sorted({n[0].decode() for n in network.WLAN(network.STA_IF).scan() if n[0]})
    except Exception:
        nets = []

    # assets copied line by line from flash, never parsed
    head(cl, "200 OK", "application/json", "Cache-Control: no-store\r\n")
    cl.write('{"s":')
    cl.write(json.dumps(app.s))
    cl.write(',"items":[')
    sep = ""
    for ln in assets.lines():
        cl.write(sep)
        cl.write(ln)
        sep = ","
    cl.write('],"off":%s' % ("true" if getattr(app, "off", False) else "false"))
    cl.write(',"pw":%s,"pp":%s,"max":%d,"reset_s":%d,"nets":%s}' % (
        "true" if app.sec.get("pw") else "false", "true" if app.sec.get("pp") else "false",
        assets.MAX, config.RESET_HOLD_S, json.dumps(nets)))
