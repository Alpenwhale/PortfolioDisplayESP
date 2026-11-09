"""Boot flow, main loop, FLASH button, fetching. Screens live in core.screens / core.setup."""
import gc
import machine
import socket
import sys
import time

import config
from net import wifi
from ui.layout import UI


def _later(ms: int) -> int:
    """ticks deadline from now."""
    return time.ticks_add(time.ticks_ms(), ms)


def _due(t: int) -> bool:
    """ticks deadline passed."""
    return time.ticks_diff(time.ticks_ms(), t) >= 0


def _drop(*names: str) -> None:
    """Unload modules and collect. RAM is the bottleneck on ESP8266."""
    for n in names:
        sys.modules.pop(n, None)
    gc.collect()


class App:
    """Holds state, owns the loops."""

    def __init__(self, d) -> None:
        """Load settings, nothing networky yet."""
        self.ui = UI(d)

        # settings + secrets, store module only while needed
        from data import store
        self.s = store.load()
        self.sec = store.load_secret()
        del store
        _drop("data.store")

        # runtime state
        self.q = {}              # item id -> {p, b, cur, n} and/or {err}
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
        """Period changed: every base price is stale."""
        self.q = {}
        self.applied()

    def reboot_soon(self, ms: int = 1500) -> None:
        """Reset after the http response went out."""
        self._reboot = _later(ms)

    def maybe_reboot(self) -> None:
        """Do the pending reset."""
        if self._reboot and _due(self._reboot):
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
        try:
            from net import portal
            portal.handle(cl, self)
        except Exception as e:
            print("portal:", repr(e))
        finally:
            cl.close()
            _drop("net.portal", "data.store")
        return True

    # --- FLASH button ---

    def button(self) -> None:
        """Short press: settings url. Hold RESET_HOLD_S: factory reset with countdown."""
        down = not self.btn.value()

        # press starts
        if down and not self._press:
            self._press = _later(0)
            return

        # still held: countdown after 2 s, wipe at RESET_HOLD_S
        if down:
            held = time.ticks_diff(time.ticks_ms(), self._press) // 1000
            left = config.RESET_HOLD_S - held
            if held >= 2 and left != self._shown_s:
                self._shown_s = left
                self.ui.message("Zurücksetzen", ["noch %d s halten" % left, "loslassen = Abbruch"])
            if left <= 0:
                from data import store
                store.factory_reset()
                self.ui.message("Zurückgesetzt", ["Neustart..."])
                time.sleep_ms(1500)
                machine.reset()
            return

        # released: short = info screen, long (aborted reset) = redraw
        if self._press:
            held = time.ticks_diff(time.ticks_ms(), self._press)
            self._press, self._shown_s = 0, -1
            if held < 1500 and not self.ap_mode:
                self.info_until, self.info_page, self.info_flip = _later(config.INFO_S * 1000), 0, 0
            self.dirty = True

    # --- boot ---

    def run(self) -> None:
        """Entry point, never returns."""
        u = self.ui
        u.message("PortfolioDisplay", ["Starte...", "FLASH = Einrichtung"])

        # FLASH held during the first 2 s -> setup mode (also how you get past a portal password)
        setup = False
        for _ in range(20):
            if not self.btn.value():
                setup = True
                break
            time.sleep_ms(100)
        reason = "per Taste" if setup else ""

        # no wifi yet / wifi down -> setup mode
        if not setup and not self.s["ssid"]:
            setup, reason = True, "kein WLAN"
        if not setup:
            u.message("Verbinde", [self.s["ssid"]])
            self.ip = wifi.sta(self.s["ssid"], self.sec.get("pw", ""), config.WIFI_TIMEOUT_S)
            if not self.ip:
                setup, reason = True, "WLAN fehlt"

        # wait for the button release so it isn't read as a reset hold
        while not self.btn.value():
            time.sleep_ms(50)
        gc.collect()
        if setup:
            from core import setup as setup_mode
            setup_mode.run(self, reason)
        self._normal()

    def _normal(self) -> None:
        """Connected: show the settings url briefly, then fetch + render forever."""
        self.listen()
        self.info_until = _later(config.INFO_S * 1000)
        self.queue = list(range(len(self.s["items"])))
        self.next_fetch = _later(self.s["fetch_s"] * 1000)
        self.next_slide = self.info_until

        while True:
            self.serve()
            self.button()
            self.maybe_reboot()

            # one fetch per loop pass keeps web + button responsive
            if self.queue:
                if wifi.connected():
                    self._fetch(self.queue.pop(0))
            elif _due(self.next_fetch):
                self.queue = list(range(len(self.s["items"])))
                self.next_fetch = _later(self.s["fetch_s"] * 1000)

            # info screen overrides everything while active
            if self.info_until and not _due(self.info_until):
                if not self.info_flip or _due(self.info_flip):
                    self._info()
                time.sleep_ms(30)
                continue
            if self.info_until:
                self.info_until, self.dirty = 0, True

            # slideshow
            n = len(self.s["items"])
            if self.s["mode"] == "slide" and n > 1 and _due(self.next_slide):
                self.slide = (self.slide + 1) % n
                self.next_slide = _later(self.s["slide_s"] * 1000)
                self.dirty = True

            # redraw only on change
            if self.dirty:
                self.dirty = False
                from core import screens
                screens.render(self)
            time.sleep_ms(30)

    def _info(self) -> None:
        """Settings url page (rotates on small screens)."""
        from core import setup as s
        pages = s.info_page(self.ui, self.info_page, self.ip)
        del s
        _drop("core.setup")
        self.info_page = (self.info_page + 1) % pages
        self.info_flip = _later(config.PAGE_S * 1000)

    # --- data ---

    def _fetch(self, i: int) -> None:
        """Resolve (once) + quote one item. Keeps the last good price on errors."""
        items = self.s["items"]
        if i >= len(items):
            return
        it = items[i]
        gc.collect()
        try:
            from net import quotes

            # isin/wkn -> yahoo symbol, cached in settings
            if not it.get("sym"):
                it["sym"], it["yname"] = quotes.resolve(it["id"], it.get("ex", "auto"))
                from data import store
                store.save(self.s)
                del store

            # price + base for the configured period
            q = quotes.quote(it["sym"], self.s["period"])
            if not q["n"]:
                q["n"] = it.get("yname", "")
            self.q[it["id"]] = q
        except Exception as e:
            print("fetch", it["id"], repr(e))
            self.q.setdefault(it["id"], {})["err"] = str(e) or e.__class__.__name__
        finally:
            _drop("net.quotes", "data.store")

        # redraw if this item is on screen
        m = self.s["mode"]
        if m == "port" or (m == "slide" and self.slide == i) or (m == "single" and self.s["single"] == i):
            self.dirty = True
