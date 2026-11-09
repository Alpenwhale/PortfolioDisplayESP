"""Screen layouts, sized from the display. Trade Republic look: black, white, green/red."""
from display import font

BIG = ("xl", "l", "m", "s")  # tried largest first for the center value
CUR = {"EUR": "€", "USD": "$"}


def num(v: float, dec: int = 2) -> str:
    """German number: 1.234,56"""
    s = ("%." + str(dec) + "f") % abs(v)
    ip, fp = (s.split(".") + [""])[:2]  # no str.partition on esp8266
    g = ""
    while len(ip) > 3:
        g = "." + ip[-3:] + g
        ip = ip[:-3]
    return ("-" if v < 0 else "") + ip + g + ("," + fp if fp else "")


def signed(v: float, dec: int = 2) -> str:
    """num with explicit +."""
    return ("+" if v >= 0 else "") + num(v, dec)


def cur(code: str) -> str:
    """Currency symbol or code."""
    return CUR.get(code, code)


class UI:
    """Draws whole screens. Content comes from the app as plain strings."""

    def __init__(self, d) -> None:
        """Pick colors + text fonts for this screen size."""
        self.d = d
        self.bg = d.rgb(0, 0, 0)
        self.fg = d.rgb(255, 255, 255)
        self.dim = d.rgb(140, 140, 145)
        self.up = d.rgb(0, 200, 110)
        self.down = d.rgb(255, 80, 80)
        self.f = font.get("m" if d.width >= 200 and d.height >= 160 else "s")
        self.m = max(3, d.width // 40)  # margin
        self.gap = max(2, d.height // 30)

    def tone(self, v: float) -> int:
        """Green/red/white by sign."""
        return self.up if v > 0 else self.down if v < 0 else self.fg

    def _fit(self, f, options: list, room: int = 0) -> str:
        """First option that fits the width, else last one cut down."""
        room = room or self.d.width - 2 * self.m
        for s in options:
            if f.width(s) <= room:
                return s
        s = options[-1]
        while s and f.width(s + "..") > room:
            s = s[:-1]
        return s + ".."

    def _center(self, f, s: str, y: int, color: int) -> None:
        """Draw s centered horizontally."""
        self.d.draw(f, s, (self.d.width - f.width(s)) // 2, y, color, self.bg)

    def message(self, title: str, lines: list) -> None:
        """Title + small lines, vertically centered."""
        d, f = self.d, self.f
        title_f = font.get("m") if d.width >= 120 else f
        h = title_f.height + self.gap * 2 + len(lines) * (f.height + self.gap)
        y = max(0, (d.height - h) // 2)
        d.fill(self.bg)
        self._center(title_f, self._fit(title_f, [title]), y, self.fg)
        y += title_f.height + self.gap * 2
        for s in lines:
            if y + f.height > d.height:
                break
            self._center(f, self._fit(f, [s]), y, self.dim)
            y += f.height + self.gap
        d.show()

    def card(self, labels: list, value: str, unit: str, color: int, trend: float,
             subs: list, page: tuple = (0, 1)) -> None:
        """label / big value+unit / sub lines. subs = [(options, color)], arrow on the first."""
        d, f, gap = self.d, self.f, self.gap
        dots = 10 if page[1] > 1 and d.height >= 100 and page[1] * 10 < d.width else 0
        room_w = d.width - 2 * self.m

        # biggest value font that fits width, and height with label + one sub line
        for name in BIG:
            vf = font.get(name)
            uf = vf if all(vf.index(c) >= 0 for c in unit) else f
            sep = vf.width(" ") if unit else 0
            vw = vf.width(value) + sep + uf.width(unit)
            if vw <= room_w and f.height * 2 + vf.height + 2 * gap + dots <= d.height:
                break

        # drop sub lines that don't fit vertically
        avail = d.height - dots - f.height - vf.height - 2 * gap
        n = 0
        while n < len(subs) and avail >= f.height + (gap if n else 0):
            avail -= f.height + (gap if n else 0)
            n += 1
        subs = subs[:n]

        total = f.height + gap + vf.height + sum(f.height + gap for _ in subs)
        y = max(0, (d.height - dots - total) // 2)
        d.fill(self.bg)

        self._center(f, self._fit(f, labels), y, self.dim)
        y += f.height + gap

        x = (d.width - vw) // 2
        x = d.draw(vf, value, x, y, color, self.bg)
        if unit:
            d.draw(uf, unit, x + sep, y + vf.height - uf.height, color, self.bg)
        y += vf.height + gap

        for i, (opts, c) in enumerate(subs):
            arrow = f.height * 5 // 8 if i == 0 and trend else 0
            aw = arrow * 7 // 4 if arrow else 0
            s = self._fit(f, opts, room_w - aw)
            x = (d.width - f.width(s) - aw) // 2
            if arrow:
                d.triangle(x + arrow * 5 // 8, y + (f.height - arrow) // 2, arrow, trend > 0, c)
            d.draw(f, s, x + aw, y, c, self.bg)
            y += f.height + gap

        if dots:
            x = (d.width - page[1] * 10) // 2 + 3
            for i in range(page[1]):
                d.fill_rect(x + i * 10, d.height - 7, 4, 4, self.fg if i == page[0] else self.dim)
        d.show()
