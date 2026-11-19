"""Hardware entropy acquisition and key generation.

Pipeline (see ``docs/ARCHITECTURE.md``)::

    STM32 UART byte stream
        -> start-up health test (>= 1024 samples, discarded)
        -> continuous health tests (RCT + APT) on every byte used
        -> HKDF-SHA256 conditioning, mixed with os.urandom
        -> 32-byte Fernet key

The serial port is opened once and kept open (the previous implementation
re-opened it on every HTTP request, and an unauthenticated endpoint could
drain it).  All access is serialised by a lock.
"""

from __future__ import annotations

import base64
import contextlib
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol

from .conditioning import INFO_FERNET_KEY, mix_entropy
from .health import STARTUP_SAMPLES, HealthMonitor, HealthTestError

STATE_NOT_STARTED = "not_started"
STATE_OK = "ok"
STATE_UNAVAILABLE = "unavailable"
STATE_HEALTH_FAILURE = "health_failure"


class EntropyError(Exception):
    """Base class for entropy acquisition errors."""


class SourceUnavailableError(EntropyError):
    """The hardware could not be opened or stopped delivering bytes."""


class SourceHealthError(EntropyError):
    """The hardware delivered bytes, but they failed a health test."""


class EntropySource(Protocol):
    """Anything that can deliver bytes from the noise source."""

    def read(self, n: int) -> bytes:
        """Return up to ``n`` bytes; fewer means the source timed out."""
        ...

    def close(self) -> None: ...


class SerialSource:
    """Lazily opened, persistent pyserial connection to the STM32 board."""

    def __init__(self, port: str, baud_rate: int = 115200, timeout: float = 5.0) -> None:
        self.port = port
        self.baud_rate = baud_rate
        self.timeout = timeout
        self._serial: Any = None

    def _open(self) -> Any:
        if self._serial is None:
            try:
                import serial  # pyserial, imported lazily so tests need no hardware stack
            except ImportError as exc:  # pragma: no cover - depends on environment
                raise SourceUnavailableError("pyserial is not installed") from exc
            try:
                self._serial = serial.Serial(self.port, self.baud_rate, timeout=self.timeout)
                # Bytes queued before we attached were not health-tested as a
                # contiguous run with what follows; drop them.
                self._serial.reset_input_buffer()
            except (OSError, ValueError) as exc:  # SerialException subclasses OSError
                self._serial = None
                raise SourceUnavailableError(f"cannot open {self.port}: {exc}") from exc
        return self._serial

    def read(self, n: int) -> bytes:
        ser = self._open()
        try:
            return bytes(ser.read(n))
        except OSError as exc:
            self.close()
            raise SourceUnavailableError(f"read from {self.port} failed: {exc}") from exc

    def close(self) -> None:
        if self._serial is not None:
            with contextlib.suppress(OSError):
                self._serial.close()
            self._serial = None


class HardwareEntropy:
    """Health-tested access to an :class:`EntropySource`.

    * Before the first use, and again after any failure, ``startup_samples``
      consecutive bytes must pass the health tests.  Those bytes are discarded.
    * Every byte handed out has passed through the continuous tests.
    * A health failure discards the whole batch and forces a new start-up test.
    """

    def __init__(
        self,
        source: EntropySource,
        monitor: HealthMonitor | None = None,
        *,
        startup_samples: int = STARTUP_SAMPLES,
        retry_interval: float = 10.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if startup_samples < STARTUP_SAMPLES:
            raise ValueError(f"start-up test needs at least {STARTUP_SAMPLES} samples")
        self._source = source
        self._monitor = monitor or HealthMonitor()
        self._startup_samples = startup_samples
        self._retry_interval = retry_interval
        self._clock = clock
        self._lock = threading.Lock()
        self._state = STATE_NOT_STARTED
        self._last_error: str | None = None
        self._last_attempt: float | None = None
        self._bytes_delivered = 0
        self._startups_passed = 0

    # -- internal helpers (lock held) -------------------------------------

    def _read_exact(self, n: int) -> bytes:
        chunks: list[bytes] = []
        remaining = n
        while remaining:
            chunk = self._source.read(remaining)
            if not chunk:
                raise SourceUnavailableError(
                    f"source timed out ({n - remaining} of {n} bytes received)"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)

    def _read_tested(self, n: int) -> bytes:
        try:
            data = self._read_exact(n)
        except SourceUnavailableError as exc:
            self._fail(STATE_UNAVAILABLE, str(exc))
            raise
        try:
            self._monitor.feed(data)
        except HealthTestError as exc:
            self._fail(STATE_HEALTH_FAILURE, str(exc))
            raise SourceHealthError(str(exc)) from exc
        return data

    def _fail(self, state: str, message: str) -> None:
        self._state = state
        self._last_error = message
        self._monitor.reset()
        self._source.close()

    def _ensure_started(self) -> None:
        if self._state == STATE_OK:
            return
        self._last_attempt = self._clock()
        self._monitor.reset()
        self._read_tested(self._startup_samples)  # result intentionally discarded
        self._state = STATE_OK
        self._last_error = None
        self._startups_passed += 1

    # -- public API -------------------------------------------------------

    def get_bytes(self, n: int) -> bytes:
        """Return ``n`` health-tested bytes or raise :class:`EntropyError`."""
        if n <= 0:
            raise ValueError("n must be positive")
        with self._lock:
            self._ensure_started()
            data = self._read_tested(n)
            self._bytes_delivered += n
            return data

    def probe(self, *, force: bool = False) -> bool:
        """Try to bring the source online; never raises.

        Unless ``force`` is set, attempts are rate-limited to one per
        ``retry_interval`` seconds so that status polling cannot hammer the port.
        """
        with self._lock:
            if self._state == STATE_OK:
                return True
            if (
                not force
                and self._last_attempt is not None
                and self._clock() - self._last_attempt < self._retry_interval
            ):
                return False
            try:
                self._ensure_started()
            except EntropyError:
                return False
            return True

    @property
    def state(self) -> str:
        return self._state

    def status(self) -> dict[str, object]:
        """Snapshot for the health endpoint (contains no entropy)."""
        return {
            "state": self._state,
            "last_error": self._last_error,
            "bytes_delivered": self._bytes_delivered,
            "startup_tests_passed": self._startups_passed,
            "startup_samples": self._startup_samples,
            "health_tests": self._monitor.describe(),
        }

    def close(self) -> None:
        with self._lock:
            self._source.close()
            if self._state == STATE_OK:
                self._state = STATE_NOT_STARTED


@dataclass(frozen=True)
class GeneratedKey:
    """A freshly derived key and a description of where its entropy came from."""

    key: bytes
    hardware_bytes: int
    source: str  # "hardware+os" or "os-only"

    @property
    def fernet_key(self) -> str:
        """URL-safe base64 form expected by Fernet."""
        return base64.urlsafe_b64encode(self.key).decode("ascii")

    def provenance(self) -> dict[str, object]:
        return {
            "source": self.source,
            "hardware_bytes_mixed": self.hardware_bytes,
            "conditioning": "HKDF-SHA256(hardware || os.urandom)",
        }


class KeyGenerator:
    """Derives keys from health-tested hardware bytes mixed with the OS CSPRNG.

    ``require_hardware=True`` (the default) is *fail closed*: if the board is
    missing or failing its health tests, :meth:`generate` raises instead of
    silently handing out a key the hardware did not contribute to.  With
    ``require_hardware=False`` the generator falls back to OS-only keys and
    labels them ``"os-only"``; such keys are still cryptographically strong,
    they are just not what this project is about.
    """

    def __init__(
        self,
        hardware: HardwareEntropy | None,
        *,
        require_hardware: bool = True,
        raw_bytes_per_key: int = 128,
        os_random: Callable[[int], bytes] | None = None,
    ) -> None:
        if raw_bytes_per_key < 32:
            raise ValueError("raw_bytes_per_key must be at least 32")
        self.hardware = hardware
        self.require_hardware = require_hardware
        self.raw_bytes_per_key = raw_bytes_per_key
        self._os_random = os_random

    def generate(self, *, length: int = 32, info: bytes = INFO_FERNET_KEY) -> GeneratedKey:
        raw = b""
        if self.hardware is None:
            if self.require_hardware:
                raise SourceUnavailableError("no hardware entropy source configured")
        else:
            try:
                raw = self.hardware.get_bytes(self.raw_bytes_per_key)
            except EntropyError:
                if self.require_hardware:
                    raise
        kwargs: dict[str, Any] = {"length": length, "info": info}
        if self._os_random is not None:
            kwargs["os_random"] = self._os_random
        key = mix_entropy(raw, **kwargs)
        return GeneratedKey(
            key=key, hardware_bytes=len(raw), source="hardware+os" if raw else "os-only"
        )
