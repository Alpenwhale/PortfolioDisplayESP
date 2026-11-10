"""Common display interface. Drivers implement fill_rect + blit_mono, the rest is shared."""
import framebuf


class Display:
    """Base for all displays. Colors are whatever rgb() returns."""

    width: int = 0
    height: int = 0
    mono: bool = False

    def rgb(self, r: int, g: int, b: int) -> int:
        """Convert 8-bit RGB to native color."""
        raise NotImplementedError

    def fill_rect(self, x: int, y: int, w: int, h: int, color: int) -> None:
        """Fill a rectangle."""
        raise NotImplementedError

    def blit_mono(self, buf: bytearray, w: int, h: int, x: int, y: int, fg: int, bg: int) -> None:
        """Draw a MONO_HLSB bitmap, 1 = fg, 0 = bg."""
        raise NotImplementedError

    def brightness(self, pct: int) -> bool:
        """Dim the panel itself. False = can't, the ui darkens its colors instead."""
        return False

    def show(self) -> None:
        """Flush buffer. No-op for unbuffered displays."""

    def fill(self, color: int) -> None:
        """Fill whole screen."""
        self.fill_rect(0, 0, self.width, self.height, color)

    def text(self, s: str, x: int, y: int, fg: int, bg: int = 0) -> None:
        """Builtin 8x8 font, fallback for tiny stuff."""
        w = 8 * len(s)
        buf = bytearray(((w + 7) // 8) * 8)
        fb = framebuf.FrameBuffer(buf, w, 8, framebuf.MONO_HLSB)
        fb.text(s, 0, 0, 1)
        self.blit_mono(buf, w, 8, x, y, fg, bg)

    def draw(self, font, s: str, x: int, y: int, fg: int, bg: int = 0) -> int:
        """Draw s with a ui.font font, returns end x. Clips at right edge."""

        # builtin 8x8 has no glyph table
        if not hasattr(font, "glyph"):
            self.text(s, x, y, fg, bg)
            return x + font.width(s)

        # proportional: one blit per glyph
        h = font.height
        for ch in s:
            i = font.index(ch)
            if i < 0:
                continue
            w = font.widths[i]
            if x + w > self.width:
                break
            self.blit_mono(font.glyph(i), w, h, x, y, fg, bg)
            x += w
        return x

    def triangle(self, cx: int, y: int, size: int, up: bool, color: int) -> None:
        """Filled isosceles triangle, size = height, apex up or down."""
        for r in range(size):
            half = (r if up else size - 1 - r) * 5 // 8
            self.fill_rect(cx - half, y + r, 2 * half + 1, 1, color)
