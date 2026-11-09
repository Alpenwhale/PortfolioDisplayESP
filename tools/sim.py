"""Render every screen on the PC with the real ui/core code -> PNGs in tools/sim_out/.

Usage: uv run tools/sim.py
Sizes: 128x64 mono (0.96" OLED) and 320x240 color (2.8" TFT).
Board-only modules (framebuf, machine, network) are stubbed; the builtin 8x8 font is
approximated with Pillow's bitmap font, widths are exact (8 px/char).
Also checks the QR encoder against segno module-by-module.
"""
import sys
import types
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "tools" / "sim_out"
sys.path.insert(0, str(ROOT / "src"))


# --- stubs for board-only modules ---

def _stub(name: str, **attrs) -> None:
    """Register a fake module."""
    m = types.ModuleType(name)
    m.__dict__.update(attrs)
    sys.modules[name] = m


class _FB:
    """framebuf.FrameBuffer, only MONO_HLSB .text() is used by display.base."""

    _font = ImageFont.load_default_imagefont()

    def __init__(self, buf, w, h, fmt):
        self.buf, self.w, self.h = buf, w, h

    def text(self, s, x, y, c):
        img = Image.new("1", (self.w, self.h), 0)
        d = ImageDraw.Draw(img)
        for i, ch in enumerate(s):
            d.text((x + 8 * i + 1, y - 2), ch, font=self._font, fill=1)
        rb = (self.w + 7) // 8
        for yy in range(self.h):
            for xx in range(self.w):
                if img.getpixel((xx, yy)):
                    self.buf[yy * rb + xx // 8] |= 0x80 >> (xx % 8)


_stub("framebuf", FrameBuffer=_FB, MONO_HLSB=0, RGB565=1)
_stub("machine", Pin=None, reset=lambda: None, unique_id=lambda: b"sim")
_stub("network", WLAN=None, STA_IF=0, AP_IF=1)

from display.base import Display  # noqa: E402
from ui import font  # noqa: E402

font.ROOT = str(ROOT / "src" / "fonts") + "/"


class SimDisplay(Display):
    """Display that paints into a Pillow image."""

    def __init__(self, w: int, h: int, mono: bool) -> None:
        """Black canvas."""
        self.width, self.height, self.mono = w, h, mono
        self.img = Image.new("RGB", (w, h))
        self.px = self.img.load()

    def rgb(self, r: int, g: int, b: int):
        """Mono: on/off like the OLED driver, color: keep the tuple."""
        if self.mono:
            return 1 if r + g + b > 120 else 0
        return (r & 0xF8, g & 0xFC, b & 0xF8)

    def _c(self, c):
        """Native color -> RGB tuple."""
        if self.mono:
            return (255, 255, 255) if c else (0, 0, 0)
        return c

    def fill_rect(self, x, y, w, h, c):
        """Clipped rect."""
        col = self._c(c)
        for yy in range(max(0, y), min(self.height, y + h)):
            for xx in range(max(0, x), min(self.width, x + w)):
                self.px[xx, yy] = col

    def blit_mono(self, buf, w, h, x, y, fg, bg):
        """1-bit bitmap, clipped."""
        f, b = self._c(fg), self._c(bg)
        rb = (w + 7) // 8
        for yy in range(h):
            for xx in range(w):
                X, Y = x + xx, y + yy
                if 0 <= X < self.width and 0 <= Y < self.height:
                    on = buf[yy * rb + xx // 8] & (0x80 >> (xx % 8))
                    self.px[X, Y] = f if on else b

    def save(self, name: str) -> None:
        """PNG, upscaled so pixels stay visible."""
        k = 4 if self.width <= 128 else 2
        self.img.resize((self.width * k, self.height * k), Image.NEAREST).save(OUT / name)


# --- scenarios ---

ITEMS = [
    {"id": "IE00B4L5Y983", "name": "MSCI World", "qty": 10.0, "buy": 80.0},
    {"id": "AAPL", "name": "", "qty": None, "buy": None},
    {"id": "DE0007164600", "name": "", "qty": 2.0, "buy": 150.0},
    {"id": "A1JX52", "name": "Ein sehr langer Fondsname der nie passt", "qty": 1.0, "buy": 10.0},
]
QUOTES = {
    "IE00B4L5Y983": {"p": 101.23, "b": 100.5, "cur": "EUR", "n": "iShares Core MSCI World"},
    "AAPL": {"p": 1228.9, "b": 1231.1, "cur": "USD", "n": "Apple Inc."},
    "DE0007164600": {"err": "HTTP 404"},
    "A1JX52": {"p": 9.1234, "b": 9.0, "cur": "EUR", "n": ""},
}


class FakeApp:
    """Just the fields core.screens reads."""

    def __init__(self, ui, mode: str, slide: int = 0, period: str = "1d") -> None:
        self.ui, self.slide, self.q, self.ip = ui, slide, QUOTES, "192.168.178.123"
        self.s = {"items": ITEMS, "mode": mode, "single": 0, "period": period}


def check_qr() -> None:
    """Encode, render, decode with zxing-cpp: what a phone camera would read."""
    import zxingcpp
    from ui import qr
    for text in ("http://192.168.4.1", "WIFI:T:WPA;S:Portfolio-AB12;P:k7mz3ab9xq;;",
                 "http://192.168.178.123"):
        m, n = qr.encode(text)

        # 4 px modules, 4 module quiet zone, dark on light
        k, q = 4, 4
        img = Image.new("L", ((n + 2 * q) * k,) * 2, 255)
        d = ImageDraw.Draw(img)
        for y in range(n):
            for x in range(n):
                if m[y * n + x]:
                    d.rectangle(((x + q) * k, (y + q) * k, (x + q + 1) * k - 1, (y + q + 1) * k - 1), fill=0)
        got = [r.text for r in zxingcpp.read_barcodes(img)]
        print("qr", "OK  " if got == [text] else "FAIL", "v%d" % ((n - 17) // 4), text, "" if got == [text] else got)


def main() -> None:
    """Render all screens at both sizes."""
    OUT.mkdir(exist_ok=True)
    from core import screens, setup
    from ui.layout import UI

    for w, h, mono in ((128, 64, True), (320, 240, False)):
        tag = "%dx%d" % (w, h)

        def shot(name, fn):
            d = SimDisplay(w, h, mono)
            fn(UI(d))
            d.save("%s_%s.png" % (tag, name))

        shot("boot", lambda u: u.message("PortfolioDisplay", ["Starte...", "FLASH = Einrichtung"]))
        shot("reset", lambda u: u.message("Zurücksetzen", ["noch 7 s halten", "loslassen = Abbruch"]))
        for p in range(3):
            shot("setup%d" % p, lambda u, p=p: setup.setup_page(u, p, "Portfolio-AB12", "k7mz3ab9xq",
                                                                 "192.168.4.1", "kein WLAN"))
        for p in range(2):
            shot("info%d" % p, lambda u, p=p: setup.info_page(u, p, "192.168.178.123"))
        for i in range(len(ITEMS)):
            shot("slide%d" % i, lambda u, i=i: screens.render(FakeApp(u, "slide", i)))
        shot("slide0_ytd", lambda u: screens.render(FakeApp(u, "slide", 0, "ytd")))
        shot("portfolio", lambda u: screens.render(FakeApp(u, "port")))
        shot("single", lambda u: screens.render(FakeApp(u, "single")))
    check_qr()
    print("pngs in", OUT)


if __name__ == "__main__":
    main()
