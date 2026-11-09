"""Boot flow, setup AP, fetch loop and display modes."""
import gc
import machine
import network
import socket
import sys
import time

import config
from ui import UI, num, signed, cur


def _store():
    """store is only needed now and then, import on demand (RAM)."""
    import store
    return store


def _drop(name: str) -> None:
    """Unload a module and collect."""
    sys.modules.pop(name, None)
    gc.collect()


def _due(t: int) -> bool:
    """ticks deadline passed."""
    return time.ticks_diff(time.ticks_ms(), t) >= 0


def _later(ms: int) -> int:
    """ticks deadline from now."""
    return time.ticks_add(time.ticks_ms(), ms)


class App:
    """Holds state, owns the main loop."""

    def __init__(self, d) -> None:
        """Load settings, nothing networky yet."""
        self.ui = UI(d)
        st = _store()
        self.s = st.load()
        self.sec = st.load_secret()
        del st
        _drop("store")
        self.q = {}            # item id -> {p, c, cur, n} or {err}
        self.ap_mode = False
        self.ip = ""
        self.srv = None
        self._reboot = 0
        self.dirty = True
        self.slide = 0
        self.next_slide = 0
        self.queue = []
        self.next_fetch = 0

    # --- called by portal ---

    def applied(self) -> None:
        """Settings changed without reboot: refetch, redraw."""
        ids = {it["id"] for it in self.s["items"]}
        self.q = {k: v for k, v in self.q.items() if k in ids}
        self.queue = [i for i, it in enumerate(self.s["items"]) if it["id"] not in self.q]
        self.slide = 0
        self.dirty = True

    def reboot_soon(self) -> None:
        """Reset after the response went out."""
        self._reboot = _later(1500)

    # --- network ---

    def _listen(self) -> None:
        """Non-blocking http server on :80."""
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("0.0.0.0", 80))
        s.listen(2)
        s.setblocking(False)
        self.srv = s

    def _poll_web(self) -> bool:
        """Serve one pending request, if any. True if something was served."""
        try:
            cl, _ = self.srv.accept()
        except OSError:
            return False
        try:
            import portal
            portal.handle(cl, self)
        except Exception as e:
            print("portal:", repr(e))
        finally:
            cl.close()
            sys.modules.pop("portal", None)
            _drop("store")
        return True

    def _tick(self) -> None:
        """Web + pending reboot, every loop."""
        self._poll_web()
        if self._reboot and _due(self._reboot):
            machine.reset()

    def _sta(self) -> str:
        """Join configured wifi, '' on timeout."""
        network.WLAN(network.AP_IF).active(False)  # micropython's open default AP
        w = network.WLAN(network.STA_IF)
        w.active(True)
        if not w.isconnected():
            w.connect(self.s["ssid"], self.sec.get("pw", ""))
            t = _later(config.WIFI_TIMEOUT_S * 1000)
            while not w.isconnected() and not _due(t):
                time.sleep_ms(200)
        return w.ifconfig()[0] if w.isconnected() else ""

    # --- boot ---

    def run(self) -> None:
        """Entry point, never returns."""
        u = self.ui
        u.message("PortfolioDisplay", ["Starte...", "FLASH halten = Einrichtung"])
        btn = machine.Pin(config.BUTTON_PIN, machine.Pin.IN, machine.Pin.PULL_UP)
        setup = False
        for _ in range(20):
            if not btn.value():
                setup = True
                break
            time.sleep_ms(100)
        reason = "per Taste gestartet" if setup else ""
        if not setup and not self.s["ssid"]:
            setup, reason = True, "noch kein WLAN"
        if not setup:
            u.message("Verbinde", [self.s["ssid"]])
            self.ip = self._sta()
            if not self.ip:
                setup, reason = True, "WLAN nicht erreichbar"
        gc.collect()
        self._setup(reason) if setup else self._normal()

    def _setup(self, reason: str) -> None:
        """WPA2 AP with random password + portal. Idle timeout reboots to retry wifi."""
        self.ap_mode = True
        pw = self.sec.get("ap")
        if not pw:
            st = _store()
            pw = self.sec["ap"] = st.random_pw()
            st.save_secret(self.sec)
            del st
            _drop("store")
        mac = network.WLAN(network.AP_IF).config("mac")
        ssid = "%s-%02X%02X" % (config.AP_PREFIX, mac[-2], mac[-1])
        ap = network.WLAN(network.AP_IF)
        ap.active(True)
        ap.config(essid=ssid, password=pw, authmode=network.AUTH_WPA2_PSK)
        network.WLAN(network.STA_IF).active(True)  # for the wifi scan in the portal
        self.ip = ap.ifconfig()[0]
        self.ui.message("Einrichtung", ["WLAN: " + ssid, "Passwort: " + pw, "http://" + self.ip, reason])
        self._listen()
        idle = _later(config.SETUP_IDLE_S * 1000)
        while True:
            if self._poll_web():
                idle = _later(config.SETUP_IDLE_S * 1000)
            if self._reboot and _due(self._reboot):
                machine.reset()
            if self.s["ssid"] and _due(idle):
                machine.reset()  # maybe the router is back
            time.sleep_ms(50)

    def _normal(self) -> None:
        """Connected: show ip briefly, then fetch + render forever."""
        self.ui.message("Verbunden", ["Einstellungen:", "http://" + self.ip])
        self._listen()
        hold = self.next_slide = _later(5000)
        self.queue = list(range(len(self.s["items"])))
        self.next_fetch = _later(self.s["fetch_s"] * 1000)
        sta = network.WLAN(network.STA_IF)
        while True:
            self._tick()
            if self.queue:
                if sta.isconnected():
                    self._fetch(self.queue.pop(0))
            elif _due(self.next_fetch):
                self.queue = list(range(len(self.s["items"])))
                self.next_fetch = _later(self.s["fetch_s"] * 1000)
            n = len(self.s["items"])
            if self.s["mode"] == "slide" and n > 1 and _due(self.next_slide):
                self.slide = (self.slide + 1) % n
                self.next_slide = _later(self.s["slide_s"] * 1000)
                self.dirty = True
            if self.dirty and _due(hold):
                self.dirty = False
                self.render()
            time.sleep_ms(30)

    # --- data ---

    def _fetch(self, i: int) -> None:
        """Resolve (once) + quote one item. Keeps the last good price on errors."""
        items = self.s["items"]
        if i >= len(items):
            return
        it = items[i]
        gc.collect()
        try:
            import quotes
            if not it.get("sym"):
                it["sym"], name = quotes.resolve(it["id"])
                it["auto"] = name
                _store().save(self.s)
                _drop("store")
            q = quotes.quote(it["sym"])
            if not q["n"]:
                q["n"] = it.get("auto", "")
            self.q[it["id"]] = q
        except Exception as e:
            print("fetch", it["id"], repr(e))
            q = self.q.setdefault(it["id"], {})
            q["err"] = str(e) or e.__class__.__name__
        finally:
            sys.modules.pop("quotes", None)
            gc.collect()
        if self._visible(i):
            self.dirty = True

    def _visible(self, i: int) -> bool:
        """Is item i on screen in the current mode?"""
        m = self.s["mode"]
        return m == "port" or (m == "slide" and self.slide == i) or (m == "single" and self.s["single"] == i)

    # --- screens ---

    def render(self) -> None:
        """Draw the screen for the current mode."""
        items, m, u = self.s["items"], self.s["mode"], self.ui
        if not items:
            u.message("Keine Wertpapiere", ["Einrichten unter", "http://" + self.ip])
        elif m == "port":
            self._portfolio()
        elif m == "single":
            self._item(min(self.s["single"], len(items) - 1), True)
        else:
            self._item(self.slide % len(items), False)

    def _labels(self, it: dict, q: dict) -> list:
        """Name if it fits, else the id."""
        name = it.get("name") or q.get("n") or ""
        return [name, it["id"]] if name else [it["id"]]

    def _item(self, i: int, ret: bool) -> None:
        """One security. ret=True: return since buy as headline (if buy price known)."""
        u, it = self.ui, self.s["items"][i]
        q = self.q.get(it["id"], {})
        page = (i, len(self.s["items"])) if self.s["mode"] == "slide" else (0, 1)
        if "p" not in q:
            u.card(self._labels(it, q), "-", "", u.dim, 0,
                   [([q["err"]] if "err" in q else ["Lade Kurs..."], u.dim)], page)
            return
        p, c, unit = q["p"], q["c"], cur(q["cur"])
        dec = 2 if p >= 1 else 4
        day = p - c
        day_pct = day / c * 100 if c else 0
        day_line = ([signed(day_pct) + " % (" + signed(day, dec) + " " + unit + ")",
                     signed(day_pct) + " %"], u.tone(day))
        buy = it.get("buy")
        if ret and buy:
            r = (p - buy) / buy * 100
            subs = [([num(p, dec) + " " + unit], u.fg), (["Heute " + signed(day_pct) + " %"], u.tone(day))]
            u.card(self._labels(it, q), signed(r), "%", u.tone(r), r, subs, page)
            return
        subs = [day_line]
        if buy:
            r = (p - buy) / buy * 100
            subs.append((["Seit Kauf " + signed(r) + " %", signed(r) + " %"], u.tone(r)))
        u.card(self._labels(it, q), num(p, dec), unit, u.tone(day), day, subs, page)

    def _portfolio(self) -> None:
        """Total return over all items with qty + buy price."""
        u = self.ui
        value = cost = 0.0
        unit = ""
        missing = 0
        for it in self.s["items"]:
            q = self.q.get(it["id"], {})
            if it.get("qty") and it.get("buy"):
                if "p" not in q:
                    missing += 1
                    continue
                value += it["qty"] * q["p"]
                cost += it["qty"] * it["buy"]
                unit = unit or cur(q["cur"])
        if not cost:
            msg = "Lade Kurse..." if missing else "Stück + Kaufkurs eintragen"
            u.card(["Portfolio"], "-", "", u.dim, 0, [([msg], u.dim)])
            return
        gain = value - cost
        r = gain / cost * 100
        subs = [([num(value) + " " + unit], u.fg), ([signed(gain) + " " + unit], u.tone(gain))]
        if missing:
            subs.append((["%d Kurs(e) fehlen" % missing], u.dim))
        u.card(["Portfolio"], signed(r), "%", u.tone(r), r, subs)
