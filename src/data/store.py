"""Settings (plain json) + secrets (AES-CBC, device-bound key) on flash.

Secrets are never sent back to the web UI. Key = sha256(salt + chip id), so the files are
useless copied off the device, but anyone with USB + this code can still decrypt them.
ESP8266 has no secure storage; also the SDK keeps the WiFi password in its own flash sector.
"""
import binascii
import cryptolib
import hashlib
import json
import machine
import os

SETTINGS = "/settings.json"
SECRET = "/secret.bin"   # wifi pw, portal pw hash. wiped by factory reset
APKEY = "/ap.key"        # setup wifi pw. once per flash, survives factory reset + deploys
DEFAULTS = {
    "ssid": "",
    "mode": "slide",   # slide | port | single
    "single": 0,       # asset index for single mode
    "period": "1d",    # 1d | 5d | ytd | max, change shown next to the price
    "numfmt": "de",    # de: 1.234,56 € | en: €1,234.56
    "cur": "EUR",      # display currency, "native" = no conversion
    "slide_s": 8,
    "fetch_s": 300,
}  # the asset list lives in data.assets (/assets.jsonl)


# --- plain settings ---

def load() -> dict:
    """Settings merged over defaults."""
    s = dict(DEFAULTS)

    # missing / broken file -> defaults
    try:
        with open(SETTINGS) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    s.pop("items", None)  # pre-assets.jsonl layout
    return s


def _write(path: str, data, mode: str) -> None:
    """Write via tmp file so a power cut doesn't leave half a file."""
    with open(path + ".tmp", mode) as f:
        f.write(data)

    # FAT can't rename over an existing file
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(path + ".tmp", path)


def save(s: dict) -> None:
    """Persist settings."""
    _write(SETTINGS, json.dumps(s), "w")


# --- encrypted files ---

def _key() -> bytes:
    """Device-bound AES-256 key."""
    return hashlib.sha256(b"portfoliodisplay/v1" + machine.unique_id()).digest()


def _seal(path: str, d: dict) -> None:
    """json -> pkcs7 pad -> AES-CBC with fresh iv -> file."""
    data = json.dumps(d).encode()
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    iv = os.urandom(16)
    _write(path, iv + cryptolib.aes(_key(), 2, iv).encrypt(data), "wb")


def _open_sealed(path: str) -> dict:
    """Inverse of _seal, {} if missing or broken."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        data = cryptolib.aes(_key(), 2, raw[:16]).decrypt(raw[16:])
        return json.loads(data[:-data[-1]])
    except Exception:
        return {}


def load_secret() -> dict:
    """{pw, pp} decrypted."""
    return _open_sealed(SECRET)


def save_secret(d: dict) -> None:
    """Encrypt + persist secrets."""
    _seal(SECRET, d)


def ap_password() -> str:
    """Setup wifi password: random on first use, then the same forever (until erase_flash)."""
    pw = _open_sealed(APKEY).get("ap")
    if not pw:
        pw = random_pw()
        _seal(APKEY, {"ap": pw})
    return pw


def new_ap_password() -> None:
    """Forget it, next setup mode rolls a new one."""
    _rm(APKEY)


# --- reset + passwords ---

def _rm(path: str) -> None:
    """Delete if present."""
    try:
        os.remove(path)
    except OSError:
        pass


def factory_reset() -> None:
    """Drop settings, secrets, assets. Setup wifi password stays (static per flash)."""
    _rm(SETTINGS)
    _rm(SECRET)
    _rm("/assets.jsonl")


def pw_hash(pw: str, salt: bytes = b"") -> str:
    """'salt$hash' hex string. New random salt if none given."""
    salt = salt or binascii.hexlify(os.urandom(8))
    h = binascii.hexlify(hashlib.sha256(salt + pw.encode()).digest())
    return (salt + b"$" + h).decode()


def pw_check(pw: str, stored: str) -> bool:
    """Compare against pw_hash output."""
    salt = stored.split("$", 1)[0].encode()
    return pw_hash(pw, salt) == stored


def random_pw(n: int = 10) -> str:
    """Readable random password (no 0/O/1/l)."""
    abc = "abcdefghijkmnpqrstuvwxyz23456789"
    return "".join(abc[b % len(abc)] for b in os.urandom(n))
