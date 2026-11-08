"""Upload src/ to the board and reset. Usage: uv run tools/deploy.py [PORT]"""
import subprocess
import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parent
SRC = TOOLS.parent / "src"


def build_args(port: str) -> list[str]:
    """Chain all cp calls into one mpremote session."""
    args = [sys.executable, str(TOOLS / "mpr.py"), "connect", port]
    for item in sorted(SRC.iterdir()):
        if item.name == "__pycache__":
            continue
        args += ["cp", "-r", str(item), ":", "+"] if item.is_dir() else ["cp", str(item), ":", "+"]
    return args + ["reset"]


def main() -> int:
    """Run the upload."""
    port = sys.argv[1] if len(sys.argv) > 1 else "COM4"
    print("uploading to", port)
    return subprocess.call(build_args(port))


if __name__ == "__main__":
    sys.exit(main())
