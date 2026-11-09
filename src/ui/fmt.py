"""Number + currency formatting. STYLE is set from settings before each render.

de: 1.234,56 €  +0,73 %   (default)
en: €1,234.56   +0.73%
Units returned with a leading space mean "draw a gap before me".
"""

STYLE = "de"
SYMBOL = {"EUR": "€", "USD": "$"}  # only these exist in the big fonts


def num(v: float, dec: int = 2) -> str:
    """1.234,56 (de) / 1,234.56 (en)"""
    thou, point = (".", ",") if STYLE == "de" else (",", ".")
    s = ("%." + str(dec) + "f") % abs(v)
    ip, fp = (s.split(".") + [""])[:2]  # no str.partition on esp8266

    # thousands separators from the right
    g = ""
    while len(ip) > 3:
        g = thou + ip[-3:] + g
        ip = ip[:-3]
    return ("-" if v < 0 else "") + ip + g + (point + fp if fp else "")


def signed(v: float, dec: int = 2) -> str:
    """num with explicit +."""
    return ("+" if v >= 0 else "") + num(v, dec)


def pct_unit() -> str:
    """'%' unit for card(): spaced in de."""
    return " %" if STYLE == "de" else "%"


def pct(v: float) -> str:
    """+0,73 % / +0.73%"""
    return signed(v) + pct_unit()


def money(v: float, code: str, dec: int = 2, sign: bool = False) -> tuple:
    """(value text, unit). de: unit behind, en: €/$ in front, other codes behind."""
    n = signed(v, dec) if sign else num(v, dec)
    sym = SYMBOL.get(code)

    # de: always "1.234,56 €" / "12,50 CHF"
    if STYLE == "de" or not sym:
        return n, " " + (sym or code)

    # en: "€1,234.56", sign stays in front of the symbol
    if n[0] in "+-":
        return n[0] + sym + n[1:], ""
    return sym + n, ""


def money_str(v: float, code: str, dec: int = 2, sign: bool = False) -> str:
    """money() as one string for small text lines."""
    n, unit = money(v, code, dec, sign)
    return n + unit


def decimals(p: float) -> int:
    """Penny stocks / crypto fractions get 4 places."""
    return 2 if p >= 1 else 4
