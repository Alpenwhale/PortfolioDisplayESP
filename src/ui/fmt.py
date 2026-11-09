"""Number + currency formatting, German style."""

CUR = {"EUR": "€", "USD": "$"}


def num(v: float, dec: int = 2) -> str:
    """1.234,56"""
    s = ("%." + str(dec) + "f") % abs(v)
    ip, fp = (s.split(".") + [""])[:2]  # no str.partition on esp8266

    # thousands dots from the right
    g = ""
    while len(ip) > 3:
        g = "." + ip[-3:] + g
        ip = ip[:-3]
    return ("-" if v < 0 else "") + ip + g + ("," + fp if fp else "")


def signed(v: float, dec: int = 2) -> str:
    """num with explicit +."""
    return ("+" if v >= 0 else "") + num(v, dec)


def pct(v: float) -> str:
    """+1,23 %"""
    return signed(v) + " %"


def cur(code: str) -> str:
    """Currency symbol or the code itself."""
    return CUR.get(code, code)


def decimals(p: float) -> int:
    """Penny stocks / crypto fractions get 4 places."""
    return 2 if p >= 1 else 4
