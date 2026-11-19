"""Statistical analysis of entropy captures using only the standard library.

These are *descriptive* statistics, comparable to the classic ``ent`` tool,
plus the Most Common Value min-entropy estimate from NIST SP 800-90B 6.3.1.

None of them can prove that a source is random.  A good CSPRNG, or a broken
noise source followed by a strong whitener, passes all of them.  In particular
the capture shipped in ``data/`` was taken *after* Von Neumann debiasing, so
these numbers describe the conditioned output, not the raw noise source.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import asdict, dataclass

#: z-score for the 99 % upper confidence bound used by the MCV estimator.
_Z_99 = 2.5758293035489


@dataclass(frozen=True)
class Report:
    """Summary statistics for a byte sequence."""

    length_bytes: int
    shannon_entropy_bits_per_byte: float
    chi_square: float
    chi_square_p_value: float
    arithmetic_mean: float
    serial_correlation: float
    monte_carlo_pi: float
    monte_carlo_pi_error_percent: float
    mcv_min_entropy_bits_per_byte: float
    most_common_byte: int
    most_common_byte_count: int
    ones_fraction: float
    mcv_min_entropy_bits_per_bit: float
    #: Fraction of ones at each bit position; index 0 is the least-significant bit.
    #: The firmware packs MSB-first, so index 7 is the first bit of every byte.
    bit_position_ones_fraction: tuple[float, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def bit_position_z_scores(self) -> tuple[float, ...]:
        """Deviation of each bit position from 0.5, in standard deviations."""
        sigma = 0.5 / math.sqrt(self.length_bytes)
        return tuple((f - 0.5) / sigma for f in self.bit_position_ones_fraction)


def shannon_entropy(data: bytes) -> float:
    """Shannon entropy of the byte histogram, in bits per byte (0..8)."""
    if not data:
        raise ValueError("no data")
    n = len(data)
    return -sum(c / n * math.log2(c / n) for c in Counter(data).values())


def chi_square(data: bytes) -> float:
    """Pearson chi-square statistic of the byte histogram against uniform (255 d.o.f.)."""
    if not data:
        raise ValueError("no data")
    expected = len(data) / 256
    counts = Counter(data)
    return sum((counts.get(v, 0) - expected) ** 2 / expected for v in range(256))


def _gammaincc(a: float, x: float) -> float:
    """Regularised upper incomplete gamma function Q(a, x)."""
    if x <= 0:
        return 1.0
    log_prefactor = -x + a * math.log(x) - math.lgamma(a)
    if x < a + 1:
        # Series for P(a, x).
        term = 1.0 / a
        total = term
        k = a
        for _ in range(10_000):
            k += 1
            term *= x / k
            total += term
            if abs(term) < abs(total) * 1e-15:
                break
        return max(0.0, 1.0 - total * math.exp(log_prefactor))
    # Continued fraction for Q(a, x) (modified Lentz).
    tiny = 1e-300
    b = x + 1 - a
    c = 1 / tiny
    d = 1 / b
    h = d
    for i in range(1, 10_000):
        an = -i * (i - a)
        b += 2
        d = an * d + b
        d = tiny if abs(d) < tiny else d
        c = b + an / c
        c = tiny if abs(c) < tiny else c
        d = 1 / d
        delta = d * c
        h *= delta
        if abs(delta - 1) < 1e-15:
            break
    return min(1.0, h * math.exp(log_prefactor))


def chi_square_p_value(statistic: float, dof: int = 255) -> float:
    """Probability that a uniform source produces a statistic at least this large."""
    return _gammaincc(dof / 2, statistic / 2)


def arithmetic_mean(data: bytes) -> float:
    if not data:
        raise ValueError("no data")
    return sum(data) / len(data)


def serial_correlation(data: bytes) -> float:
    """Lag-1 serial correlation coefficient (same circular definition as ``ent``)."""
    n = len(data)
    if n < 2:
        raise ValueError("need at least two bytes")
    sum_x = sum(data)
    sum_xx = sum(b * b for b in data)
    sum_xy = sum(a * b for a, b in zip(data, data[1:], strict=False)) + data[-1] * data[0]
    denominator = n * sum_xx - sum_x * sum_x
    if denominator == 0:
        return 1.0  # constant sequence: fully correlated
    return (n * sum_xy - sum_x * sum_x) / denominator


def monte_carlo_pi(data: bytes) -> float:
    """Estimate pi from 6-byte (x, y) points, as ``ent`` does."""
    points = len(data) // 6
    if points == 0:
        raise ValueError("need at least six bytes")
    radius_sq = (2**24 - 1) ** 2
    inside = 0
    for i in range(points):
        x = int.from_bytes(data[6 * i : 6 * i + 3], "big")
        y = int.from_bytes(data[6 * i + 3 : 6 * i + 6], "big")
        if x * x + y * y <= radius_sq:
            inside += 1
    return 4.0 * inside / points


def mcv_min_entropy(most_common_count: int, total: int) -> float:
    """SP 800-90B 6.3.1 Most Common Value estimate, in bits per symbol.

    Uses the upper end of a 99 % confidence interval on the frequency of the
    most common symbol, so it is deliberately pessimistic for short inputs.
    """
    if total < 2 or not 0 < most_common_count <= total:
        raise ValueError("invalid counts")
    p_hat = most_common_count / total
    p_upper = min(1.0, p_hat + _Z_99 * math.sqrt(p_hat * (1 - p_hat) / (total - 1)))
    return -math.log2(p_upper)


def ones_fraction(data: bytes) -> float:
    """Fraction of 1 bits (0.5 for an unbiased source)."""
    if not data:
        raise ValueError("no data")
    return sum(bin(b).count("1") for b in data) / (8 * len(data))


def bit_position_ones_fraction(data: bytes) -> tuple[float, ...]:
    """Fraction of ones at each of the eight bit positions (index 0 = LSB)."""
    if not data:
        raise ValueError("no data")
    counts = Counter(data)
    return tuple(
        sum(c for value, c in counts.items() if value >> k & 1) / len(data) for k in range(8)
    )


def analyze(data: bytes) -> Report:
    """Compute the full :class:`Report` for ``data``."""
    if len(data) < 6:
        raise ValueError("need at least six bytes to analyse")
    value, count = Counter(data).most_common(1)[0]
    chi = chi_square(data)
    pi_estimate = monte_carlo_pi(data)
    ones = ones_fraction(data)
    total_bits = 8 * len(data)
    majority_bits = round(max(ones, 1 - ones) * total_bits)
    return Report(
        length_bytes=len(data),
        shannon_entropy_bits_per_byte=shannon_entropy(data),
        chi_square=chi,
        chi_square_p_value=chi_square_p_value(chi),
        arithmetic_mean=arithmetic_mean(data),
        serial_correlation=serial_correlation(data),
        monte_carlo_pi=pi_estimate,
        monte_carlo_pi_error_percent=abs(pi_estimate - math.pi) / math.pi * 100,
        mcv_min_entropy_bits_per_byte=mcv_min_entropy(count, len(data)),
        most_common_byte=value,
        most_common_byte_count=count,
        ones_fraction=ones,
        mcv_min_entropy_bits_per_bit=mcv_min_entropy(majority_bits, total_bits),
        bit_position_ones_fraction=bit_position_ones_fraction(data),
    )


def format_report(report: Report, name: str = "") -> str:
    """Human-readable rendering of a :class:`Report`."""
    r = report
    lines = [
        f"Entropy analysis{' of ' + name if name else ''} ({r.length_bytes:,} bytes)",
        "",
        f"  Shannon entropy        {r.shannon_entropy_bits_per_byte:.6f} bits/byte (ideal 8)",
        f"  Chi-square (255 dof)   {r.chi_square:.2f}  (p = {r.chi_square_p_value:.4f})",
        f"  Arithmetic mean        {r.arithmetic_mean:.4f}  (ideal 127.5)",
        f"  Serial correlation     {r.serial_correlation:+.6f}  (ideal 0)",
        f"  Monte Carlo pi         {r.monte_carlo_pi:.6f}"
        f"  (error {r.monte_carlo_pi_error_percent:.3f} %)",
        f"  Ones fraction          {r.ones_fraction:.6f}  (ideal 0.5)",
        f"  MCV min-entropy        {r.mcv_min_entropy_bits_per_byte:.4f} bits/byte"
        f"  (most common 0x{r.most_common_byte:02x} x {r.most_common_byte_count})",
        f"  MCV min-entropy (bits) {r.mcv_min_entropy_bits_per_bit:.6f} bits/bit",
        "",
        "  Ones fraction per bit position (bit 7 = first bit the firmware emits per byte):",
        *(
            f"    bit {k}: {r.bit_position_ones_fraction[k]:.6f}  (z = {z:+.2f})"
            for k, z in reversed(list(enumerate(r.bit_position_z_scores())))
        ),
        "",
        "  These describe the conditioned output only. They do not validate the",
        "  noise source; see docs/ARCHITECTURE.md ('What is and is not claimed').",
    ]
    return "\n".join(lines)
