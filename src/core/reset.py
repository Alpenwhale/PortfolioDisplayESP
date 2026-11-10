"""A real soft reset from running code.

machine.soft_reset() can't do it on the ESP8266: called from main.py it just ends main.py
and leaves the board sitting at the REPL (measured, that was the "stuck at Loading prices" bug).
What does trigger a soft reboot is Ctrl-D typed at the REPL. So: end main.py, then feed
the REPL one Ctrl-D through a dupterm stream. Chip, wifi and display keep running.
"""
import io
import machine
import os
import sys

_keep = None  # timer + stream must not be garbage collected before they fire


class _CtrlD(io.IOBase):
    """Input stream that delivers a single Ctrl-D."""

    def __init__(self) -> None:
        """Nothing sent yet."""
        self.sent = False

    def readinto(self, b) -> int:
        """One byte, then 'no data' (None), never EOF (0 would detach the stream)."""
        if self.sent:
            return None
        self.sent = True
        b[0] = 4
        return 1

    def write(self, b) -> int:
        """Swallow the REPL's output."""
        return len(b)

    def ioctl(self, op, arg) -> int:
        """Stream protocol stub."""
        return 0


def soft_reset() -> None:
    """Never returns: main.py ends via SystemExit, 200 ms later the REPL gets its Ctrl-D."""
    global _keep
    s = _CtrlD()
    os.dupterm(s, 0)

    # one-shot only: an armed timer would outlive the soft reset with a dangling callback
    t = machine.Timer(-1)
    t.init(period=200, mode=machine.Timer.ONE_SHOT, callback=lambda _: os.dupterm_notify(None))
    _keep = (s, t)
    sys.exit()
