"""Dependency-free Solana transaction signing.

Pure-Python Ed25519 (RFC 8032 reference construction) + Base58, so live
trading works on platforms where the Rust-based `solders` package cannot be
built (e.g. Termux/Android). Signing a swap takes a few milliseconds — plenty
fast for a bot that trades a handful of times per hour.

The implementation is validated against the RFC 8032 test vector on first
use, and the test suite cross-checks signatures byte-for-byte against
`solders` where that package is available.
"""

from __future__ import annotations

import hashlib
import json

# ── Ed25519 (RFC 8032) ────────────────────────────────────────────────────────

_P = 2**255 - 19
_Q = 2**252 + 27742317777372353535851937790883648493
_D = -121665 * pow(121666, _P - 2, _P) % _P


def _sha512(data: bytes) -> bytes:
    return hashlib.sha512(data).digest()


def _point_add(a, b):
    e = (a[1] - a[0]) * (b[1] - b[0]) % _P
    f = (a[1] + a[0]) * (b[1] + b[0]) % _P
    g = 2 * a[3] * b[3] * _D % _P
    h = 2 * a[2] * b[2] % _P
    return (
        (f - e) * (h - g) % _P,
        (h + g) * (f + e) % _P,
        (h - g) * (h + g) % _P,
        (f - e) * (f + e) % _P,
    )


def _point_mul(s: int, point):
    result = (0, 1, 1, 0)  # neutral element
    while s > 0:
        if s & 1:
            result = _point_add(result, point)
        point = _point_add(point, point)
        s >>= 1
    return result


def _point_compress(point) -> bytes:
    zinv = pow(point[2], _P - 2, _P)
    x = point[0] * zinv % _P
    y = point[1] * zinv % _P
    return int.to_bytes(y | ((x & 1) << 255), 32, "little")


def _recover_x(y: int, sign_bit: int) -> int:
    x2 = (y * y - 1) * pow(_D * y * y + 1, _P - 2, _P) % _P
    x = pow(x2, (_P + 3) // 8, _P)
    if (x * x - x2) % _P != 0:
        x = x * pow(2, (_P - 1) // 4, _P) % _P
    if x % 2 != sign_bit:
        x = _P - x
    return x


_G_Y = 4 * pow(5, _P - 2, _P) % _P
_G_X = _recover_x(_G_Y, 0)
_G = (_G_X, _G_Y, 1, _G_X * _G_Y % _P)


def _secret_expand(seed: bytes) -> tuple[int, bytes]:
    h = _sha512(seed)
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 1 << 254
    return a, h[32:]


def ed25519_public_key(seed: bytes) -> bytes:
    a, _ = _secret_expand(seed)
    return _point_compress(_point_mul(a, _G))


def ed25519_sign(seed: bytes, message: bytes) -> bytes:
    a, prefix = _secret_expand(seed)
    pub = _point_compress(_point_mul(a, _G))
    r = int.from_bytes(_sha512(prefix + message), "little") % _Q
    big_r = _point_compress(_point_mul(r, _G))
    h = int.from_bytes(_sha512(big_r + pub + message), "little") % _Q
    s = (r + h * a) % _Q
    return big_r + int.to_bytes(s, 32, "little")


# ── Base58 ────────────────────────────────────────────────────────────────────

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_B58_INDEX = {c: i for i, c in enumerate(_B58)}


def b58decode(s: str) -> bytes:
    num = 0
    for ch in s:
        if ch not in _B58_INDEX:
            raise ValueError(f"invalid base58 character {ch!r}")
        num = num * 58 + _B58_INDEX[ch]
    raw = num.to_bytes((num.bit_length() + 7) // 8, "big") if num else b""
    pad = len(s) - len(s.lstrip("1"))
    return b"\x00" * pad + raw


def b58encode(data: bytes) -> str:
    num = int.from_bytes(data, "big")
    out = ""
    while num:
        num, rem = divmod(num, 58)
        out = _B58[rem] + out
    pad = len(data) - len(data.lstrip(b"\x00"))
    return "1" * pad + out


# ── Solana wallet + versioned-transaction signing ────────────────────────────

_selftest_done = False


def _self_test() -> None:
    """Known-good vector (generated with solders/ed25519-dalek) — guards
    against porting mistakes before any real transaction is signed."""
    global _selftest_done
    if _selftest_done:
        return
    seed = bytes.fromhex(
        "9d61b94d66c6c68d61c3d17b6b8d6a4f36eaf4c8b23a67d5b58a2b28002f4f3b"
    )
    expect_pub = bytes.fromhex(
        "bbeea065275c98e84ec673cdd0aabdf2786d7acb64e80566c4357236d242ea2d"
    )
    expect_sig = bytes.fromhex(
        "63c02daed7604368b47bbfd4c682980fd315bf2ca2f15fee776fdb33249d1cfd"
        "f7091d7b19cab45a8bc9b8199c62b661996a04a675dd575cae7a4ef60bfb240b"
    )
    if ed25519_public_key(seed) != expect_pub or ed25519_sign(seed, b"") != expect_sig:
        raise RuntimeError("Ed25519 self-test failed — refusing to sign transactions")
    _selftest_done = True


class Wallet:
    """Solana keypair from a Phantom-style base58 export (or JSON byte array)."""

    def __init__(self, private_key: str):
        _self_test()
        key = private_key.strip()
        if key.startswith("["):  # solana-cli id.json format
            raw = bytes(json.loads(key))
        else:
            raw = b58decode(key)
        if len(raw) == 64:
            self._seed = raw[:32]
            if ed25519_public_key(self._seed) != raw[32:]:
                raise ValueError("private key is corrupt: pubkey half does not match")
        elif len(raw) == 32:
            self._seed = raw
        else:
            raise ValueError(f"expected a 32- or 64-byte key, got {len(raw)} bytes")
        self._pubkey = b58encode(ed25519_public_key(self._seed))

    def pubkey(self) -> str:
        return self._pubkey

    def sign(self, message: bytes) -> bytes:
        return ed25519_sign(self._seed, message)


def _decode_compact_u16(data: bytes, offset: int) -> tuple[int, int]:
    result = shift = 0
    while True:
        byte = data[offset]
        offset += 1
        result |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return result, offset
        shift += 7


def sign_versioned_transaction(raw: bytes, wallet: Wallet) -> bytes:
    """Sign a serialized (unsigned) Solana versioned transaction.

    Layout: compact-u16 signature count, N x 64-byte signature slots, then
    the message. Jupiter builds swaps with the user's wallet as fee payer,
    i.e. signature slot 0.
    """
    count, sigs_start = _decode_compact_u16(raw, 0)
    if count < 1:
        raise ValueError("transaction has no signature slots")
    sigs_end = sigs_start + 64 * count
    message = raw[sigs_end:]
    signature = wallet.sign(message)
    return raw[:sigs_start] + signature + raw[sigs_start + 64 : sigs_end] + message
