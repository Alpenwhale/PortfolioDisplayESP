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
    """Fill build/ and return board paths of every module (without extension)."""
    shutil.rmtree(BUILD, ignore_errors=True)
    modules = []
    for f in SRC.rglob("*"):
        if f.is_dir() or "__pycache__" in f.parts:
            continue
        rel = f.relative_to(SRC)
        out = BUILD / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if f.suffix == ".py" and rel.name not in KEEP_PY:
            out = out.with_suffix(".mpy")
            subprocess.check_call([sys.executable, "-m", "mpy_cross", "-o", str(out), str(f)])
            modules.append("/" + rel.with_suffix("").as_posix())
        else:
            shutil.copy2(f, out)
    return modules


def cleanup_cmd(modules: list[str]) -> str:
    """Board-side snippet: drop stale .py twins that would shadow the new .mpy."""
    return ("import os\nfor m in %r:\n try: os.remove(m + '.py')\n except OSError: pass" % modules)


def main() -> int:
    """Build, clean stale files, copy, reset."""
    port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
    modules = build()
    args = [sys.executable, str(TOOLS / "mpr.py"), "connect", port, "exec", cleanup_cmd(modules), "+"]
    for item in sorted(BUILD.iterdir()):
        args += ["cp", "-r", str(item), ":", "+"] if item.is_dir() else ["cp", str(item), ":", "+"]
    args += ["reset"]
    print("uploading to", port)
    return subprocess.call(args)


if __name__ == "__main__":
    sys.exit(main())
