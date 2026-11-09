"""Compile src/ to .mpy, upload, reset. Usage: uv run tools/deploy.py [PORT]

.mpy = precompiled bytecode, the board skips the compiler -> far less RAM at import.
main.py stays .py (entry point). settings.json / secret.bin on the board are left alone.
"""
import shutil
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "src"
BUILD = TOOLS.parent / "build"
KEEP_PY = {"main.py"}


def build() -> list[str]:
    """Fill build/ and return the board path of every file in it."""
    shutil.rmtree(BUILD, ignore_errors=True)
    files = []
    for f in SRC.rglob("*"):
        if f.is_dir() or "__pycache__" in f.parts:
            continue
        rel = f.relative_to(SRC)
        out = BUILD / rel
        out.parent.mkdir(parents=True, exist_ok=True)

        # .py -> .mpy, everything else (fonts, css, main.py) as is
        if f.suffix == ".py" and rel.name not in KEEP_PY:
            out = out.with_suffix(".mpy")
            subprocess.check_call([sys.executable, "-m", "mpy_cross", "-o", str(out), str(f)])
        else:
            shutil.copy2(f, out)
        files.append("/" + out.relative_to(BUILD).as_posix())
    return files


def cleanup_cmd(files: list[str]) -> str:
    """Board-side snippet: delete code files that aren't part of this build.

    Catches moved modules and stale .py twins (a .py would shadow the new .mpy).
    Data files (settings.json, secret.bin) and boot.py are never touched.
    """
    keep = set(files) | {"/boot.py"}
    return ("import os\n"
            "keep = %r\n"
            "def walk(d):\n"
            " for e in os.ilistdir(d):\n"
            "  p = (d if d != '/' else '') + '/' + e[0]\n"
            "  if e[1] == 0x4000: walk(p)\n"
            "  elif p.endswith(('.py', '.mpy')) and p not in keep:\n"
            "   os.remove(p); print('removed', p)\n"
            "walk('/')" % sorted(keep))


def main() -> int:
    """Build, clean stale files, copy, reset."""
    port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
    files = build()
    args = [sys.executable, str(TOOLS / "mpr.py"), "connect", port, "exec", cleanup_cmd(files), "+"]
    for item in sorted(BUILD.iterdir()):
        args += ["cp", "-r", str(item), ":", "+"] if item.is_dir() else ["cp", str(item), ":", "+"]
    args += ["reset"]
    print("uploading to", port)
    return subprocess.call(args)


if __name__ == "__main__":
    sys.exit(main())
