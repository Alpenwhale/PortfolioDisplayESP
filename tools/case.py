# /// script
# requires-python = ">=3.12"
# dependencies = ["manifold3d", "numpy", "pillow"]
# ///
"""Retro TV style desk cases for the 2.8" TFT and the 0.96" OLED + NodeMCU v3.

Writes the print files to 3d/ and preview images to docs/img/3d/.
Run: uv run tools/case.py
"""
import math
import zipfile
from pathlib import Path

import numpy as np
from manifold3d import CrossSection, Manifold
from PIL import Image, ImageDraw

# --- displays, landscape, sizes in mm; check with the fit frame ---
# PCB_L/PCB_H    PCB size
# STACK_T        glass front to PCB back, without pins
# ACT_W/ACT_H    visible image
# ACT_END        PCB end without pins to image edge (only with side pins)
# ACT_Z          image center vs PCB center, + = up
# HEADER         pins: -1 left end, 1 right end, 0 top edge (seen from front)
# HEADER_SPAN    rail cut-out for side pins
# LIFT           PCB bottom above base top
# DISP_X         display center vs case center
# ESP_ALONG      "x": board crosswise, USB right; "y": lengthwise, USB at the back
# DECOR          candle chart on the "chin" or the right side "wall"
# BEZEL          CRT look: front frame this much wider per side (0 = plain box)
# ROOF           CRT look: roof line as (y, drop) points, () = flat
# SPLIT          True: back panel + roof that slides in from the back (flat roof only)
VARIANTS = {
    # ZJY280S0800TG01, blue 8 pin board; from photos, PCB edge 0.7 past the glass
    "tft": dict(PCB_L=83.0, PCB_H=51.4, STACK_T=4.8, ACT_W=57.6, ACT_H=43.2, ACT_END=15.8,
                ACT_Z=0.0, HEADER=-1, HEADER_SPAN=24.0, LIFT=9.0, DISP_X=0.0,
                ESP_ALONG="x", DECOR="chin", BEZEL=0.0, ROOF=(), SPLIT=True),
    # 0.96" SSD1306 I2C, 4 pins on top; their plugs run back between the board's pin rows
    # roof: wires on the pin rows need ~30 mm up to y ~60, behind that only the USB plug
    "oled": dict(PCB_L=27.3, PCB_H=27.8, STACK_T=2.8, ACT_W=21.74, ACT_H=10.86, ACT_END=2.78,
                 ACT_Z=1.5, HEADER=0, HEADER_SPAN=0.0, LIFT=2.0, DISP_X=0.0,
                 ESP_ALONG="y", DECOR="wall", BEZEL=2.5,
                 ROOF=((44, 0), (61, 3.5), (74, 14)), SPLIT=False),
}
BEZEL_D = 10.0       # depth of the wider front frame

# --- NodeMCU v3, lies upside down (buttons down, pins up) ---
ESP_L = 58.0         # length incl. USB socket
ESP_W = 31.5
ESP_LIFT = 6.0       # base top to component side
USB_HOLE = (13.0, 8.0)  # plug opening, w x h

# --- case ---
TILT = 12.0          # screen leans back (deg)
WALL = 2.0
BASE_T = 2.0
FIT = 0.3            # sliding clearance, PETG
VISOR = 3.0          # roof overhang at the front
R_FRONT = 6.0        # front corner radius
PLINTH = 4.0         # foot band height
SEG = 48

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "3d"
IMG = ROOT / "docs" / "img" / "3d"
BUILD = ROOT / "build" / "case"

# fixed derived
T = math.radians(TILT)
C, TN = math.cos(T), math.tan(T)
LIP = 2.0                            # rail overlap on the PCB edge
RAIL = 1.6                           # rail thickness behind the PCB
ROOF_T = 2.0
PANEL_T = 1.6
BACK_LIP = 1.4                       # frame around the back panel
CH_IN = 1.6                          # rails stick out of the side wall
LEDGE = 1.4                          # split roof: ledge under the wall top, 45 deg underside
LEDGE_H = 1.0                        # its straight part below the roof
TONGUE = 1.4                         # roof rail inside the ledge, hooks under it
HOOK_H = 1.2


def use(name: str) -> None:
    """Load a display variant and derive all case sizes from it."""
    g = globals()
    g.update(VARIANTS[name], VARIANT=name)

    st = STACK_T / C + 0.5                       # display slot, horizontal
    back = 1.4 + PANEL_T + 2 * FIT + BACK_LIP     # inner rail to the back face

    # board position: crosswise needs width, lengthwise needs depth
    if ESP_ALONG == "x":
        iw = max(PCB_L + 2 * abs(DISP_X) + 6.0, ESP_L + 4.0)
        esp_y0 = WALL + st + RAIL + 7.5          # plugs on the front pin row clear of the rails
        depth = round(esp_y0 + ESP_W + 7.5)
    else:
        iw = max(PCB_L + 2 * abs(DISP_X) + 6.0, ESP_W + 4.5)
        esp_y0 = WALL + st + RAIL + (BASE_T + ESP_LIFT + 1.6) * TN + 0.5  # board clear of the rails
        depth = round(esp_y0 + ESP_L + 0.5 + back + 0.4)
    y_slot = depth - BACK_LIP - PANEL_T - 2 * FIT

    g.update(
        IW=iw, W=iw + 2 * WALL, ST=st, DEPTH=depth,
        Z_PCB=BASE_T + LIFT,
        Z_TOP=BASE_T + LIFT + PCB_H * C + 5.0,   # room for the screen frame
        Y_SLOT=y_slot,                           # front face of the panel channel
        Y_RIB=y_slot - 1.4,                      # front of the inner rail
        ESP_Y0=esp_y0,                           # board front (crosswise: long edge)
        WF=iw + 2 * WALL + 2 * BEZEL,            # front frame width
    )


def under_roof(extra: float = 0.0) -> Manifold:
    """Everything below the roof line (+extra), local frame. Flat, then falling."""
    zt = Z_TOP + extra
    if not ROOF:
        return box(-200, 200, -50, DEPTH + 50, -50, zt)

    # roof line points, last segment extended past the back
    (ya, da), (yb, db) = ROOF[-2], ROOF[-1]
    far = DEPTH + 50
    line = [(y, zt - d) for y, d in ROOF] + [(far, zt - db - (db - da) / (yb - ya) * (far - yb))]
    pts = [(-50, -50), (-50, zt), *line, (far, -50)]
    prof = CrossSection([pts[::-1]])  # counter-clockwise
    # profile drawn in (y, z), extruded along x
    return Manifold.extrude(prof, 400).rotate((90, 0, 90)).translate((-200, 0, 0))


def board_box(u0: float, u1: float, v0: float, v1: float, z0: float, z1: float) -> Manifold:
    """Box in board coords: u from the far end to the USB end, v across, centered."""
    if ESP_ALONG == "x":
        x0 = IW / 2 - 1.5 - ESP_L
        yc = ESP_Y0 + ESP_W / 2
        return box(x0 + u0, x0 + u1, yc + v0, yc + v1, z0, z1)
    return box(v0, v1, ESP_Y0 + u0, ESP_Y0 + u1, z0, z1)


def box(x0: float, x1: float, y0: float, y1: float, z0: float, z1: float) -> Manifold:
    """Axis aligned box from min/max corners."""
    return Manifold.cube((x1 - x0, y1 - y0, z1 - z0)).translate((x0, y0, z0))


def prism_xz(pts: list, y0: float, y1: float) -> Manifold:
    """Polygon in the XZ plane, extruded from y0 to y1."""
    cs = [(x, -z) for x, z in pts]  # rotate(-90 about x) maps section v to -z
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(cs, cs[1:] + cs[:1]))
    sec = CrossSection([cs if area > 0 else cs[::-1]])
    return Manifold.extrude(sec, y1 - y0).rotate((-90, 0, 0)).translate((0, y0, 0))


def dovetail() -> tuple[list, list, float]:
    """Right side (x > 0) of the split roof joint: (wall ledge, roof hook, hook bottom z).

    Ledge hangs from the wall top with a 45 deg underside (prints standing), the roof hook
    reaches under it with the same 45 deg face (prints roof down).
    """
    xw, zt = IW / 2, Z_TOP
    ledge = [(xw, zt), (xw - LEDGE, zt), (xw - LEDGE, zt - LEDGE_H), (xw, zt - LEDGE_H - LEDGE)]
    xt = xw - LEDGE - FIT                       # tongue outer face
    zb = zt - LEDGE_H - LEDGE - FIT - HOOK_H    # hook bottom
    hook = [(xt - TONGUE, zt + 0.01), (xt, zt + 0.01), (xt, zt - LEDGE_H - FIT),
            (xw - FIT, zt - LEDGE_H - LEDGE - FIT), (xw - FIT, zb), (xt - TONGUE, zb)]
    return ledge, hook, zb


def hook_path() -> Manifold:
    """Room the roof hooks need while sliding in from the back (rails, lips, panel corners)."""
    _, hook, zb = dovetail()
    x0 = hook[0][0] - FIT
    out = Manifold()
    for s in (-1, 1):
        xa, xb = sorted((s * x0, s * IW / 2))
        out += box(xa, xb, Y_RIB, DEPTH + 1, zb - FIT, Z_TOP + 1)
    return out


def rrect(w: float, h: float, r: float) -> CrossSection:
    """Centered rounded rectangle."""
    r = min(r, w / 2 - 0.01, h / 2 - 0.01)
    return CrossSection.square((w - 2 * r, h - 2 * r), center=True).offset(r, circular_segments=SEG)


def slab_xz(w: float, h: float, r: float, cx: float, cz: float, y0: float, y1: float) -> Manifold:
    """Rounded rect in the XZ plane, extruded from y0 to y1."""
    return Manifold.extrude(rrect(w, h, r), y1 - y0).rotate((-90, 0, 0)).translate((cx, y0, cz))


def shear(m: Manifold) -> Manifold:
    """Lean everything back by TILT: y += z * tan."""
    return m.transform([[1, 0, 0, 0], [0, 1, TN, 0], [0, 0, 1, 0]])


def window() -> tuple[float, float, float, float]:
    """Image center x/z and opening size, local (unsheared) frame."""
    cx = DISP_X - HEADER * (PCB_L / 2 - ACT_END - ACT_W / 2)
    cz = Z_PCB + (PCB_H / 2 + ACT_Z) * C
    return cx, cz, ACT_W + 1.0, (ACT_H + 1.0) * C


def outline(w: float, y0: float, y1: float, r: float) -> CrossSection:
    """XY outline, round front corners only."""
    sq = CrossSection.square((w, y1 - y0 - r)).translate((-w / 2, y0 + r))
    return sq + rrect(w, 2 * r, r).translate((0, y0 + r))


def shell_local(bezel: bool = True) -> Manifold:
    """Front, sides, base, rails. Open at top and back, unsheared.

    bezel=False keeps the front flat, needed when it lies on the bed.
    """
    # body + wider foot band, CRT front frame, minus cavity (open top + back)
    m = Manifold.extrude(outline(W, 0, DEPTH, R_FRONT), Z_TOP)
    m += Manifold.extrude(outline(W + 1.6, -0.8, DEPTH, R_FRONT + 0.8), PLINTH)
    if BEZEL:
        m += Manifold.extrude(outline(WF, 0, BEZEL_D, R_FRONT), Z_TOP)
        m += Manifold.batch_hull([box(-WF / 2, WF / 2, BEZEL_D - 0.01, BEZEL_D, 0, Z_TOP),
                                  box(-W / 2, W / 2, BEZEL_D + BEZEL, BEZEL_D + BEZEL + 0.01, 0, Z_TOP)])
    m -= box(-IW / 2, IW / 2, WALL, DEPTH + 1, BASE_T, Z_TOP + 1)

    # back channel: inner rail + outer lip on both side walls and the base
    for s in (-1, 1):
        x0, x1 = sorted((s * IW / 2, s * (IW / 2 - CH_IN)))
        m += box(x0, x1, Y_RIB, Y_SLOT, BASE_T, Z_TOP)
        m += box(x0, x1, DEPTH - BACK_LIP, DEPTH, BASE_T, Z_TOP)
    m += box(-IW / 2, IW / 2, Y_RIB, Y_SLOT, BASE_T, BASE_T + 3)
    m += box(-IW / 2, IW / 2, DEPTH - BACK_LIP, DEPTH, BASE_T, BASE_T + 3)

    # walls follow the falling roof
    m ^= under_roof()

    # split roof: ledges from the display slot to the back channel, free path behind
    if SPLIT:
        ledge, _, _ = dovetail()
        for s in (-1, 1):
            m += prism_xz([(s * x, z) for x, z in ledge], WALL + ST + RAIL, Y_RIB)
        m -= hook_path()

    # detent dimples in the inner rails
    for s in (-1, 1):
        m -= Manifold.sphere(1.4, SEG).translate((s * (IW / 2 - 0.9), Y_SLOT, BASE_T + 4))

    # display slot: thin side ribs + rails behind the PCB ends
    for s in (-1, 1):
        edge = DISP_X + s * (PCB_L / 2 + 0.3)
        x0, x1 = sorted((edge, edge + s * 1.2))
        m += box(x0, x1, WALL, WALL + ST + RAIL, BASE_T, Z_TOP)
        x0, x1 = sorted((edge - s * LIP, edge + s * 1.2))
        rail = box(x0, x1, WALL + ST, WALL + ST + RAIL, BASE_T, Z_TOP)
        if s == HEADER:
            zc = Z_PCB + PCB_H / 2 * C
            rail -= box(x0 - 1, x1 + 1, 0, DEPTH, zc - HEADER_SPAN / 2, zc + HEADER_SPAN / 2)
        m += rail

    # display rests on this block
    m += box(DISP_X - PCB_L / 2 + 4, DISP_X + PCB_L / 2 - 4, WALL + 0.3, WALL + ST - 0.3, BASE_T, Z_PCB)

    # screen: raised frame, recess, chamfered opening
    cx, cz, w, h = window()
    face = 0.0
    if bezel:
        ring = slab_xz(w + 13, h + 13, 7, cx, cz, -0.8, 0.5) - slab_xz(w + 7, h + 7, 4.5, cx, cz, -2, 1)
        m += ring ^ box(-W, W, -5, 5, 0, Z_TOP)
        m -= slab_xz(w + 7, h + 7, 4.5, cx, cz, -2, 0.6)
        face = 0.6
    m -= Manifold.batch_hull([slab_xz(w, h, 1.5, cx, cz, WALL - 0.3, WALL + 0.1),
                              slab_xz(w + 2.4, h + 2.4, 2.5, cx, cz, face - 0.01 - (0 if bezel else 1), face)])
    m -= slab_xz(w, h, 1.5, cx, cz, -1, WALL + 0.5)
    if not bezel:
        return m

    # candle chart: right side wall (rising to the back), or on the chin
    if DECOR == "wall":
        art = candles(0, 0, 2.0).rotate((0, 0, 90))
        m -= art.translate((W / 2 - 0.4, DEPTH / 2, (PLINTH + Z_TOP) / 2))
    else:
        m -= candles(cx + w / 2 - 4, (PLINTH + cz - h / 2 - 6.5) / 2 + 0.5)
    return m


def candles(cx: float, cz: float, k: float = 1.0) -> Manifold:
    """Engraved candlestick chart, trending up, scaled by k."""
    out = Manifold()
    for i, (lo, hi) in enumerate(((0, 1.8), (1, 2.6), (0.6, 3.4), (1.8, 4.2), (2.8, 5))):
        x = cx + (i - 2) * 2.8 * k
        z = cz - 2.5 * k
        out += box(x - 0.9 * k, x + 0.9 * k, -1, 0.6, z + lo * k, z + hi * k)
        out += box(x - 0.25 * k, x + 0.25 * k, -1, 0.6, z + (lo - 0.6) * k, z + (hi + 0.6) * k)
    return out


def esp_parts() -> tuple[Manifold, Manifold]:
    """Pads/fences for the board (add) and holes (cut), world frame."""
    L, hw = ESP_L, ESP_W / 2
    top = BASE_T + ESP_LIFT
    add = Manifold()

    # pads under USB socket and ESP-12 shield
    add += board_box(L - 6.5, L - 1, -3.5, 3.5, BASE_T, top - 3.2)
    add += board_box(6, 20, -5, 5, BASE_T, top - 3.4)

    # fences around the board outline
    fz = top + 1.6 + 1.2
    add += board_box(-1.6, -0.4, -hw + 4, hw - 4, BASE_T, fz)
    for u in (1, L - 14):
        add += board_box(u, u + 4, -hw - 1.6, -hw - 0.4, BASE_T, fz)
        add += board_box(u, u + 4, hw + 0.4, hw + 1.6, BASE_T, fz)

    # USB plug opening: right wall, or through the back (shell part, cover has its own notch)
    uw, uh = USB_HOLE
    if ESP_ALONG == "x":
        cut = Manifold.extrude(rrect(uw, uh, 2), WALL + 4).rotate((0, 90, 0)).rotate((90, 0, 0))
        cut = cut.translate((IW / 2 - 1, ESP_Y0 + hw, top - 1.6))
    else:
        cut = box(-uw / 2 - 1, uw / 2 + 1, Y_RIB - 1, DEPTH + 5, BASE_T, top - 1.6 + uh / 2 + 0.5)

    # RST / FLASH access from below, paperclip
    for v0 in (-14, 5):
        cut += board_box(L - 8, L - 1.5, v0, v0 + 9, -1, BASE_T + 0.01)

    # hidden release: push the back cover up through the base, beside the USB notch
    yp = (Y_SLOT + DEPTH - BACK_LIP) / 2 + BASE_T * TN
    cut += Manifold.cylinder(BASE_T + 2, 2.0, circular_segments=SEG).translate((IW / 2 - 6, yp, -1))
    return add, cut


def shell() -> Manifold:
    """Main body in world frame = print orientation."""
    add, cut = esp_parts()
    return shear(shell_local()) + add - cut


def cover_local() -> tuple[Manifold, Manifold]:
    """(back panel, roof), local frame. One part unless SPLIT: then the panel slides down the
    rails and the roof slides in from the back over it, hooked under the wall ledges."""
    # roof outline: visor, wider over the CRT front frame; split roof also covers the channel
    yb = DEPTH - BACK_LIP - FIT
    mask = outline(W + 1.0, -VISOR, DEPTH if SPLIT else yb, R_FRONT + 1)
    if BEZEL:
        mask += outline(WF + 1.0, -VISOR, BEZEL_D, R_FRONT + 1)
    mask = Manifold.extrude(mask, 300).translate((0, 0, -100))
    if BEZEL:
        mask += Manifold.batch_hull([box(-WF / 2 - 0.5, WF / 2 + 0.5, BEZEL_D - 0.01, BEZEL_D, -100, 200),
                                     box(-W / 2 - 0.5, W / 2 + 0.5, BEZEL_D + BEZEL, BEZEL_D + BEZEL + 0.01, -100, 200)])

    # roof band follows the roof line, rounded front edge
    roof = (under_roof(ROOF_T) - under_roof()) ^ mask
    edge = Manifold.cylinder(WF + 4, ROOF_T / 2, circular_segments=SEG).rotate((0, 90, 0))
    edge = edge.translate((-WF / 2 - 2, -VISOR + ROOF_T / 2, Z_TOP + ROOF_T / 2))
    roof = roof ^ Manifold.batch_hull([edge, box(-WF, WF, (DEPTH if SPLIT else yb) - 1, DEPTH if SPLIT else yb,
                                                 -50, Z_TOP + ROOF_T)])

    # panel in the channel up into the roof, vents as a rising bar chart
    px = IW / 2 - FIT
    panel = box(-px, px, Y_SLOT + FIT, yb, BASE_T, Z_TOP) ^ under_roof(0.5)
    n, pitch, bw = (9, 6.0, 2.6) if IW > 60 else (7, 3.8, 2.0)
    z0 = max(Z_TOP - 34, BASE_T + ESP_LIFT + USB_HOLE[1] / 2 + 3)
    hmax = Z_TOP - (ROOF[-1][1] if ROOF else 0) - 4 - z0
    for i in range(n if hmax >= 6 else 0):
        hgt = hmax * (0.25 + 0.75 * i / (n - 1))
        panel -= slab_xz(bw, hgt, bw / 2, (n - 1) / 2 * pitch - i * pitch, z0 + hgt / 2, Y_SLOT, yb + 1)

    # USB notch from the bottom edge, so the cover slides over the plugged cable
    if ESP_ALONG == "y":
        uw, uh = USB_HOLE
        panel -= box(-uw / 2 - 1, uw / 2 + 1, Y_SLOT - 1, yb + 1, 0, BASE_T + ESP_LIFT - 1.6 + uh / 2 + 0.5)

    # detent bumps, clipped so nothing pokes out of the back face (it lies on the bed)
    for s in (-1, 1):
        cap = Manifold.sphere(1.2, SEG).translate((s * (IW / 2 - 0.9), Y_SLOT + FIT + 0.75, BASE_T + 4))
        panel += cap ^ box(-W, W, 0, yb, 0, Z_TOP)

    # split: hooks along the whole roof (front end stops at the display slot), panel corners
    # free for them, two snap bumps that click over the panel top
    if SPLIT:
        _, hook, _ = dovetail()
        for s in (-1, 1):
            roof += prism_xz([(s * x, z) for x, z in hook], WALL + ST + RAIL + FIT, DEPTH)
            roof += Manifold.sphere(1.5, SEG).translate((s * 12, Y_SLOT - 1.2, Z_TOP + 1.0)) ^ \
                box(-W, W, -50, DEPTH, Z_TOP - 1, Z_TOP + 1)
        return panel - hook_path(), roof

    # locating rims under the roof, 45 deg end so they print without support
    for s in (-1, 1):
        x0, x1 = sorted((s * (IW / 2 - FIT), s * (IW / 2 - FIT - 1.2)))
        y0, y1 = WALL + ST + RAIL + 1, (min(Y_RIB, ROOF[0][0]) if ROOF else Y_RIB) - 1
        panel += Manifold.batch_hull([box(x0, x1, y0, y1 - 3, Z_TOP - 3, Z_TOP + 0.5),
                                      box(x0, x1, y0, y1, Z_TOP - 0.01, Z_TOP + 0.5)])  # into the roof
    return roof + panel, Manifold()


def cover() -> tuple[Manifold, Manifold]:
    """Cover part(s) in world frame = assembled. Printed like this too: the back panel leans
    with the rails, a part printed unsheared would sit 12 deg off once it is in."""
    a, b = cover_local()
    return shear(a), shear(b)


def fit_frame() -> Manifold:
    """Front + display slot only, true size, lies flat: check fit first.

    Starts at the PCB bottom edge, so the frame edge shows where the PCB sits.
    """
    m = shell_local(bezel=False) ^ box(-W, W, 0, WALL + ST + RAIL, Z_PCB, Z_TOP)
    return m.scale((1, C, 1 / C))


def warmup() -> Manifold:
    """Small badge with a candle chart, primes the nozzle on the first layers."""
    m = Manifold.extrude(rrect(40, 20, 4), 2.4)
    for i, (lo, hi) in enumerate(((0, 4), (2, 6), (1.5, 8), (4, 10), (6, 13))):
        x = -12 + i * 6
        m -= box(x - 2, x + 2, -6.5 + lo, -6.5 + hi, 1.8, 3)
        m -= box(x - 0.5, x + 0.5, -7.5 + lo, -5.5 + hi, 1.8, 3)
    return m


def to_print(m: Manifold, rot: tuple[float, float, float]) -> Manifold:
    """Rotate and drop onto the bed at the origin."""
    m = m.rotate(rot)
    (x0, y0, z0, x1, y1, _) = m.bounding_box()
    return m.translate((-(x0 + x1) / 2, -(y0 + y1) / 2, -z0))


def mesh(m: Manifold) -> tuple[np.ndarray, np.ndarray]:
    """Vertices + triangles."""
    msh = m.to_mesh()
    return np.asarray(msh.vert_properties)[:, :3], np.asarray(msh.tri_verts)


def write_stl(m: Manifold, path: Path) -> None:
    """Binary STL."""
    v, t = mesh(m)
    tri = v[t]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
    rec = np.zeros(len(t), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
    rec["n"], rec["v"] = n, tri
    with open(path, "wb") as f:
        f.write(b"tft case".ljust(80, b" "))
        f.write(np.uint32(len(t)).tobytes())
        f.write(rec.tobytes())


def write_3mf(parts: list[tuple[str, Manifold]], path: Path) -> None:
    """Minimal 3MF, parts side by side on one plate."""
    objs, items, x = [], [], 0.0
    for i, (name, m) in enumerate(parts, 1):
        v, t = mesh(m)
        vs = "".join(f'<vertex x="{a:.4f}" y="{b:.4f}" z="{c:.4f}"/>' for a, b, c in v)
        ts = "".join(f'<triangle v1="{a}" v2="{b}" v3="{c}"/>' for a, b, c in t)
        objs.append(f'<object id="{i}" name="{name}" type="model"><mesh><vertices>{vs}</vertices>'
                    f'<triangles>{ts}</triangles></mesh></object>')
        w = v[:, 0].max() - v[:, 0].min()
        items.append(f'<item objectid="{i}" transform="1 0 0 0 1 0 0 0 1 {x + w / 2:.3f} 0 0"/>')
        x += w + 10

    # package files
    model = ('<?xml version="1.0" encoding="UTF-8"?><model unit="millimeter" xml:lang="en-US" '
             'xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"><resources>'
             + "".join(objs) + "</resources><build>" + "".join(items) + "</build></model>")
    types = ('<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
             '<Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", types)
        z.writestr("_rels/.rels", rels)
        z.writestr("3D/3dmodel.model", model)


def render(parts: list[tuple[Manifold, tuple[int, int, int]]], path: Path,
           yaw: float, pitch: float, size: int = 700) -> None:
    """Flat shaded preview, painter's algorithm."""
    # view rotation
    a, b = math.radians(yaw), math.radians(pitch)
    rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, math.cos(b), -math.sin(b)], [0, math.sin(b), math.cos(b)]])
    rot = rx @ rz
    light = rot @ (np.array([-0.4, -0.6, 0.7]) / np.linalg.norm([-0.4, -0.6, 0.7]))

    # collect projected triangles
    polys = []
    for m, col in parts:
        v, t = mesh(m)
        tri = (v @ rot.T)[t]
        n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-12
        vis = n[:, 1] < 0
        shade = 0.35 + 0.65 * np.clip(n @ light, 0, 1)
        for tr, s in zip(tri[vis], shade[vis]):
            polys.append((tr[:, 1].mean(), tr, tuple(int(c * s) for c in col)))

    # fit + draw far to near
    allp = np.concatenate([p[1] for p in polys])
    lo, hi = allp.min(0), allp.max(0)
    k = size * 0.9 / max(hi[0] - lo[0], hi[2] - lo[2])
    img = Image.new("RGB", (size, size), (245, 242, 235))
    dr = ImageDraw.Draw(img)
    for _, tr, col in sorted(polys, key=lambda q: -q[0]):
        pts = [(size / 2 + (x - (lo[0] + hi[0]) / 2) * k, size / 2 - (z - (lo[2] + hi[2]) / 2) * k) for x, _, z in tr]
        dr.polygon(pts, fill=col)
    img.save(path)


def main() -> None:
    """Build, export, render."""
    OUT.mkdir(exist_ok=True)
    IMG.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    write_stl(warmup(), BUILD / "warmup.stl")
    black, grey = (70, 70, 74), (120, 120, 126)

    for name in VARIANTS:
        use(name)
        sh, (cv, roof) = shell(), cover()

        # print parts: back face down for the leaning panel / cover, split roof upside down
        down = (TILT - 90, 0, 0)
        if SPLIT:
            parts = [("shell", to_print(sh, (0, 0, 0))), ("panel", to_print(cv, down)),
                     ("roof", to_print(roof, (180, 0, 0)))]
        else:
            parts = [("shell", to_print(sh, (0, 0, 0))), ("cover", to_print(cv, down))]
        parts.append(("fit_frame", to_print(fit_frame(), (90, 0, 0))))
        for part, m in parts:
            bb = m.bounding_box()
            print(f"{name} {part}: {m.volume() / 1000:.1f} cm3, "
                  f"{bb[3] - bb[0]:.0f} x {bb[4] - bb[1]:.0f} x {bb[5] - bb[2]:.0f} mm")
        write_3mf([(f"{name}_{p}", m) for p, m in parts[:-1]], OUT / f"{name}_case.3mf")
        write_stl(parts[-1][1], OUT / f"{name}_fit_frame.stl")

        # single parts for tools/bambu_project.py
        for part, m in parts[:-1]:
            write_stl(m, BUILD / f"{name}_{part}.stl")
        for old in ("cover", "panel", "roof"):
            if old not in dict(parts):
                (BUILD / f"{name}_{old}.stl").unlink(missing_ok=True)

        # previews for the docs; opened: panel lifted, roof slid back
        closed = [(sh, black), (cv, black), (roof, black)]
        render(closed, IMG / f"{name}_front.png", yaw=-30, pitch=12)
        render(closed, IMG / f"{name}_back.png", yaw=150, pitch=15)
        opened = [(sh, black), (cv.translate((0, 25 * TN, 25)), grey), (roof.translate((0, 45, 30)), grey)]
        render(opened, IMG / f"{name}_open.png", yaw=150, pitch=30)


if __name__ == "__main__":
    main()
