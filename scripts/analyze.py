#!/usr/bin/env python3
"""Entropy analysis of a capture file.

    python scripts/analyze.py data/random_whitened.bin            # statistics (stdlib only)
    python scripts/analyze.py data/random_whitened.bin --plot     # + random-walk plot

The statistics are implemented in ``phyrand/stats.py`` (Shannon entropy,
chi-square, mean, serial correlation, Monte Carlo pi, SP 800-90B MCV
min-entropy).  ``--plot`` additionally needs numpy and matplotlib
(``pip install -r requirements-viz.txt``).
"""

import argparse
from pathlib import Path

import _bootstrap  # noqa: F401

from phyrand import stats

DEFAULT_FILE = _bootstrap.ROOT / "data" / "random_whitened.bin"


def plot_random_walk(data: bytes, title: str) -> None:
    """Cumulative sum of +1/-1 per bit; a drifting line indicates bias."""
    import matplotlib.pyplot as plt
    import numpy as np

    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    path = np.cumsum(np.where(bits == 1, 1, -1))
    plt.figure(figsize=(10, 5))
    plt.plot(path, linewidth=0.5)
    plt.axhline(0, color="black", linestyle="--")
    plt.title(f"Bit random walk: {title}")
    plt.xlabel("Bits processed")
    plt.ylabel("Cumulative (ones - zeros)")
    plt.grid(True)
    plt.show()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("file", nargs="?", default=str(DEFAULT_FILE))
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--plot", action="store_true", help="show the bit random walk")
    args = parser.parse_args()

    data = Path(args.file).read_bytes()
    report = stats.analyze(data)
    if args.json:
        import json

        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(stats.format_report(report, args.file))
    if args.plot:
        plot_random_walk(data, Path(args.file).name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
