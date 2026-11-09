"""Bitmap fonts from /fonts/*.bin, glyphs read from flash on demand (no RAM for data)."""
import struct

ROOT = "/fonts/"  # host simulator points this at src/fonts/


class Font:
    """One .bin font. See tools/make_fonts.py for the layout."""

    def __init__(self, path: str) -> None:
        """Read header + index. Glyph file opens lazily, release() closes it."""
        self._path = path
        with open(path, "rb") as f:
            self.height, n, cl = struct.unpack("<BHH", f.read(7)[2:])
            self.chars = f.read(cl).decode()
            self.widths = f.read(n)
            self._offs = f.read(2 * n)
        self._data = 7 + cl + 3 * n
        self._f = None

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
        """Raw MONO_HLSB rows of glyph i, read from flash."""
        if self._f is None:
            self._f = open(self._path, "rb")
        off = self._offs[2 * i] | self._offs[2 * i + 1] << 8
        self._f.seek(self._data + off)
        return bytearray(self._f.read(((self.widths[i] + 7) // 8) * self.height))

    def close(self) -> None:
        """Drop the open file (each one holds ~0.5 KB sector buffer)."""
        if self._f:
            self._f.close()
            self._f = None


class Builtin:
    """framebuf's 8x8 font with the Font interface. Crisp on tiny OLEDs."""

    height = 8

    def index(self, ch: str) -> int:
        """ASCII only."""
        return 0 if " " <= ch <= "~" else -1

    def width(self, s: str) -> int:
        """Fixed 8 px per char."""
        return 8 * len(s)


B8 = Builtin()
_cache = {}


def release() -> None:
    """After a screen is drawn: close files and forget the indexes (re-read from flash next time)."""
    for f in _cache.values():
        f.close()
    _cache.clear()


def get(name: str):
    """Cached font by name: s, m, l, xl or b8."""
    if name == "b8":
        return B8
    f = _cache.get(name)
    if f is None:
        f = _cache[name] = Font(ROOT + name + ".bin")
    return f
