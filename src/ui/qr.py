"""Tiny QR encoder: byte mode, ECC level L, versions 1-4 (max 78 bytes), fixed mask 0.

Follows Nayuki's reference implementation, stripped to what a WiFi/URL code needs.
Only imported in setup/info screens, then unloaded.
"""

# data codewords / ecc codewords per version at level L (single block for v1-4)
_DATA = (0, 19, 34, 55, 80)
_ECC = (0, 7, 10, 15, 20)


def _mul(x: int, y: int) -> int:
    """GF(256) multiply, poly 0x11d."""
    z = 0
    for i in range(7, -1, -1):
        z = ((z << 1) ^ ((z >> 7) * 0x11D)) & 0xFF
        z ^= ((y >> i) & 1) * x
    return z


def _ecc(data: bytearray, n: int) -> bytearray:
    """Reed-Solomon remainder, n ecc bytes."""

    # generator polynomial
    div = bytearray(n)
    div[n - 1] = 1
    root = 1
    for _ in range(n):
        for j in range(n):
            div[j] = _mul(div[j], root)
            if j + 1 < n:
                div[j] ^= div[j + 1]
        root = _mul(root, 2)

    # polynomial division
    res = bytearray(n)
    for b in data:
        f = b ^ res[0]
        res = res[1:] + b"\x00"
        for i in range(n):
            res[i] ^= _mul(div[i], f)
    return res


def _codewords(text: bytes) -> tuple:
    """(version, data+ecc bytes)."""

    # smallest version that fits mode(4) + len(8) + payload bits
    ver = 1
    while ver < 4 and 12 + 8 * len(text) > _DATA[ver] * 8:
        ver += 1
    cap = _DATA[ver]
    if 12 + 8 * len(text) > cap * 8:
        raise ValueError("qr text too long")

    # bit stream: 0100 | len | bytes | terminator, then byte align
    bits = [0, 1, 0, 0] + [(len(text) >> i) & 1 for i in range(7, -1, -1)]
    for b in text:
        bits += [(b >> i) & 1 for i in range(7, -1, -1)]
    bits += [0] * min(4, cap * 8 - len(bits))
    bits += [0] * (-len(bits) % 8)

    # pack + pad with 0xEC 0x11
    data = bytearray(len(bits) // 8)
    for i, bit in enumerate(bits):
        data[i >> 3] |= bit << (7 - (i & 7))
    pad = 0xEC
    while len(data) < cap:
        data.append(pad)
        pad ^= 0xEC ^ 0x11
    return ver, data + _ecc(data, _ECC[ver])


def encode(text: str) -> tuple:
    """(modules bytearray row-major, size). 1 = dark."""
    ver, words = _codewords(text.encode())
    n = 17 + 4 * ver
    m = bytearray(n * n)
    fn = bytearray(n * n)  # function pattern mask

    def put(x: int, y: int, dark) -> None:
        m[y * n + x] = 1 if dark else 0
        fn[y * n + x] = 1

    # timing lines
    for i in range(n):
        put(6, i, i % 2 == 0)
        put(i, 6, i % 2 == 0)

    # finders + separators
    for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
        for dy in range(-4, 5):
            for dx in range(-4, 5):
                x, y = cx + dx, cy + dy
                if 0 <= x < n and 0 <= y < n:
                    put(x, y, max(abs(dx), abs(dy)) not in (2, 4))

    # single alignment pattern for v2-4
    if ver > 1:
        c = n - 7
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                put(c + dx, c + dy, max(abs(dx), abs(dy)) != 1)

    # format bits: level L (01), mask 0, BCH(15,5)
    data = 1 << 3
    rem = data
    for _ in range(10):
        rem = (rem << 1) ^ ((rem >> 9) * 0x537)
    fmt = ((data << 10) | rem) ^ 0x5412
    bit = lambda i: (fmt >> i) & 1
    for i in range(6):
        put(8, i, bit(i))
    put(8, 7, bit(6))
    put(8, 8, bit(7))
    put(7, 8, bit(8))
    for i in range(9, 15):
        put(14 - i, 8, bit(i))
    for i in range(8):
        put(n - 1 - i, 8, bit(i))
    for i in range(8, 15):
        put(8, n - 15 + i, bit(i))
    put(8, n - 8, 1)

    # zigzag codeword placement, mask 0 = (x + y) even flips
    i, total = 0, len(words) * 8
    right = n - 1
    while right >= 1:
        if right == 6:
            right = 5
        for vert in range(n):
            for j in range(2):
                x = right - j
                y = n - 1 - vert if ((right + 1) & 2) == 0 else vert
                if not fn[y * n + x]:
                    dark = i < total and (words[i >> 3] >> (7 - (i & 7))) & 1
                    i += 1
                    m[y * n + x] = (1 if dark else 0) ^ ((x + y) % 2 == 0)
        right -= 2
    return m, n
