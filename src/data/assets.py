"""Assets on flash: /assets.jsonl, one json object per line.

RAM only holds numbers (core.app: float arrays), full records are read per use.
That keeps RAM per asset at ~20 bytes instead of ~340 for a dict, so the list can be long.
Record: {id, ex, name, qty, buy, sym, yname}
"""
import json
import os

PATH = "/assets.jsonl"
MAX = 50  # flash and RAM would allow more; the portal form gets long beyond this


def lines():
    """Raw json lines, streamed."""
    try:
        f = open(PATH)
    except OSError:
        return
    with f:
        for ln in f:
            ln = ln.strip()
            if ln:
                yield ln


def each():
    """Records one by one."""
    for ln in lines():
        yield json.loads(ln)


def count() -> int:
    """Number of assets, streamed."""
    n = 0
    for _ in lines():
        n += 1
    return n


def read(i: int) -> dict:
    """Record i, {} if out of range."""
    for n, ln in enumerate(lines()):
        if n == i:
            return json.loads(ln)
    return {}


class Writer:
    """Write a fresh list to a tmp file, swap it in on commit (power-cut safe)."""

    def __init__(self) -> None:
        """Open tmp file."""
        self.n = 0
        self._f = open(PATH + ".tmp", "w")

    def add(self, rec: dict) -> bool:
        """Append one record, False once MAX is reached."""
        if self.n >= MAX:
            return False
        self._f.write(json.dumps(rec))
        self._f.write("\n")
        self.n += 1
        return True

    def commit(self) -> None:
        """Replace the real file."""
        self._f.close()
        try:
            os.remove(PATH)
        except OSError:
            pass
        os.rename(PATH + ".tmp", PATH)

    def abort(self) -> None:
        """Drop the tmp file, keep the old list."""
        self._f.close()
        try:
            os.remove(PATH + ".tmp")
        except OSError:
            pass


def update(i: int, **kv) -> None:
    """Change fields of record i (e.g. cache the resolved symbol). Streams the file once."""
    w = Writer()
    try:
        for n, rec in enumerate(each()):
            if n == i:
                rec.update(kv)
            w.add(rec)
    except Exception:
        w.abort()
        raise
    w.commit()
