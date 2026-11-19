"""Shared test doubles: no hardware, no network, deterministic."""

from __future__ import annotations

import random
from pathlib import Path

from phyrand.entropy import HardwareEntropy, KeyGenerator, SourceUnavailableError
from phyrand.health import HealthMonitor

REPO_ROOT = Path(__file__).resolve().parent.parent
CAPTURE = REPO_ROOT / "data" / "random_whitened.bin"
STRONG_TOKEN = "t3st-Only_Master-Token_0123456789abcdefXYZ"


class FakeSource:
    """Stands in for the serial port.

    ``mode`` can be switched at any time:
      * ``"random"``  -- seeded pseudo-random bytes (a healthy board)
      * ``"stuck"``   -- one repeating value (e.g. a saturated amplifier)
      * ``"biased"``  -- one value 40 % of the time, never in long runs
      * ``"timeout"`` -- returns no data (board silent / unplugged)
      * ``"error"``   -- the port cannot be opened
    """

    def __init__(self, mode: str = "random", seed: int = 1234) -> None:
        self.mode = mode
        self._rng = random.Random(seed)
        self.bytes_read = 0
        self.close_calls = 0

    def read(self, n: int) -> bytes:
        if self.mode == "error":
            raise SourceUnavailableError("fake: cannot open port")
        if self.mode == "timeout":
            return b""
        if self.mode == "stuck":
            data = b"\xaa" * n
        elif self.mode == "biased":
            data = bytes(0x55 if i % 5 in (0, 2) else self._rng.randrange(256) for i in range(n))
        else:
            data = self._rng.randbytes(n)
        self.bytes_read += len(data)
        return data

    def close(self) -> None:
        self.close_calls += 1


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def make_hardware(source: FakeSource, clock: FakeClock | None = None) -> HardwareEntropy:
    kwargs = {"clock": clock} if clock is not None else {}
    return HardwareEntropy(source, HealthMonitor(min_entropy=4.0), **kwargs)


def make_keygen(source: FakeSource, *, require_hardware: bool = True) -> KeyGenerator:
    return KeyGenerator(make_hardware(source), require_hardware=require_hardware)
