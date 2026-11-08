"""mpremote wrapper that keeps DTR/RTS low on open.

This board's reset circuit holds the ESP in reset when both are high,
which is pyserial's default. Usage: uv run tools/mpr.py connect COM4 repl
"""
import sys
import time
import serial
from mpremote import main as mpremote_main

_open = serial.Serial.open
BOOT_WAIT_S = 1.5  # open still glitches EN once, let it boot


def _open_quiet(self: serial.Serial) -> None:
    """Drop DTR/RTS before open, then wait out the boot."""
    self.dtr = False  # setter only caches while closed
    self.rts = False
    _open(self)
    time.sleep(BOOT_WAIT_S)
    self.reset_input_buffer()


serial.Serial.open = _open_quiet

if __name__ == "__main__":
    sys.exit(mpremote_main.main())
