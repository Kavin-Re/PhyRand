"""File encryption helpers built on Fernet.

Fernet (https://github.com/fernet/spec) is authenticated encryption:
AES-128 in CBC mode with PKCS#7 padding, authenticated with HMAC-SHA256
(encrypt-then-MAC).  The 32-byte Fernet key is two independent 128-bit keys:
bytes 0-15 sign, bytes 16-31 encrypt.

Fernet processes the whole message in memory and is therefore meant for small
and medium files, not multi-gigabyte ones.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

ENCRYPTED_SUFFIX = ".quantum"  # historical name kept for compatibility with existing files


class DecryptionError(Exception):
    """The token failed authentication (wrong key, or the file was modified)."""


def _fernet(key: str | bytes) -> Any:
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - depends on environment
        raise RuntimeError("the 'cryptography' package is required for file encryption") from exc
    return Fernet(key)


def encrypt_bytes(key: str | bytes, plaintext: bytes) -> bytes:
    return bytes(_fernet(key).encrypt(plaintext))


def decrypt_bytes(key: str | bytes, token: bytes) -> bytes:
    from cryptography.fernet import InvalidToken

    try:
        return bytes(_fernet(key).decrypt(token.strip()))
    except InvalidToken as exc:
        raise DecryptionError("authentication failed: wrong key or corrupted file") from exc


def encrypted_path(path: Path) -> Path:
    return path.with_name(path.name + ENCRYPTED_SUFFIX)


def decrypted_path(path: Path, extension: str | None = None) -> Path:
    """Default output name: strip a trailing ``.quantum`` or append ``.decrypted``.

    Only the final suffix is touched (the old scripts used ``str.replace``,
    which also rewrote directory names containing ``.quantum``).
    """
    if path.name.endswith(ENCRYPTED_SUFFIX) and len(path.name) > len(ENCRYPTED_SUFFIX):
        candidate = path.with_name(path.name[: -len(ENCRYPTED_SUFFIX)])
    else:
        candidate = path.with_name(path.name + ".decrypted")
    if extension and not candidate.suffix:
        candidate = candidate.with_name(f"{candidate.name}.{extension}")
    return candidate


def write_new_file(path: Path, data: bytes, *, force: bool = False, private: bool = False) -> None:
    """Write ``data`` to ``path``; refuse to overwrite unless ``force`` is set."""
    flags = os.O_WRONLY | os.O_CREAT | (os.O_TRUNC if force else os.O_EXCL)
    try:
        fd = os.open(path, flags, 0o600 if private else 0o644)
    except FileExistsError as exc:
        raise FileExistsError(f"{path} already exists (use --force to overwrite)") from exc
    with os.fdopen(fd, "wb") as handle:
        handle.write(data)


def encrypt_file(key: str | bytes, source: Path, *, force: bool = False) -> Path:
    target = encrypted_path(source)
    write_new_file(target, encrypt_bytes(key, source.read_bytes()), force=force)
    return target


def decrypt_file(
    key: str | bytes,
    source: Path,
    target: Path | None = None,
    *,
    extension: str | None = None,
    force: bool = False,
) -> Path:
    plaintext = decrypt_bytes(key, source.read_bytes())
    target = target or decrypted_path(source, extension)
    write_new_file(target, plaintext, force=force, private=True)
    return target
