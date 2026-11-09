"""Screen layouts sized from the display. Trade Republic look: black, white, green/red.

Small = 0.96" OLED class (128x64): fixed pages, nothing scrolls, fonts shrink to fit.
Big = 2.8" TFT class: everything on one screen.
"""
from ui import font

BIG = ("xl", "l", "m", "s")  # center value, largest first


class UI:
    """Draws whole screens. Content comes in as plain strings."""

    def __init__(self, d) -> None:
        """Palette + size class for this display."""
        self.d = d

        # palette, mono displays map it to on/off
        self.bg = d.rgb(0, 0, 0)
        self.fg = d.rgb(255, 255, 255)
        self.dim = d.rgb(140, 140, 145)
        self.up = d.rgb(0, 200, 110)
        self.down = d.rgb(255, 80, 80)

        # size class drives fonts + spacing
        self.small = d.width < 200 or d.height < 160
        self.texts = ("s", "b8") if self.small else ("m", "s", "b8")
        self.f = font.get(self.texts[0])
        self.m = 2 if self.small else max(4, d.width // 40)
        self.gap = 2 if self.small else max(3, d.height // 30)

    # --- primitives ---

    def tone(self, v: float) -> int:
        """Green/red/white by sign."""
        return self.up if v > 0 else self.down if v < 0 else self.fg

    def fit(self, f, options: list, room: int = 0) -> str:
        """First option that fits the width, else the last one cut down."""
        room = room or self.d.width - 2 * self.m
        for s in options:
            if f.width(s) <= room:
                return s

        # nothing fits: shorten the last (= shortest) option
        s = options[-1]
        while s and f.width(s + "..") > room:
            s = s[:-1]
        return s + ".."

    def pick(self, s: str, room: int, names: tuple = ()) -> tuple:
        """(font, text): largest font from names in which s fits, else smallest + cut."""
        names = names or self.texts
        for n in names:
            f = font.get(n)
            if f.width(s) <= room:
                return f, s
        f = font.get(names[-1])
        return f, self.fit(f, [s], room)

    def center(self, f, s: str, y: int, c: int, x0: int = 0, w: int = 0) -> None:
        """Draw s centered in [x0, x0 + w)."""
        w = w or self.d.width
        self.d.draw(f, s, x0 + (w - f.width(s)) // 2, y, c, self.bg)

    def qr(self, mat, n: int, x: int, y: int, scale: int, quiet: int = 1) -> int:
        """Draw a QR matrix as dark-on-light, returns its pixel side."""
        side = (n + 2 * quiet) * scale
        rb = (side + 7) // 8

        # one module row at a time: build a 1-bit line, repeat it scale times, blit
        for my in range(-quiet, n + quiet):
            row = bytearray(rb)
            if 0 <= my < n:
                for mx in range(n):
                    if mat[my * n + mx]:
                        for k in range(scale):
                            px = (mx + quiet) * scale + k
                            row[px >> 3] |= 0x80 >> (px & 7)
            # bytearray * int doesn't exist on esp8266, copy rows by slice
            buf = bytearray(rb * scale)
            for k in range(scale):
                buf[k * rb:(k + 1) * rb] = row
            self.d.blit_mono(buf, side, scale, x, y + (my + quiet) * scale, self.bg, self.fg)
        return side

    # --- screens ---

    def column(self, lines: list, x0: int = 0, w: int = 0, names: tuple = ()) -> None:
        """Vertically centered lines [(text, color)] in [x0, x0 + w), each in the largest fitting font."""
        d = self.d
        w = w or d.width
        room = w - 2 * self.m

        # fonts first, then drop lines from the bottom until the stack fits the height
        rows = [self.pick(s, room, names) + (c,) for s, c in lines]
        while rows and sum(f.height for f, _, _ in rows) + self.gap * (len(rows) - 1) > d.height:
            rows.pop()

        y = (d.height - sum(f.height for f, _, _ in rows) - self.gap * (len(rows) - 1)) // 2
        for f, s, c in rows:
            self.center(f, s, y, c, x0, w)
            y += f.height + self.gap

    def message(self, title: str, lines: list) -> None:
        """Title + dim lines, whole screen."""
        self.d.fill(self.bg)
        self.column([(title, self.fg)] + [(s, self.dim) for s in lines])
        self.d.show()

    def card(self, labels: list, value: str, unit: str, color: int,
             subs: list, page: tuple = (0, 1)) -> None:
        """label / big value+unit / sub lines. subs = [(options, color, trend)], trend != 0 draws an arrow."""
        d, f, gap = self.d, self.f, self.gap
        dots = 10 if page[1] > 1 and d.height >= 100 and page[1] * 10 < d.width else 0
        room = d.width - 2 * self.m

        # unit with a leading space = gap before it ("12,50 €" vs "+1.2%")
        spaced = unit[:1] == " "
        unit = unit.strip()

        # biggest value font that fits the width and leaves room for label + one sub line
        for name in BIG:
            vf = font.get(name)
            uf = vf if all(vf.index(c) >= 0 for c in unit) else f
            sep = vf.width(" ") if spaced else 0
            vw = vf.width(value) + sep + uf.width(unit)
            if vw <= room and f.height * 2 + vf.height + 2 * gap + dots <= d.height:
                break

        # keep only the sub lines that still fit vertically
        avail = d.height - dots - f.height - vf.height - 2 * gap
        n = 0
        while n < len(subs) and avail >= f.height + (gap if n else 0):
            avail -= f.height + (gap if n else 0)
            n += 1
        subs = subs[:n]

        # vertical centering of the whole stack
        total = f.height + gap + vf.height + sum(f.height + gap for _ in subs)
        y = max(0, (d.height - dots - total) // 2)
        d.fill(self.bg)

        # label: name if it fits, else the id
        self.center(f, self.fit(f, labels), y, self.dim)
        y += f.height + gap

        # value, unit bottom-aligned (smaller font if the big one lacks the glyphs)
        x = d.draw(vf, value, (d.width - vw) // 2, y, color, self.bg)
        if unit:
            d.draw(uf, unit, x + sep, y + vf.height - uf.height, color, self.bg)
        y += vf.height + gap

        # sub lines, change lines get an up/down arrow
        for opts, c, trend in subs:
            arrow = f.height * 5 // 8 if trend else 0
            aw = arrow * 7 // 4
            s = self.fit(f, opts, room - aw)
            x = (d.width - f.width(s) - aw) // 2
            if arrow:
                d.triangle(x + arrow * 5 // 8, y + (f.height - arrow) // 2, arrow, trend > 0, c)
            d.draw(f, s, x + aw, y, c, self.bg)
            y += f.height + gap

        # slideshow position dots
        if dots:
            x = (d.width - page[1] * 10) // 2 + 3
            for i in range(page[1]):
                d.fill_rect(x + i * 10, d.height - 7, 4, 4, self.fg if i == page[0] else self.dim)
        d.show()
