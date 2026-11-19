#!/usr/bin/env python3
"""Sender-side menu (legacy entry point).

Thin wrapper around the ``phyrand`` CLI, kept so existing habits keep working:

    1. Encrypt a file   -> phyrand encrypt FILE
    2. List the vault   -> phyrand vault list
    3. Revoke a key     -> phyrand vault revoke FILE_ID

The old option "release key" printed the raw key to the terminal; recipients
now use the file ID + release token with ``phyrand decrypt`` or the web client.
"""

import _bootstrap  # noqa: F401

from phyrand.cli import main


def menu() -> None:
    while True:
        print("\n--- PhyRand sender menu ---")
        print("1. Encrypt file (hardware entropy, fail closed)")
        print("2. List vaulted files")
        print("3. Revoke a key")
        print("4. Exit")
        choice = input("Choice: ").strip()
        if choice == "1":
            main(["encrypt", input("File to encrypt: ").strip()])
        elif choice == "2":
            main(["vault", "list"])
        elif choice == "3":
            main(["vault", "revoke", input("File ID: ").strip()])
        elif choice == "4":
            break


if __name__ == "__main__":
    menu()
