"""Data card: label / big value / sub lines. Only loaded in normal mode (RAM)."""
from ui import font

BIG = ("xl", "l", "m", "s")  # center value, largest first


def card(ui, labels: list, value: str, unit: str, color: int,
         subs: list, page: tuple = (0, 1)) -> None:
    """label / big value+unit / sub lines. subs = [(options, color, trend)], trend != 0 draws an arrow."""
    d, f, gap = ui.d, ui.f, ui.gap
    dots = 10 if page[1] > 1 and d.height >= 100 and page[1] * 10 < d.width else 0
    room = d.width - 2 * ui.m

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
    d.fill(ui.bg)

    # label: name if it fits, else the id
    ui.center(f, ui.fit(f, labels), y, ui.dim)
    y += f.height + gap

    # value, unit bottom-aligned (smaller font if the big one lacks the glyphs)
    x = d.draw(vf, value, (d.width - vw) // 2, y, color, ui.bg)
    if unit:
        d.draw(uf, unit, x + sep, y + vf.height - uf.height, color, ui.bg)
    y += vf.height + gap

    # sub lines, change lines get an up/down arrow
    for opts, c, trend in subs:
        arrow = f.height * 5 // 8 if trend else 0
        aw = arrow * 7 // 4
        s = ui.fit(f, opts, room - aw)
        x = (d.width - f.width(s) - aw) // 2
        if arrow:
            d.triangle(x + arrow * 5 // 8, y + (f.height - arrow) // 2, arrow, trend > 0, c)
        d.draw(f, s, x + aw, y, c, ui.bg)
        y += f.height + gap

    # slideshow position dots
    if dots:
        x = (d.width - page[1] * 10) // 2 + 3
        for i in range(page[1]):
            d.fill_rect(x + i * 10, d.height - 7, 4, 4, ui.fg if i == page[0] else ui.dim)
    d.show()
