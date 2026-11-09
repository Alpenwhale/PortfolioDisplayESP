"""Screen layouts sized from the display. Trade Republic look: black, white, green/red.

Small = 0.96" OLED class (128x64): fixed pages, nothing scrolls, fonts shrink to fit.
Big = 2.8" TFT class: everything on one screen.
"""
from ui import font


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

