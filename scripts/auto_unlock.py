#!/usr/bin/env python3
"""Fetch a key from the key authority and decrypt a file (legacy entry point).

Equivalent to ``phyrand decrypt FILE --file-id ID --url URL``.

Configuration comes from the environment / ``.env`` (nothing is hard-coded):

    PHYRAND_API_URL        base URL of the key authority (https://...)
    PHYRAND_RELEASE_TOKEN  per-file release token (preferred), or
    VAULT_MASTER_TOKEN     the master token
"""

import os

import _bootstrap  # noqa: F401

from phyrand.cli import main
from phyrand.config import load_dotenv

if __name__ == "__main__":
    load_dotenv()
    url = os.environ.get("PHYRAND_API_URL") or input("Key authority URL: ").strip()
    path = input("Path of the .quantum file: ").strip().strip("'\"")
    file_id = input("File ID: ").strip().upper()
    raise SystemExit(main(["decrypt", path, "--file-id", file_id, "--url", url]))
