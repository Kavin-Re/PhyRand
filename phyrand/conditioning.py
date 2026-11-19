"""Conditioning and mixing of hardware entropy.

Design goals
------------
1. Hardware bytes are never used directly as key material.  They pass through
   HKDF-SHA256 (RFC 5869), which removes residual bias/correlation as long as
   the input carries enough min-entropy.
2. The hardware input is *always* combined with fresh bytes from the operating
   system CSPRNG.  HKDF-Extract over the concatenation acts as a robust
   combiner: the output key is at least as hard to predict as the stronger of
   the two inputs, so a degraded, failed or even adversarial noise source
   cannot make keys weaker than plain ``os.urandom`` keys.
3. Inputs are length-prefixed and the derivation is domain-separated so that
   the two inputs can never be confused with each other or with another use.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Callable

HASH = hashlib.sha256
HASH_LEN = HASH().digest_size

#: Fixed, public domain-separation salt for HKDF-Extract.
MIX_SALT = HASH(b"PhyRand/v1/entropy-mix/salt").digest()
#: Default ``info`` label for Fernet key derivation.
INFO_FERNET_KEY = b"PhyRand/v1/fernet-key"
#: Bytes drawn from the OS CSPRNG for every derived key.
OS_ENTROPY_BYTES = 32


def hkdf_extract(salt: bytes, ikm: bytes) -> bytes:
    """RFC 5869 HKDF-Extract with SHA-256."""
    return hmac.new(salt or bytes(HASH_LEN), ikm, HASH).digest()


def hkdf_expand(prk: bytes, info: bytes, length: int) -> bytes:
    """RFC 5869 HKDF-Expand with SHA-256."""
    if not 0 < length <= 255 * HASH_LEN:
        raise ValueError("invalid HKDF output length")
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), HASH).digest()
        okm += block
        counter += 1
    return okm[:length]


def hkdf(ikm: bytes, *, salt: bytes, info: bytes, length: int) -> bytes:
    return hkdf_expand(hkdf_extract(salt, ikm), info, length)


def _lp(data: bytes) -> bytes:
    """Length-prefix ``data`` with a 4-byte big-endian length."""
    return len(data).to_bytes(4, "big") + data


def mix_entropy(
    hardware: bytes,
    *,
    length: int = 32,
    info: bytes = INFO_FERNET_KEY,
    os_random: Callable[[int], bytes] = os.urandom,
) -> bytes:
    """Derive ``length`` key bytes from hardware bytes mixed with OS randomness.

    ``hardware`` may be empty (hardware unavailable and the caller has decided
    to allow an OS-only fallback); the result is then exactly as strong as the
    OS CSPRNG.
    """
    os_bytes = os_random(OS_ENTROPY_BYTES)
    if len(os_bytes) != OS_ENTROPY_BYTES:
        raise RuntimeError("OS CSPRNG returned a short read")
    ikm = _lp(hardware) + _lp(os_bytes)
    return hkdf(ikm, salt=MIX_SALT, info=info, length=length)
