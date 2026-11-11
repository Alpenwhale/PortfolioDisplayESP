"""Local time for the sleep window. Loaded only for the check, then dropped again.

The RTC runs in UTC (set by ntptime in the fetch phase). Time zone setting = base offset in
minutes + DST rule, e.g. "60eu" (Berlin), "-300us" (New York), "540" (Tokyo, no DST).
"""
import time

KNOWN = 1700000000 - 946684800  # anything before late 2023 (epoch 2000) = clock never set


def _sunday(y: int, m: int, nth: int) -> int:
    """Day of the nth Sunday in month m (nth = -1: last one, months with 31 days)."""
    if nth < 0:
        wd = time.localtime(time.mktime((y, m, 31, 0, 0, 0, 0, 0)))[6]  # Mon = 0
        return 31 - (wd + 1) % 7
    wd = time.localtime(time.mktime((y, m, 1, 0, 0, 0, 0, 0)))[6]
    return 1 + (6 - wd) % 7 + 7 * (nth - 1)


def _dst(utc: int, y: int, rule: str, base: int) -> bool:
    """Summer time active at utc seconds?"""

    # EU: last Sunday of March 01:00 UTC to last Sunday of October 01:00 UTC
    if rule == "eu":
        a = time.mktime((y, 3, _sunday(y, 3, -1), 1, 0, 0, 0, 0))
        b = time.mktime((y, 10, _sunday(y, 10, -1), 1, 0, 0, 0, 0))
        return a <= utc < b

    # US: second Sunday of March 02:00 local to first Sunday of November 02:00 local (summer time)
    if rule == "us":
        a = time.mktime((y, 3, _sunday(y, 3, 2), 2, 0, 0, 0, 0)) - base * 60
        b = time.mktime((y, 11, _sunday(y, 11, 1), 1, 0, 0, 0, 0)) - base * 60
        return a <= utc < b
    return False


def minutes(tz: str):
    """Local minutes since midnight, None while the clock was never set."""
    utc = time.time()
    if utc < KNOWN:
        return None

    # "60eu" -> 60 minutes base offset, EU rule
    rule = tz[-2:] if tz[-2:] in ("eu", "us") else ""
    base = int(tz[:len(tz) - len(rule)] or 0)
    off = base + (60 if _dst(utc, time.localtime(utc)[0], rule, base) else 0)
    t = time.localtime(utc + off * 60)
    return t[3] * 60 + t[4]


def asleep(s: dict) -> bool:
    """Inside the sleep window of settings s? Unknown time = awake."""
    if not s.get("sleep"):
        return False
    now = minutes(s.get("tz", "60eu"))
    if now is None:
        return False
    a, b = _hm(s.get("sleep_from", "")), _hm(s.get("sleep_to", ""))
    if a is None or b is None or a == b:
        return False
    return a <= now < b if a < b else now >= a or now < b


def _hm(v: str):
    """'22:30' -> 1350, None if broken."""
    try:
        h, m = v.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None
