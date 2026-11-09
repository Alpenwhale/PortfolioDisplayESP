"""Settings (plain json) + secrets (AES-CBC, device-bound key) on flash.

Secrets are never sent back to the web UI. Key = sha256(salt + chip id), so the file is
useless copied off the device, but anyone with USB + this code can still decrypt it.
ESP8266 has no secure storage; also the SDK keeps the WiFi password in its own flash sector.
"""
import binascii
import cryptolib
import hashlib
import json
import machine
import os

SETTINGS = "/settings.json"
SECRET = "/secret.bin"
MAX_ITEMS = 8
DEFAULTS = {
    "ssid": "",
    "mode": "slide",   # slide | port | single
    "single": 0,       # item index for single mode
    "slide_s": 8,
    "fetch_s": 300,
    "items": [],       # {id, name, sym, qty, buy}
}


def load() -> dict:
    """Settings merged over defaults."""
    s = dict(DEFAULTS)
    try:
        with open(SETTINGS) as f:
            s.update(json.load(f))
    except (OSError, ValueError):
        pass
    return s


def _write(path: str, data, mode: str) -> None:
    """Write via tmp file so a power cut doesn't leave half a file."""
    with open(path + ".tmp", mode) as f:
        f.write(data)
    try:
        os.remove(path)
    except OSError:
        pass
    os.rename(path + ".tmp", path)


def save(s: dict) -> None:
    """Persist settings."""
    _write(SETTINGS, json.dumps(s), "w")


def _key() -> bytes:
    """Device-bound AES-256 key."""
    return hashlib.sha256(b"portfoliodisplay/v1" + machine.unique_id()).digest()


def load_secret() -> dict:
    """Decrypted secrets, {} if missing or broken."""
    try:
        with open(SECRET, "rb") as f:
            raw = f.read()
        data = cryptolib.aes(_key(), 2, raw[:16]).decrypt(raw[16:])
        return json.loads(data[:-data[-1]])
    except Exception:
        return {}


def save_secret(d: dict) -> None:
    """Encrypt + persist secrets (pkcs7 pad, random iv)."""
    data = json.dumps(d).encode()
    pad = 16 - len(data) % 16
    data += bytes([pad]) * pad
    iv = os.urandom(16)
    _write(SECRET, iv + cryptolib.aes(_key(), 2, iv).encrypt(data), "wb")


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
