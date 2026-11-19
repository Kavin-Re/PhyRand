"""Backwards-compatible entry point for the key-authority server.

The implementation now lives in the ``phyrand`` package (``phyrand/api.py``).
Both of these still work from the repository root::

    python api/qrng_api.py
    uvicorn api.qrng_api:app

Prefer ``phyrand serve``.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from phyrand.cli import main  # noqa: E402


def __getattr__(name: str) -> object:
    # Build the ASGI app lazily so importing this module has no side effects
    # (the original created ./vault and read .env at import time).
    if name == "app":
        from phyrand.api import create_app

        return create_app()
    raise AttributeError(name)


if __name__ == "__main__":
    raise SystemExit(main(["serve", *sys.argv[1:]]))
