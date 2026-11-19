"""Continuous health tests modelled on NIST SP 800-90B, section 4.4.

Two tests are implemented:

* **Repetition Count Test** (4.4.1) -- detects a source that becomes stuck on
  one value.
* **Adaptive Proportion Test** (4.4.2) -- detects a large loss of entropy that
  shows up as one value becoming too common inside a window.

Both are parameterised by ``H``, the *assumed* min-entropy per sample, and by a
false-positive probability ``alpha = 2**-alpha_exp``.

Important scope note
--------------------
SP 800-90B specifies these tests for the *raw* noise samples.  The PhyRand
firmware only exports bytes that have already been Von Neumann debiased, so
the host cannot see the raw ADC samples.  Running the tests on the debiased
byte stream still catches gross failures (stuck/constant output, strongly
skewed bytes, a disconnected or mis-wired board that emits a repeating
pattern), but it is **not** a compliant SP 800-90B health-test implementation
and the assumed ``H`` is an engineering parameter, not a validated entropy
estimate.  See ``docs/ARCHITECTURE.md``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

#: Minimum number of consecutive samples the start-up test must cover (4.3, item 10).
STARTUP_SAMPLES = 1024

#: Window sizes from SP 800-90B 4.4.2.
APT_WINDOW_BINARY = 1024
APT_WINDOW_NON_BINARY = 512


class HealthTestError(Exception):
    """Raised when a continuous health test rejects the sample stream."""

    def __init__(self, test: str, detail: str) -> None:
        super().__init__(f"{test}: {detail}")
        self.test = test
        self.detail = detail


def rct_cutoff(min_entropy: float, alpha_exp: int = 20) -> int:
    """Repetition Count Test cutoff ``C = 1 + ceil(-log2(alpha) / H)``."""
    _check_params(min_entropy, alpha_exp)
    return 1 + math.ceil(alpha_exp / min_entropy)


def _binom_log_pmf(n: int, k: int, p: float) -> float:
    return (
        math.lgamma(n + 1)
        - math.lgamma(k + 1)
        - math.lgamma(n - k + 1)
        + k * math.log(p)
        + (n - k) * math.log1p(-p)
    )


def critbinom(n: int, p: float, alpha: float) -> int:
    """Smallest ``k`` such that ``P[X > k] <= alpha`` for ``X ~ Binomial(n, p)``.

    This equals the spreadsheet function ``CRITBINOM(n, p, 1 - alpha)`` used by
    SP 800-90B, but sums the upper tail directly so that very small ``alpha``
    values do not lose precision.
    """
    if not 0.0 < p < 1.0:
        raise ValueError("p must be strictly between 0 and 1")
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be strictly between 0 and 1")
    tail = 0.0
    # Walk down from k = n; stop at the first k whose inclusion would push the
    # upper tail P[X >= k] above alpha.  Then P[X > k] <= alpha holds for that k.
    for k in range(n, -1, -1):
        tail += math.exp(_binom_log_pmf(n, k, p))
        if tail > alpha:
            return k
    return 0


def apt_cutoff(min_entropy: float, window: int, alpha_exp: int = 20) -> int:
    """Adaptive Proportion Test cutoff ``C = 1 + CRITBINOM(W, 2**-H, 1 - alpha)``."""
    _check_params(min_entropy, alpha_exp)
    if window < 2:
        raise ValueError("window must be at least 2")
    return 1 + critbinom(window, 2.0**-min_entropy, 2.0**-alpha_exp)


def _check_params(min_entropy: float, alpha_exp: int) -> None:
    if not min_entropy > 0:
        raise ValueError("assumed min-entropy must be positive")
    if not 20 <= alpha_exp <= 40:
        # SP 800-90B recommends alpha between 2^-20 and 2^-40.
        raise ValueError("alpha_exp must be in [20, 40]")


class RepetitionCountTest:
    """SP 800-90B 4.4.1.  Fails when one value repeats ``cutoff`` times in a row."""

    name = "repetition_count"

    def __init__(self, cutoff: int) -> None:
        if cutoff < 2:
            raise ValueError("cutoff must be at least 2")
        self.cutoff = cutoff
        self.reset()

    def reset(self) -> None:
        self._last: int | None = None
        self._run = 0

    def feed(self, sample: int) -> None:
        if sample == self._last:
            self._run += 1
            if self._run >= self.cutoff:
                run = self._run
                self.reset()
                raise HealthTestError(
                    self.name, f"value 0x{sample:02x} repeated {run} times (cutoff {self.cutoff})"
                )
        else:
            self._last = sample
            self._run = 1


class AdaptiveProportionTest:
    """SP 800-90B 4.4.2.  Fails when the first sample of a window recurs too often."""

    name = "adaptive_proportion"

    def __init__(self, cutoff: int, window: int = APT_WINDOW_NON_BINARY) -> None:
        if not 2 <= cutoff <= window:
            raise ValueError("cutoff must be in [2, window]")
        self.cutoff = cutoff
        self.window = window
        self.reset()

    def reset(self) -> None:
        self._reference: int | None = None
        self._seen = 0
        self._count = 0

    def feed(self, sample: int) -> None:
        if self._reference is None:
            self._reference = sample
            self._seen = 1
            self._count = 1
            return
        self._seen += 1
        if sample == self._reference:
            self._count += 1
            if self._count >= self.cutoff:
                count, ref = self._count, self._reference
                self.reset()
                raise HealthTestError(
                    self.name,
                    f"value 0x{ref:02x} seen {count} times in a {self.window}-sample "
                    f"window (cutoff {self.cutoff})",
                )
        if self._seen >= self.window:
            self.reset()


@dataclass
class HealthMonitor:
    """Runs both continuous tests over a byte stream and keeps counters.

    ``feed`` raises :class:`HealthTestError` on the first failing sample.  The
    caller must then discard every byte of that batch and re-run the start-up
    test (see :class:`phyrand.entropy.HardwareEntropy`).
    """

    min_entropy: float = 4.0
    alpha_exp: int = 20
    window: int = APT_WINDOW_NON_BINARY
    samples_tested: int = 0
    failures: int = 0
    last_failure: str | None = None
    _rct: RepetitionCountTest = field(init=False, repr=False)
    _apt: AdaptiveProportionTest = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if not 0 < self.min_entropy <= 8:
            raise ValueError("assumed min-entropy per byte must be in (0, 8]")
        self._rct = RepetitionCountTest(rct_cutoff(self.min_entropy, self.alpha_exp))
        self._apt = AdaptiveProportionTest(
            apt_cutoff(self.min_entropy, self.window, self.alpha_exp), self.window
        )

    @property
    def rct_cutoff(self) -> int:
        return self._rct.cutoff

    @property
    def apt_cutoff(self) -> int:
        return self._apt.cutoff

    def reset(self) -> None:
        """Forget in-progress runs/windows (counters are kept)."""
        self._rct.reset()
        self._apt.reset()

    def feed(self, data: bytes) -> None:
        for sample in data:
            self.samples_tested += 1
            try:
                self._rct.feed(sample)
                self._apt.feed(sample)
            except HealthTestError as exc:
                self.failures += 1
                self.last_failure = str(exc)
                self.reset()
                raise

    def describe(self) -> dict[str, object]:
        return {
            "assumed_min_entropy_bits_per_byte": self.min_entropy,
            "false_positive_rate": f"2^-{self.alpha_exp}",
            "rct_cutoff": self.rct_cutoff,
            "apt_window": self.window,
            "apt_cutoff": self.apt_cutoff,
            "samples_tested": self.samples_tested,
            "failures": self.failures,
            "last_failure": self.last_failure,
        }
