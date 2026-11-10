"""Screenshots of the web portal for docs/SETUP.md -> docs/img/portal/*.png.

Usage: uv run tools/portal_shots.py
Serves the real src/www files on localhost with example /cfg.json data and takes
phone-width shots with headless Edge/Chrome. No board needed.
Whole pages (1_..4_) plus one shot per form section (wifi, display, assets, security).
"""
import json
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WWW = ROOT / "src" / "www"
OUT = ROOT / "docs" / "img" / "portal"
PORT = 8765
WIDTH = 500  # headless chromium won't go narrower, smaller crops the page
BROWSERS = (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe", "chromium", "google-chrome")

BASE = {"ssid": "", "show_total": 1, "show_assets": 1, "single": 0, "period": "1d", "numfmt": "de",
        "cur": "EUR", "slide_s": 8, "total_s": 8, "fetch_s": 300, "bright": 100}
ASSETS = [
    {"id": "IE00B4L5Y983", "ex": ".DE", "name": "MSCI World", "qty": 10, "buy": 80.5,
     "sym": "EUNL.DE", "yname": "iShares Core MSCI World"},
    {"id": "AAPL", "ex": "US", "name": "", "qty": 3, "buy": 172.3, "sym": "AAPL", "yname": "Apple Inc."},
    {"id": "A1JX52", "ex": "auto", "name": "", "qty": None, "buy": None},
]
NETS = ["FRITZ!Box 7590 XY", "Home", "Neighbour-5G"]

CONFIGURED = {"s": dict(BASE, ssid="Home", period="ytd", total_s=15), "items": ASSETS,
              "pw": True, "pp": True, "max": 50, "reset_s": 10, "nets": NETS}

# name -> (path, cfg.json). "?only=<section>" shows just that part of the form (for the field tables)
VIEWS = {
    "wifi": ("/?only=wifi", CONFIGURED),
    "display": ("/?only=display", CONFIGURED),
    "assets": ("/?only=assets", CONFIGURED),
    "security": ("/?only=security", CONFIGURED),
    "1_first_setup": ("/", {"s": BASE, "items": [], "pw": False, "pp": False, "max": 50, "reset_s": 10,
                            "nets": NETS}),
    "2_configured": ("/", CONFIGURED),
    "3_saved": ("/saved", None),
    "4_back_after_save": ("/?ok", {"s": dict(BASE, ssid="Home"), "items": ASSETS[:2], "pw": True,
                                   "pp": False, "max": 50, "reset_s": 10, "nets": NETS}),
}
STATE = {"cfg": None}


class Handler(BaseHTTPRequestHandler):
    """Same routes as net/portal.py."""

    def log_message(self, *a) -> None:
        """Quiet."""

    def do_GET(self) -> None:
        """Static files + example cfg.json."""
        path, _, query = self.path.partition("?")
        if path == "/cfg.json":
            body, ctype = json.dumps(STATE["cfg"]).encode(), "application/json"
        else:
            name = {"/": "index.html", "/s.css": "s.css", "/saved": "saved.html"}.get(path, "index.html")
            body = (WWW / name).read_bytes()
            ctype = "text/css" if name.endswith(".css") else "text/html; charset=utf-8"

            # section-only shot: hide everything else (screenshot helper, not part of the device)
            if query.startswith("only="):
                css = "<style>h1,#note,form>button,section:not(#%s){display:none}</style>" % query[5:]
                body = body.replace(b"</title>", b"</title>" + css.encode())
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.end_headers()
        self.wfile.write(body)


def browser() -> str:
    """First Chromium-ish browser found."""
    for b in BROWSERS:
        if Path(b).exists() or shutil.which(b):
            return b
    raise SystemExit("no Edge/Chrome found")


def trim(raw: Path, p: Path) -> None:
    """Cut the empty black area below the content."""

    # the browser returns before its file is complete: wait until the size stops changing
    size = -1
    for _ in range(60):
        time.sleep(0.5)
        now = raw.stat().st_size if raw.exists() else -1
        if now > 0 and now == size:
            break
        size = now
    img = Image.open(raw).convert("RGB")
    w, h = img.size
    px = img.load()
    bottom = h
    while bottom > 1 and all(px[x, bottom - 1] == (0, 0, 0) for x in range(0, w, 4)):
        bottom -= 1
    img.crop((0, 0, w, min(h, bottom + 24))).save(p)


def main() -> None:
    """One screenshot per view."""
    OUT.mkdir(parents=True, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    exe = browser()

    # raw shots go to a temp dir: the browser sometimes rewrites its file after it exited
    tmp = Path(tempfile.mkdtemp())
    try:
        for name, (path, cfg) in VIEWS.items():
            STATE["cfg"] = cfg
            out = OUT / (name + ".png")
            subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                            "--force-device-scale-factor=1", "--virtual-time-budget=1500",
                            "--window-size=%d,4000" % WIDTH, "--screenshot=%s" % (tmp / out.name),
                            "http://127.0.0.1:%d%s" % (PORT, path)],
                           check=True, capture_output=True, timeout=60)
            trim(tmp / out.name, out)
            print(name, Image.open(out).size)
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
