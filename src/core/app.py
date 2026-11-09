"""App state, web serving, FLASH button. Shared by setup + normal mode.

Everything else is loaded only when needed (RAM): core.boot (start decision, dropped
after), core.setup (setup AP), core.run (normal loop + fetching), core.screens (drawing).
"""
import gc
import machine
import socket
import sys
import time
from array import array

import config


NAN = float("nan")


def later(ms: int) -> int:
    """ticks deadline from now."""
    return time.ticks_add(time.ticks_ms(), ms)


def due(t: int) -> bool:
    """ticks deadline passed."""
    return time.ticks_diff(time.ticks_ms(), t) >= 0


def drop(*names: str) -> None:
    """Unload modules and collect. RAM is the bottleneck on ESP8266.

    A submodule also hangs as attribute on its package (ui.card on ui), so it has to go
    from there too, otherwise sys.modules.pop alone frees nothing.
    """
    for n in names:
        sys.modules.pop(n, None)
        i = n.rfind(".")
        parent = sys.modules.get(n[:i]) if i > 0 else None
        if parent:
            parent.__dict__.pop(n[i + 1:], None)
    gc.collect()


class App:
    """Shared state for setup + normal mode."""

    def __init__(self, d) -> None:
        """Load settings, nothing networky yet."""
        self.d = d
        self._ui = None

        # settings + secrets, store module only while needed
        from data import store
        self.s = store.load()
        self.sec = store.load_secret()
        del store
        drop("data.store")

        # assets: numbers only, records stay on flash
        self.load_assets()

        # runtime state
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
        self.just_saved = False  # set by the portal, handled in serve()
        self._press = 0
        self._shown_s = -1
        self.btn = machine.Pin(config.BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

    # --- drawing: layout code only lives in RAM while something is drawn ---

    @property
    def ui(self):
        """Layout helper, created on first use after each release_ui()."""
        if self._ui is None:
            from ui.layout import UI
            self._ui = UI(self.d)
        return self._ui

    def release_ui(self) -> None:
        """After a screen is drawn: drop layout + drawing modules, close font files."""
        self._ui = None
        from ui import font
        font.release()
        del font
        drop("ui.layout", "core.screens", "core.setup", "ui.card", "ui.fmt", "ui.font")

    def message(self, title: str, lines: list) -> None:
        """Full-screen text, then free the layout again."""
        self.ui.message(title, lines)
        self.release_ui()

    # --- setup mode loop (pages come from core.setup, loaded per flip) ---

    def setup_loop(self, ssid: str, pw: str, reason: str) -> None:
        """Serve the portal on the setup AP until saved; never returns."""
        page, pages, flip, idle = 0, 1, 0, 0
        while True:
            now = time.ticks_ms()
            if self.serve():
                idle = 0

            # rotate pages, but keep "Saved / Restarting" up once a reboot is pending
            if not self._reboot and (not flip or time.ticks_diff(now, flip) >= 0):
                from core import setup
                pages = setup.setup_page(self.ui, page, ssid, pw, self.ip, reason)
                del setup
                self.release_ui()
                page = (page + 1) % pages
                flip = later(config.PAGE_S * 1000 if pages > 1 else 3600000)

            # idle too long with a known wifi -> reboot, maybe the router is back
            if not idle:
                idle = later(config.SETUP_IDLE_S * 1000)
            if self.s["ssid"] and due(idle):
                self.reboot_soon(0)
            self.button()
            self.maybe_reboot()
            time.sleep_ms(50)

    # --- assets ---

    def load_assets(self) -> None:
        """Float arrays per asset index (~20 B each). NaN price = not fetched yet."""
        from data import assets
        qty, buy = [], []
        for rec in assets.each():
            qty.append(rec.get("qty") or 0.0)
            buy.append(rec.get("buy") or 0.0)
        del assets
        drop("data.assets")

        # one slot per asset; currency as index into self.curs
        self.n = n = len(qty)
        self.qty = array("f", qty)
        self.buy = array("f", buy)
        self.price = array("f", [NAN] * n)
        self.base = array("f", [NAN] * n)
        self.cur = bytearray(n)
        self.curs = [""]
        self.err = {}  # index -> last fetch error, rare

    def asset(self, i: int) -> dict:
        """Full record of asset i, read from flash."""
        from data import assets
        rec = assets.read(i)
        del assets
        drop("data.assets")
        return rec

    def set_quote(self, i: int, p: float, b: float, code: str) -> None:
        """Store a converted quote in the arrays."""
        if code not in self.curs:
            self.curs.append(code)
        self.price[i], self.base[i], self.cur[i] = p, b, self.curs.index(code)
        self.err.pop(i, None)

    # --- called by portal / setup ---

    def applied(self) -> None:
        """Asset list or settings changed without reboot: reload numbers, refetch all, redraw."""
        self.load_assets()
        self.queue = list(range(self.n))
        self.slide = 0
        self.dirty = True

    def refetch_all(self) -> None:
        """Period or currency changed: rates are stale too."""
        self.fx = {}
        self.applied()

    def saved(self, reboot: bool) -> None:
        """Feedback on the device itself after a portal save."""
        if reboot:
            self.ui.message("Saved", ["Restarting..."])
            self.reboot_soon()
        else:
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
            drop("net.portal", "net.cfg", "data.store", "data.assets")

        # a saved form: now that the portal is gone there's room for the message
        if self.just_saved:
            self.just_saved = False
            self.saved()
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
