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


def _exists(path: str) -> bool:
    """File on flash?"""
    import os
    try:
        os.stat(path)
        return True
    except OSError:
        return False


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

        # panel dims itself (OLED contrast, TFT backlight pin), else the ui darkens its colors
        self.bright = 100 if d.brightness(self.s["bright"]) else self.s["bright"]

        # assets: numbers only, records stay on flash; prices from the last fetch phase
        self.load_assets()

        # runtime state
        self.ap_mode = False
        self.ip = ""
        self.srv = None
        self.dirty = True
        self.slide = 0
        self.offset = 0          # next asset batch for core.fetch
        self.cycle = 0           # refresh counter since the cold boot
        self.show_info = 0       # show the settings url right after this boot
        self.t_refresh = None    # ticks when the last refresh froze the screen (warm boot only)
        self.next_slide = 0
        self.next_fetch = 0
        self.info_until = 0      # info screen (settings url) active until
        self.info_page = 0
        self.info_flip = 0
        self._reboot = 0
        self.just_saved = False  # set by the portal, handled in serve()
        self.web_until = 0       # portal in use: no refresh (soft reset) until then
        self.nap_at = 0          # next sleep window / power check
        self.off = _exists("/off")  # switched off in the portal: dark like the sleep window
        self._press = 0
        self._shown_s = -1
        self.btn = machine.Pin(config.BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)

    # --- drawing: layout code only lives in RAM while something is drawn ---

    @property
    def ui(self):
        """Layout helper, created on first use after each release_ui()."""
        if self._ui is None:
            from ui.layout import UI
            self._ui = UI(self.d, self.bright)
        return self._ui

    def release_ui(self) -> None:
        """After a screen is drawn: drop layout + drawing modules, close font files."""
        self._ui = None
        from ui import font
        font.release()
        del font
        drop("ui.layout", "core.screens", "core.setup", "ui.card", "ui.fmt", "ui.font")

    def message(self, title: str, lines: list) -> None:
        """Full-screen text, then free the layout again. Lights a dark panel (reset countdown)."""
        if getattr(self, "asleep", False):
            self.d.power(True)
        self.ui.message(title, lines)
        self.release_ui()

    # --- assets ---

    def load_assets(self) -> None:
        """Float arrays per asset index (~20 B each), prices from /prices.bin. NaN price = none yet."""
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

        # slideshow: optional total page first, then the assets (or just the first one)
        s = self.s
        self.total = 0 if s["single"] or not n else s["show_total"]
        self.pages = self.total + (min(n, 1) if s["single"] else n if s["show_assets"] or not self.total else 0)

        # prices written by core.fetch during the last warm boot
        from data import prices
        for i, p, b, ok, code, err in prices.each():
            if i >= n:
                break
            if ok:
                self.set_quote(i, p, b, code)
            if err:
                self.err[i] = err
        del prices
        drop("data.prices")

    def asset(self, i: int) -> dict:
        """Full record of asset i, read from flash."""
        from data import assets
        rec = assets.read(i)
        del assets
        drop("data.assets")
        return rec

    def set_quote(self, i: int, p: float, b: float, code: str) -> None:
        """Store a quote in the arrays."""
        if code not in self.curs:
            self.curs.append(code)
        self.price[i], self.base[i], self.cur[i] = p, b, self.curs.index(code)

    def refresh(self, info: int = 0) -> None:
        """Soft reset into the warm-boot fetch phase. Draws nothing: the screen stays frozen.

        Only the Python VM restarts: chip, display and wifi keep running. State for the
        next boot goes into RTC memory, which survives the soft reset. "t" = ticks now, so
        main.py can tell a fresh marker from one left over before a chip reset.
        """
        import json
        if self.srv:
            self.srv.close()
        state = {"s": self.slide, "o": self.offset, "c": self.cycle, "i": info, "t": time.ticks_ms()}
        machine.RTC().memory(b"W" + json.dumps(state).encode())
        print("refresh: soft reset")
        from core import reset
        reset.soft_reset()

    def slide_ms(self) -> int:
        """How long the current slide stays up."""
        return self.s["total_s" if self.slide < self.total else "slide_s"] * 1000

    # --- called by portal / setup ---

    def saved(self) -> None:
        """Portal saved a form: reboot (main.py applies it at the next boot). Called after the portal is unloaded."""
        self.reboot_soon()
        try:
            self.message("Saved", ["Restarting..."])
        except MemoryError:
            pass  # the reboot is what matters

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

        # someone is on the settings page: keep the server up, no refresh for a while
        self.web_until = later(config.WEB_HOLD_S * 1000)

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
                self.message("Factory reset", ["keep holding %d s" % left, "release = cancel"])
            if left <= 0:
                from data import store
                store.factory_reset()
                self.message("Reset done", ["Rebooting..."])
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
