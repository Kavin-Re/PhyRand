"""Reference model of the firmware's Von Neumann debiaser.

``firmware/Core/Src/main.c`` takes the least-significant bit of each ADC
sample, groups the bits into non-overlapping pairs, drops ``00``/``11`` pairs
and emits the *first* bit of each ``01``/``10`` pair.  Eight emitted bits are
packed MSB-first into one output byte.

This module mirrors that logic bit-for-bit so the algorithm can be unit-tested
on the host and applied to raw captures.  It is not used on the key path.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator


def von_neumann_bits(bits: Iterable[int]) -> Iterator[int]:
    """Yield debiased bits from an iterable of raw 0/1 bits."""
    first: int | None = None
    for bit in bits:
        bit &= 1
        if first is None:
            first = bit
            continue
        if first != bit:
            yield first
        first = None


def pack_bits_msb_first(bits: Iterable[int]) -> bytes:
    """Pack bits into bytes MSB-first; a trailing partial byte is discarded."""
    out = bytearray()
    acc = 0
    count = 0
    for bit in bits:
        acc = ((acc << 1) | (bit & 1)) & 0xFF
        count += 1
        if count == 8:
            out.append(acc)
            acc = 0
            count = 0
    return bytes(out)


def von_neumann_bytes(adc_samples: Iterable[int]) -> bytes:
    """Model of the whole firmware loop: ADC samples in, debiased bytes out."""
    return pack_bits_msb_first(von_neumann_bits(sample & 1 for sample in adc_samples))
