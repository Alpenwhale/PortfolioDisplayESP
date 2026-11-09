"""Bitmap fonts from /fonts/*.bin, glyphs read from flash on demand (no RAM for data)."""
import struct


class Font:
    """One .bin font. See tools/make_fonts.py for the layout."""

    def __init__(self, path: str) -> None:
        """Read header + index, keep file open."""
        f = open(path, "rb")
        self.height, n, cl = struct.unpack("<BHH", f.read(7)[2:])
        self.chars = f.read(cl).decode()
        self.widths = f.read(n)
        self._offs = f.read(2 * n)
        self._data = 7 + cl + 3 * n
        self._f = f

    def index(self, ch: str) -> int:
        """Glyph index or -1."""
        return self.chars.find(ch)

    def width(self, s: str) -> int:
        """Pixel width of s, unknown chars count as 0."""
        w = 0
        for ch in s:
            i = self.chars.find(ch)
            if i >= 0:
                w += self.widths[i]
        return w

    def glyph(self, i: int) -> bytearray:
        """Raw MONO_HLSB rows of glyph i."""
        off = self._offs[2 * i] | self._offs[2 * i + 1] << 8
        self._f.seek(self._data + off)
        return bytearray(self._f.read(((self.widths[i] + 7) // 8) * self.height))


_cache = {}


def get(name: str) -> Font:
    """Cached font by name (s, m, l, xl)."""
    f = _cache.get(name)
    if f is None:
        f = _cache[name] = Font("/fonts/%s.bin" % name)
    return f
