"""App state, boot decision, web serving, FLASH button.

Mode-specific code lives elsewhere and is only loaded when needed (RAM):
core.setup (setup AP), core.run (normal loop + fetching), core.screens (drawing).
"""
import gc
import machine
import socket
import sys
import time

import config
from net import wifi
from ui.layout import UI


def later(ms: int) -> int:
    """ticks deadline from now."""
    return time.ticks_add(time.ticks_ms(), ms)


def due(t: int) -> bool:
    """ticks deadline passed."""
    return time.ticks_diff(time.ticks_ms(), t) >= 0


def drop(*names: str) -> None:
    """Unload modules and collect. RAM is the bottleneck on ESP8266."""
    for n in names:
        sys.modules.pop(n, None)
    gc.collect()


class App:
    """Shared state for setup + normal mode."""

    def __init__(self, d) -> None:
        """Load settings, nothing networky yet."""
        self.ui = UI(d)

        # settings + secrets, store module only while needed
        from data import store
        self.s = store.load()
        self.sec = store.load_secret()
        del store
        drop("data.store")

        # runtime state
        self.q = {}              # item id -> {p, b, cur, n} and/or {err}
        self.fx = {}             # currency -> rate into the display currency
        self.ap_mode = False
        self.ip = ""
        self.srv = None
        self.dirty = True
        self.slide = 0
        self.next_slide = 0
        self.queue = []
        self.next_fetch = 0
        self.info_until = 0      # info screen (settings url) active until
        self.info_page = 0
        self.info_flip = 0
        self._reboot = 0
        self._press = 0
        self._shown_s = -1
        self.btn = machine.Pin(config.BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

    # --- called by portal / setup ---

    def applied(self) -> None:
        """Settings changed without reboot: refetch what's new, redraw."""
        ids = {it["id"] for it in self.s["items"]}
        self.q = {k: v for k, v in self.q.items() if k in ids}
        self.queue = [i for i, it in enumerate(self.s["items"]) if it["id"] not in self.q]
        self.slide = 0
        self.dirty = True

    def refetch_all(self) -> None:
        """Period or currency changed: every cached price is stale."""
        self.q, self.fx = {}, {}
        self.applied()

    def reboot_soon(self, ms: int = 1500) -> None:
        """Reset after the http response went out."""
        self._reboot = later(ms)

    def maybe_reboot(self) -> None:
        """Do the pending reset."""
        if self._reboot and due(self._reboot):
            machine.reset()

    # --- web ---

    def listen(self) -> None:
        """Non-blocking http server on :80."""
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 80))
        s.listen(2)
        s.setblocking(False)
        self.srv = s

    def serve(self) -> bool:
        """Handle one pending request, if any. True if something was served."""
        try:
            cl, _ = self.srv.accept()
        except OSError:
            return False

        # portal only lives in RAM for the duration of one request
        gc.collect()
        try:
            from net import portal
            portal.handle(cl, self)
        except Exception as e:
            print("portal:", repr(e))
        finally:
            cl.close()
            drop("net.portal", "data.store")
        return True

    # --- FLASH button ---

    def button(self) -> None:
        """Short press: settings url. Hold RESET_HOLD_S: factory reset with countdown."""
        down = not self.btn.value()

        # press starts
        if down and not self._press:
            self._press = later(0)
            return

        # still held: countdown after 2 s, wipe at RESET_HOLD_S
        if down:
            held = time.ticks_diff(time.ticks_ms(), self._press) // 1000
            left = config.RESET_HOLD_S - held
            if held >= 2 and left != self._shown_s:
                self._shown_s = left
                self.ui.message("Factory reset", ["keep holding %d s" % left, "release = cancel"])
            if left <= 0:
                from data import store
                store.factory_reset()
                self.ui.message("Reset done", ["Rebooting..."])
                time.sleep_ms(1500)
                machine.reset()
            return

        # released: short = info screen, long (aborted reset) = redraw
        if self._press:
            held = time.ticks_diff(time.ticks_ms(), self._press)
            self._press, self._shown_s = 0, -1
            if held < 1500 and not self.ap_mode:
                self.info_until, self.info_page, self.info_flip = later(config.INFO_S * 1000), 0, 0
            self.dirty = True

    # --- boot ---

    def run(self) -> None:
        """Entry point, never returns."""
        u = self.ui
        u.message("PortfolioDisplay", ["Starting...", "Hold FLASH = setup"])

        # FLASH held during the first 2 s -> setup mode (also how you get past a portal password)
        setup = False
        for _ in range(20):
            if not self.btn.value():
                setup = True
                break
            time.sleep_ms(100)
        reason = "FLASH pressed" if setup else ""

        # no wifi yet / wifi down -> setup mode
        if not setup and not self.s["ssid"]:
            setup, reason = True, "no Wi-Fi set"
        if not setup:
            u.message("Connecting", [self.s["ssid"]])
            self.ip = wifi.sta(self.s["ssid"], self.sec.get("pw", ""), config.WIFI_TIMEOUT_S)
            if not self.ip:
                setup, reason = True, "Wi-Fi not found"

        # wait for the button release so it isn't read as a reset hold
        while not self.btn.value():
            time.sleep_ms(50)
        gc.collect()

        # hand over to the mode, each loads only its own code
        if setup:
            from core import setup as mode
            mode.run(self, reason)
        from core import run as mode
        mode.loop(self)
