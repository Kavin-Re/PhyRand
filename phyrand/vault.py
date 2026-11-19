"""Key-escrow store: a small JSON file written atomically with owner-only permissions.

The vault holds the Fernet keys the key authority has issued, so whoever can
read this file (or holds the master token) can decrypt every escrowed file.
That is the definition of key escrow and the opposite of "zero knowledge";
the documentation says so explicitly.

Compared with the original implementation this module adds:

* strict validation of file IDs, extensions and keys (they used to be stored,
  echoed into HTML and used in download names unchecked);
* atomic replace (temp file + fsync + ``os.replace``) so a crash cannot leave a
  truncated vault that loses every key;
* ``0600`` file / ``0700`` directory permissions;
* a lock around read-modify-write cycles;
* per-file *release tokens* stored only as SHA-256 digests, so a recipient can
  be given the right to fetch one key without learning the master token.
"""

from __future__ import annotations

import base64
import binascii
import contextlib
import hashlib
import hmac
import json
import os
import re
import secrets
import tempfile
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2

FILE_ID_RE = re.compile(r"[A-Z0-9]{6,32}")
EXTENSION_RE = re.compile(r"[A-Za-z0-9]{1,16}")
DEFAULT_EXTENSION = "bin"
FILE_ID_BYTES = 6
MAX_ENTRIES = 100_000


class VaultError(Exception):
    """Base class for vault errors."""


class ValidationError(VaultError):
    """An identifier, extension or key was malformed."""


class DuplicateEntryError(VaultError):
    """The file ID already exists; entries are never silently overwritten."""


class VaultCorruptError(VaultError):
    """The vault file exists but cannot be parsed."""


def new_file_id() -> str:
    """Random 12-hex-character identifier (48 bits; an identifier, not a secret)."""
    return secrets.token_hex(FILE_ID_BYTES).upper()


def new_release_token() -> str:
    """Random 256-bit bearer token authorising the release of one key."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 of a high-entropy random token (not suitable for passwords)."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def validate_file_id(file_id: object) -> str:
    if not isinstance(file_id, str):
        raise ValidationError("file ID must be a string")
    candidate = file_id.strip().upper()
    if not FILE_ID_RE.fullmatch(candidate):
        raise ValidationError("file ID must be 6-32 characters of A-Z and 0-9")
    return candidate


def sanitize_extension(extension: object) -> str:
    """Return a safe extension; anything unexpected collapses to ``bin``."""
    if not isinstance(extension, str):
        return DEFAULT_EXTENSION
    candidate = extension.strip().lstrip(".")
    return candidate.lower() if EXTENSION_RE.fullmatch(candidate) else DEFAULT_EXTENSION


def validate_key(key: object) -> str:
    """Check that ``key`` is a well-formed Fernet key (URL-safe base64 of 32 bytes)."""
    if not isinstance(key, str) or len(key) != 44:
        raise ValidationError("key must be a 44-character URL-safe base64 string")
    try:
        raw = base64.b64decode(key.encode("ascii"), altchars=b"-_", validate=True)
    except (binascii.Error, UnicodeEncodeError, ValueError) as exc:
        raise ValidationError("key is not valid URL-safe base64") from exc
    if len(raw) != 32:
        raise ValidationError("key must decode to exactly 32 bytes")
    return key


class Vault:
    """Thread-safe JSON key store.  Use one server process per vault file."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path)
        self._lock = threading.RLock()

    # -- persistence ------------------------------------------------------

    def _load(self) -> dict[str, dict[str, Any]]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        try:
            data = json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError as exc:
            raise VaultCorruptError(f"{self.path} is not valid JSON: {exc}") from exc
        if not isinstance(data, dict):
            raise VaultCorruptError(f"{self.path} does not contain a JSON object")
        entries = data.get("entries") if "version" in data else data
        if not isinstance(entries, dict):
            raise VaultCorruptError(f"{self.path} has no usable entries table")
        return {
            str(file_id): self._normalise(entry)
            for file_id, entry in entries.items()
            if isinstance(entry, dict)
        }

    @staticmethod
    def _normalise(entry: dict[str, Any]) -> dict[str, Any]:
        """Accept both the current schema and the two legacy layouts."""
        return {
            "key": entry.get("key") or entry.get("quantum_key") or "",
            "extension": sanitize_extension(entry.get("extension")),
            "created_at": entry.get("created_at") or entry.get("timestamp"),
            "release_token_sha256": entry.get("release_token_sha256"),
        }

    def _save(self, entries: dict[str, dict[str, Any]]) -> None:
        directory = self.path.parent
        directory.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):  # e.g. filesystems without POSIX permissions
            os.chmod(directory, 0o700)
        payload = json.dumps({"version": SCHEMA_VERSION, "entries": entries}, indent=2)
        fd, tmp_name = tempfile.mkstemp(prefix=".vault-", suffix=".tmp", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:  # mkstemp creates 0600
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp_name, self.path)
        except BaseException:
            with contextlib.suppress(FileNotFoundError):
                os.unlink(tmp_name)
            raise

    # -- operations -------------------------------------------------------

    def add(self, file_id: str, key: str, extension: str = DEFAULT_EXTENSION) -> str:
        """Store ``key`` under ``file_id`` and return a new one-file release token.

        The release token is returned exactly once; only its hash is stored.
        """
        file_id = validate_file_id(file_id)
        key = validate_key(key)
        release_token = new_release_token()
        with self._lock:
            entries = self._load()
            if file_id in entries:
                raise DuplicateEntryError(f"file ID {file_id} already exists")
            if len(entries) >= MAX_ENTRIES:
                raise VaultError("vault is full")
            entries[file_id] = {
                "key": key,
                "extension": sanitize_extension(extension),
                "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "release_token_sha256": hash_token(release_token),
            }
            self._save(entries)
        return release_token

    def get(self, file_id: str) -> dict[str, Any] | None:
        file_id = validate_file_id(file_id)
        with self._lock:
            return self._load().get(file_id)

    def remove(self, file_id: str) -> bool:
        file_id = validate_file_id(file_id)
        with self._lock:
            entries = self._load()
            if file_id not in entries:
                return False
            del entries[file_id]
            self._save(entries)
            return True

    def list_metadata(self) -> dict[str, dict[str, Any]]:
        """Entries *without* key material, for listings."""
        with self._lock:
            return {
                file_id: {"extension": entry["extension"], "created_at": entry["created_at"]}
                for file_id, entry in self._load().items()
            }

    @staticmethod
    def release_token_matches(entry: dict[str, Any], token: str) -> bool:
        stored = entry.get("release_token_sha256")
        if not isinstance(stored, str) or not token:
            return False
        return hmac.compare_digest(stored, hash_token(token))
