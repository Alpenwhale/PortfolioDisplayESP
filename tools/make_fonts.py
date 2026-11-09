"""Render TTF fonts into tiny 1-bit .bin files the board reads glyph by glyph.

Usage: uv run tools/make_fonts.py [--ttf path/to/font.ttf]
Default font is Aileron (bundled with Pillow, CC0), close to Helvetica.
Aileron lacks umlauts/€/°, so those get composed from base glyphs.

.bin layout (little endian):
    b"PF" | height u8 | count u16 | chars_len u16 | chars utf8 | widths u8*count
    | offsets u16*count (into data) | data (MONO_HLSB rows, ceil(w/8) bytes per row)
"""
import argparse
import struct
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "src" / "fonts"
TEXT = "".join(chr(c) for c in range(32, 127)) + "ÄÖÜäöüß€°"
NUM = "0123456789.,+-% €$"

# name: (px size, charset). l/xl only carry digits + symbols, keeps flash small.
FONTS = {
    "s": (13, TEXT),
    "m": (20, TEXT),
    "l": (36, NUM),
    "xl": (60, NUM),
}
THRESHOLD = 110
UMLAUT = {"ä": "a", "ö": "o", "ü": "u", "Ä": "A", "Ö": "O", "Ü": "U"}
FALLBACK = {"€": "C", "°": " ", "ß": "ss"}


def load(ttf: str | None, size: int) -> ImageFont.FreeTypeFont:
    """TTF if given, else Pillow's bundled Aileron."""
    return ImageFont.truetype(ttf, size) if ttf else ImageFont.load_default(size)


def _raster(font: ImageFont.FreeTypeFont, ch: str) -> bytes:
    """Raw render for comparisons."""
    img = Image.new("L", (font.size * 2, font.size * 2), 0)
    ImageDraw.Draw(img).text((0, 0), ch, font=font, fill=255)
    return img.tobytes()


def missing(font: ImageFont.FreeTypeFont, ch: str) -> bool:
    """True if the font would draw its tofu box."""
    return _raster(font, ch) == _raster(font, "￿")


def glyph(font: ImageFont.FreeTypeFont, ch: str, pad: int) -> tuple[Image.Image, int]:
    """Render one char (grayscale) + advance. Composes umlauts / € / ° if missing."""
    size = font.size
    base = ch if not missing(font, ch) else UMLAUT.get(ch) or FALLBACK.get(ch, "?")
    adv = max(1, round(font.getlength(base)))
    asc, desc = font.getmetrics()
    img = Image.new("L", (adv + 4, asc + desc + 2 * pad), 0)
    d = ImageDraw.Draw(img)
    d.text((0, pad), base, font=font, fill=255)
    if base == ch:
        return img, adv
    l, t, r, b = img.getbbox() or (0, pad, adv, pad + size)
    if ch in UMLAUT:
        rad = max(1, round(size * 0.06))
        cy = t - rad - max(1, round(size * 0.07))
        for cx in ((l + r) / 2 - size * 0.14, (l + r) / 2 + size * 0.14):
            d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), fill=255)
    elif ch == "€":
        sw = max(1, round(size * 0.05))
        for fy in (0.36, 0.58):
            y = round(t + (b - t) * fy)
            d.rectangle((round(l - size * 0.08), y, round((l + r) / 2), y + sw - 1), fill=255)
    elif ch == "°":
        rad = size * 0.12
        cx, cy = size * 0.18, pad + asc - size * 0.62
        d.ellipse((cx - rad, cy - rad, cx + rad, cy + rad), outline=255, width=max(1, round(size * 0.06)))
    return img, adv


def render(font: ImageFont.FreeTypeFont, chars: str) -> tuple[int, list[tuple[int, bytes]]]:
    """1-bit glyphs, all cropped to the charset's common vertical bbox."""
    pad = font.size // 4  # headroom for composed umlaut dots
    imgs = []
    top, bottom = 10**6, 0
    for ch in chars:
        img, w = glyph(font, ch, pad)
        img = img.point(lambda v: 255 if v > THRESHOLD else 0).convert("1")
        bbox = img.getbbox()
        if bbox:
            w = max(w, bbox[2])
            top, bottom = min(top, bbox[1]), max(bottom, bbox[3])
        imgs.append((w, img))
    h = bottom - top
    glyphs = []
    for w, img in imgs:
        g = img.crop((0, top, w, bottom))
        row = (w + 7) // 8
        data = bytearray(row * h)
        for y in range(h):
            for x in range(w):
                if g.getpixel((x, y)):
                    data[y * row + x // 8] |= 0x80 >> (x % 8)
        glyphs.append((w, bytes(data)))
    return h, glyphs


def write(path: Path, h: int, chars: str, glyphs: list[tuple[int, bytes]]) -> int:
    """Pack into .bin, returns size."""
    cb = chars.encode()
    offs, data = [], bytearray()
    for _, g in glyphs:
        offs.append(len(data))
        data += g
    blob = (b"PF" + struct.pack("<BHH", h, len(chars), len(cb)) + cb
            + bytes(w for w, _ in glyphs) + struct.pack("<%dH" % len(offs), *offs) + data)
    path.write_bytes(blob)
    return len(blob)


def main() -> None:
    """Build all fonts."""
    ap = argparse.ArgumentParser()
    ap.add_argument("--ttf")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (size, chars) in FONTS.items():
        h, glyphs = render(load(args.ttf, size), chars)
        n = write(OUT / f"{name}.bin", h, chars, glyphs)
        print(f"{name}: {size}px -> height {h}, {len(chars)} glyphs, {n} bytes")


if __name__ == "__main__":
    main()
