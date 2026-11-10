"""Join the home network or open the setup AP."""
import network
import time


def sta(ssid: str, pw: str, timeout_s: int) -> str:
    """Connect as client, returns ip or '' on timeout."""

    # micropython opens an unprotected AP by default, kill it
    network.WLAN(network.AP_IF).active(False)
    w = network.WLAN(network.STA_IF)
    w.active(True)

    # SDK may still be connected from before the soft reset
    if not w.isconnected():
        w.connect(ssid, pw)
        end = time.ticks_add(time.ticks_ms(), timeout_s * 1000)
        while not w.isconnected() and time.ticks_diff(end, time.ticks_ms()) > 0:
            time.sleep_ms(200)
    return w.ifconfig()[0] if w.isconnected() else ""


def ap_name(prefix: str) -> str:
    """prefix-XXXX from the last mac bytes, stable per device."""
    mac = network.WLAN(network.AP_IF).config("mac")
    return "%s-%02X%02X" % (prefix, mac[-2], mac[-1])


def ap(ssid: str, pw: str) -> str:
    """WPA2 access point, returns its ip."""
    a = network.WLAN(network.AP_IF)
    a.active(True)
    a.config(essid=ssid, password=pw, authmode=network.AUTH_WPA2_PSK)

    # station stays on for the network scan in the portal
    network.WLAN(network.STA_IF).active(True)
    return a.ifconfig()[0]
