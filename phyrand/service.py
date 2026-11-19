"""Key-authority business logic, independent of any web framework.

Keeping this layer free of FastAPI means authentication, validation, rate
limiting and the fail-closed entropy policy are covered by plain ``unittest``
tests; :mod:`phyrand.api` only translates HTTP to these calls.
"""

from __future__ import annotations

import hashlib
import hmac
import threading
import time
from collections import deque
from collections.abc import Callable
from typing import Any

from .entropy import EntropyError, KeyGenerator
from .vault import (
    DuplicateEntryError,
    ValidationError,
    Vault,
    new_file_id,
    validate_file_id,
    validate_key,
)

PENDING_TTL_SECONDS = 600.0
MAX_PENDING = 256
MAX_AUTH_FAILURES = 10
AUTH_FAILURE_WINDOW_SECONDS = 60.0
MAX_TRACKED_CLIENTS = 4096


class ServiceError(Exception):
    """Base class; ``status`` is the HTTP status the API layer should use."""

    status = 500


class AuthError(ServiceError):
    status = 401


class RateLimitedError(ServiceError):
    status = 429


class NotFoundError(ServiceError):
    status = 404


class ConflictError(ServiceError):
    status = 409


class BadRequestError(ServiceError):
    status = 422


class EntropyUnavailableError(ServiceError):
    status = 503


def tokens_equal(supplied: str | None, expected: str) -> bool:
    """Constant-time comparison that also tolerates a missing header.

    Both sides are hashed first so the comparison time does not depend on the
    length of either value.
    """
    if not supplied:
        return False
    a = hashlib.sha256(supplied.encode("utf-8", "surrogatepass")).digest()
    b = hashlib.sha256(expected.encode("utf-8")).digest()
    return hmac.compare_digest(a, b)


class FailureLimiter:
    """Blocks a client after too many failed authentications in a time window."""

    def __init__(
        self,
        max_failures: int = MAX_AUTH_FAILURES,
        window: float = AUTH_FAILURE_WINDOW_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_failures
        self._window = window
        self._clock = clock
        self._failures: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def _prune(self, client: str, now: float) -> deque[float]:
        events = self._failures.setdefault(client, deque())
        while events and now - events[0] > self._window:
            events.popleft()
        return events

    def check(self, client: str) -> None:
        with self._lock:
            events = self._prune(client, self._clock())
            if len(events) >= self._max:
                raise RateLimitedError("too many failed attempts; try again later")
            if not events:
                del self._failures[client]

    def record_failure(self, client: str) -> None:
        with self._lock:
            now = self._clock()
            if client not in self._failures and len(self._failures) >= MAX_TRACKED_CLIENTS:
                # Bound memory: drop the stalest client record.
                stalest = min(self._failures, key=lambda c: self._failures[c][-1])
                del self._failures[stalest]
            self._prune(client, now).append(now)


class KeyAuthority:
    """Issues keys, escrows them and releases them to authorised callers."""

    def __init__(
        self,
        master_token: str,
        vault: Vault,
        keygen: KeyGenerator,
        *,
        limiter: FailureLimiter | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._master_token = master_token
        self._vault = vault
        self._keygen = keygen
        self._limiter = limiter or FailureLimiter(clock=clock)
        self._clock = clock
        self._pending: dict[str, tuple[bytes, float]] = {}
        self._lock = threading.Lock()

    # -- authentication ---------------------------------------------------

    def _require_master(self, token: str | None, client: str) -> None:
        self._limiter.check(client)
        if not tokens_equal(token, self._master_token):
            self._limiter.record_failure(client)
            raise AuthError("invalid or missing API token")

    # -- pending issuance -------------------------------------------------

    def _expire_pending(self) -> None:
        now = self._clock()
        for file_id in [f for f, (_, t) in self._pending.items() if now - t > PENDING_TTL_SECONDS]:
            del self._pending[file_id]

    @staticmethod
    def _key_digest(key: str) -> bytes:
        return hashlib.sha256(key.encode("ascii")).digest()

    # -- operations -------------------------------------------------------

    def status(self) -> dict[str, Any]:
        """Public liveness summary.  Contains no entropy and no vault data."""
        hardware = self._keygen.hardware
        state = "not_configured"
        if hardware is not None:
            hardware.probe()
            state = hardware.state
        can_issue = state == "ok" or not self._keygen.require_hardware
        return {
            "status": "ONLINE" if state == "ok" else "DEGRADED" if can_issue else "OFFLINE",
            "hardware": state,
            "require_hardware": self._keygen.require_hardware,
            "can_issue_keys": can_issue,
        }

    def health(self, token: str | None, client: str = "local") -> dict[str, Any]:
        """Detailed health-test report (master token required)."""
        self._require_master(token, client)
        report = self.status()
        hardware = self._keygen.hardware
        report["entropy"] = hardware.status() if hardware is not None else None
        report["raw_bytes_per_key"] = self._keygen.raw_bytes_per_key
        return report

    def request_key(self, token: str | None, client: str = "local") -> dict[str, Any]:
        """Generate a key and reserve a file ID; the key is not stored yet."""
        self._require_master(token, client)
        try:
            generated = self._keygen.generate()
        except EntropyError as exc:
            raise EntropyUnavailableError(
                f"hardware entropy unavailable, refusing to issue a key: {exc}"
            ) from exc
        key = generated.fernet_key
        with self._lock:
            self._expire_pending()
            if len(self._pending) >= MAX_PENDING:
                oldest = min(self._pending, key=lambda f: self._pending[f][1])
                del self._pending[oldest]
            file_id = new_file_id()
            while file_id in self._pending or self._vault.get(file_id) is not None:
                file_id = new_file_id()
            self._pending[file_id] = (self._key_digest(key), self._clock())
        return {"key": key, "file_id": file_id, "entropy": generated.provenance()}

    def commit(
        self, token: str | None, file_id: str, key: str, extension: str, client: str = "local"
    ) -> dict[str, Any]:
        """Escrow a key previously issued by :meth:`request_key`.

        Only (file ID, key) pairs this process issued in the last ten minutes
        are accepted, so clients cannot plant arbitrary keys or overwrite
        existing entries.
        """
        self._require_master(token, client)
        try:
            file_id = validate_file_id(file_id)
            key = validate_key(key)
        except ValidationError as exc:
            raise BadRequestError(str(exc)) from exc
        with self._lock:
            self._expire_pending()
            pending = self._pending.get(file_id)
            if pending is None or not hmac.compare_digest(pending[0], self._key_digest(key)):
                raise ConflictError("no matching pending key; call /request-keys first")
            try:
                release_token = self._vault.add(file_id, key, extension)
            except DuplicateEntryError as exc:
                raise ConflictError(str(exc)) from exc
            del self._pending[file_id]
        return {"status": "committed", "file_id": file_id, "release_token": release_token}

    def release(self, token: str | None, file_id: str, client: str = "local") -> dict[str, Any]:
        """Return an escrowed key to the master token or that file's release token."""
        self._limiter.check(client)
        try:
            file_id = validate_file_id(file_id)
        except ValidationError as exc:
            raise BadRequestError(str(exc)) from exc
        is_master = tokens_equal(token, self._master_token)
        entry = self._vault.get(file_id)
        if entry is None:
            if is_master:
                raise NotFoundError("unknown file ID")
            # Do not reveal which IDs exist to callers without the master token.
            self._limiter.record_failure(client)
            raise AuthError("invalid token or unknown file ID")
        if not (is_master or Vault.release_token_matches(entry, token or "")):
            self._limiter.record_failure(client)
            raise AuthError("invalid token or unknown file ID")
        return {"key": entry["key"], "extension": entry["extension"]}

    def revoke(self, token: str | None, file_id: str, client: str = "local") -> dict[str, Any]:
        self._require_master(token, client)
        try:
            removed = self._vault.remove(file_id)
        except ValidationError as exc:
            raise BadRequestError(str(exc)) from exc
        if not removed:
            raise NotFoundError("unknown file ID")
        return {"status": "revoked", "file_id": validate_file_id(file_id)}

    def list_entries(self, token: str | None, client: str = "local") -> dict[str, Any]:
        """Vault index without key material."""
        self._require_master(token, client)
        return self._vault.list_metadata()
