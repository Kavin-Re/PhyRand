#!/usr/bin/env python3
"""Decrypt a file with a key supplied out of band (legacy entry point).

Equivalent to ``phyrand decrypt FILE --key-prompt``.  The key is read without
echo, and the plaintext is written to disk rather than printed.
"""

import _bootstrap  # noqa: F401

from phyrand.cli import main

if __name__ == "__main__":
    path = input("Path of the .quantum file: ").strip().strip("'\"")
    raise SystemExit(main(["decrypt", path, "--key-prompt"]))
