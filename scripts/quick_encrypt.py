#!/usr/bin/env python3
"""Encrypt a file without requiring the board (legacy entry point).

Equivalent to ``phyrand encrypt --allow-os-fallback FILE``: hardware entropy is
mixed in when the board is present and healthy; otherwise the key comes from
the OS CSPRNG only, and the command says so in its "entropy source" line.
"""

import sys

import _bootstrap  # noqa: F401

from phyrand.cli import main

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else input("File to encrypt: ").strip()
    raise SystemExit(main(["encrypt", "--allow-os-fallback", "--timeout", "2", target]))
