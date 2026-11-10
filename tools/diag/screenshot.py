"""Screenshot of the REAL panel: reads the TFT's own image memory back over MISO. Runs on the PC.

What:     resets the board, lets the app run for --wait seconds (its log is printed), stops it
          with Ctrl-C, reads every pixel out of the panel (RAMRD) and saves a PNG.
          So you see what the display actually shows, not what the code thinks it drew.
Needs:    TFT with MISO wired (D6). Not for the OLED.
Run:      uv run tools/diag/screenshot.py COM4 --wait 45 --out shot.png
          uv run tools/diag/screenshot.py COM4 --until "fetch phase" --wait 0 --out during_fetch.png
          (--until TEXT [--count N]: shoot when the device log shows TEXT for the N-th time)
Expected: the device log, then "saved shot.png (320x240)". Takes ~30 s on top of the waiting.
Tells you: whether a screen really reached the panel (e.g. after the refresh soft reset).
Note:     this module has no CS pin, so after a memory read the panel ignores commands until
          a hardware reset. The script therefore resets the board at the end; the app restarts.
"""
import argparse
import sys
import time

import serial
from PIL import Image

# board side, sent in paste mode. 2 bits per color channel -> one printable char per pixel
SNIPPET = r'''
import config, gc
from machine import Pin, SPI
gc.collect()
_dc = Pin(config.TFT_DC, Pin.OUT, value=1)
_spi = SPI(1, baudrate=1000000, polarity=config.TFT_SPI_MODE >> 1, phase=config.TFT_SPI_MODE & 1)
_w, _h = (config.TFT_HEIGHT, config.TFT_WIDTH) if config.TFT_ROTATION % 2 else (config.TFT_WIDTH, config.TFT_HEIGHT)
def _c(b, d=b""):
    _dc(0); _spi.write(b); _dc(1)
    if d: _spi.write(d)
_c(b"\x2a", bytes([0, 0, (_w - 1) >> 8, (_w - 1) & 255]))
_c(b"\x2b", bytes([0, 0, (_h - 1) >> 8, (_h - 1) & 255]))
_c(b"\x2e")
_spi.read(1)
_b = bytearray(3 * _w); _o = bytearray(_w)
print("SHOT", _w, _h)
for _y in range(_h):
    _spi.readinto(_b)
    for _x in range(_w):
        _i = 3 * _x
        _o[_x] = 48 + (_b[_i] >> 6) + ((_b[_i + 1] >> 6) << 2) + ((_b[_i + 2] >> 6) << 4)
    print(_o.decode())
print("SHOTEND")
'''


def open_port(port: str) -> serial.Serial:
    """Open with DTR/RTS low (this board sits in reset when both are high)."""
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, 115200, 0.2
    s.dtr = False
    s.rts = False
    s.open()
    return s


def reset(s: serial.Serial) -> None:
    """Pulse EN via RTS."""
    s.rts = True
    time.sleep(0.1)
    s.rts = False


def pump(s: serial.Serial, seconds: float, echo: bool = True, until: str = "", count: int = 1) -> str:
    """Read for a while (or until `until` showed up `count` times), optionally echo printable lines."""
    end, buf = time.time() + seconds, b""
    while time.time() < end:
        buf += s.read(4096)
        if until and buf.count(until.encode()) >= count:
            break
    text = buf.decode("utf-8", "replace")
    if echo:
        for ln in text.splitlines():
            if ln.strip() and ln.isprintable() and not ln.startswith(("load ", "tail ", "chksum", "ho ", "csum")):
                print("  |", ln)
    if until and text.count(until) < count:
        raise SystemExit("'%s' did not show up %d time(s) within %d s" % (until, count, seconds))
    return text


def grab(s: serial.Serial) -> Image.Image:
    """Ctrl-C into the REPL, paste the dump snippet, parse the pixel lines."""
    s.write(b"\x03\x03")
    pump(s, 1.0, echo=False)
    s.reset_input_buffer()

    # paste mode: Ctrl-E, code, Ctrl-D
    s.write(b"\x05")
    time.sleep(0.2)
    for line in SNIPPET.strip().splitlines():
        s.write(line.encode() + b"\r")
        time.sleep(0.02)
    s.write(b"\x04")

    # collect until the end marker
    buf, end = b"", time.time() + 120
    while b"SHOTEND" not in buf.split(b"print(\"SHOTEND\")")[-1] and time.time() < end:
        buf += s.read(8192)
    text = buf.decode("ascii", "replace")
    head = text.rfind("SHOT ", 0, text.rfind("SHOTEND"))
    if head < 0:
        raise SystemExit("no screenshot data, board said:\n" + text[-600:])
    lines = text[head:].splitlines()
    w, h = (int(v) for v in lines[0].split()[1:3])
    rows = [ln for ln in lines[1:] if len(ln) == w][:h]
    if len(rows) < h:
        raise SystemExit("only %d of %d rows received" % (len(rows), h))

    # 2 bits per channel back to 0..255
    img = Image.new("RGB", (w, h))
    px = img.load()
    for y, ln in enumerate(rows):
        for x, ch in enumerate(ln):
            v = ord(ch) - 48
            px[x, y] = ((v & 3) * 85, ((v >> 2) & 3) * 85, ((v >> 4) & 3) * 85)
    return img


def main() -> None:
    """Reset, wait, grab, save, reset again."""
    ap = argparse.ArgumentParser()
    ap.add_argument("port")
    ap.add_argument("--wait", type=float, default=45, help="seconds to let the app run before the shot "
                                                             "(with --until: extra seconds after the match)")
    ap.add_argument("--until", default="", help="shoot when this text appears in the device log, e.g. 'fetch phase'")
    ap.add_argument("--count", type=int, default=1, help="... for the n-th time")
    ap.add_argument("--timeout", type=float, default=600, help="give up waiting for --until after this long")
    ap.add_argument("--out", default="shot.png")
    args = ap.parse_args()

    s = open_port(args.port)
    try:
        reset(s)
        if args.until:
            pump(s, args.timeout, until=args.until, count=args.count)
            args.wait and pump(s, args.wait)
        else:
            pump(s, args.wait)
        img = grab(s)
        img.save(args.out)
        print("saved %s (%dx%d)" % (args.out, img.width, img.height))
    finally:
        reset(s)  # panel is locked after RAMRD, a chip reset re-inits it
        s.close()


if __name__ == "__main__":
    sys.exit(main())
