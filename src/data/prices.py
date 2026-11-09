"""Fetched prices on flash: /prices.bin, one fixed 32 byte record per asset index.

Fixed size = a record can be read/written in place (seek) without loading the file, which
matters because it's written during the TLS fetch phase where every KB counts.
Record: price f32 | base f32 | ok u8 (has a price) | currency 3s | last error 20s
"""
import struct

PATH = "/prices.bin"
FMT = "<ffB3s20s"
SIZE = 32
EMPTY = (0.0, 0.0, 0, "", "")


def _unpack(raw: bytes) -> tuple:
    """Record bytes -> (price, base, ok, currency, error)."""
    p, b, ok, cur, err = struct.unpack(FMT, raw)
    return p, b, ok, cur.rstrip(b"\0").decode(), err.rstrip(b"\0").decode()


def read(i: int) -> tuple:
    """Record i, EMPTY if not there yet."""
    try:
        with open(PATH, "rb") as f:
            f.seek(i * SIZE)
            raw = f.read(SIZE)
    except OSError:
        return EMPTY
    return _unpack(raw) if len(raw) == SIZE else EMPTY


def write(i: int, p: float, b: float, ok: int, cur: str, err: str) -> None:
    """Store record i in place."""
    rec = struct.pack(FMT, p, b, ok, cur.encode()[:3], err.encode()[:20])
    try:
        f = open(PATH, "r+b")
    except OSError:
        f = open(PATH, "w+b")
    with f:

        # grow the file with empty records up to i
        f.seek(0, 2)
        end = f.tell() // SIZE
        while end < i:
            f.write(bytes(SIZE))
            end += 1
        f.seek(i * SIZE)
        f.write(rec)


def each():
    """(index, price, base, ok, currency, error) for every stored record."""
    try:
        f = open(PATH, "rb")
    except OSError:
        return
    with f:
        i = 0
        while True:
            raw = f.read(SIZE)
            if len(raw) < SIZE:
                return
            yield (i,) + _unpack(raw)
            i += 1


def clear() -> None:
    """Asset list changed: indexes no longer match."""
    import os
    try:
        os.remove(PATH)
    except OSError:
        pass
