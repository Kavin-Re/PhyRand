"""``phyrand`` command-line interface."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from collections.abc import Sequence
from pathlib import Path

from . import __version__, stats
from .client import ApiError, KeyAuthorityClient
from .config import ConfigError, Settings, load_dotenv
from .entropy import EntropyError, HardwareEntropy, KeyGenerator, SerialSource
from .filecrypt import DecryptionError, decrypt_file, encrypt_file
from .health import HealthMonitor
from .vault import Vault, VaultError, new_file_id, validate_file_id, validate_key

DEFAULT_PORT = "/dev/ttyACM0"


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _hardware(args: argparse.Namespace) -> HardwareEntropy:
    return HardwareEntropy(
        SerialSource(args.port, args.baud, args.timeout),
        HealthMonitor(min_entropy=args.min_entropy),
    )


def _vault(args: argparse.Namespace) -> Vault:
    return Vault(Path(args.vault_dir) / "quantum_vault.json")


def _add_serial_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--port", default=_env("QRNG_SERIAL_PORT", DEFAULT_PORT))
    parser.add_argument("--baud", type=int, default=int(_env("PHYRAND_BAUD_RATE", "115200")))
    parser.add_argument("--timeout", type=float, default=10.0, help="serial read timeout (s)")
    parser.add_argument(
        "--min-entropy",
        type=float,
        default=float(_env("PHYRAND_ASSUMED_MIN_ENTROPY", "4.0")),
        help="assumed min-entropy per byte used to size the health-test cutoffs",
    )


def _add_vault_option(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--vault-dir", default=_env("PHYRAND_VAULT_DIR", "vault"))


def _remote_token(prompt: str) -> str:
    token = os.environ.get("PHYRAND_RELEASE_TOKEN") or os.environ.get("VAULT_MASTER_TOKEN")
    return token or getpass.getpass(prompt)


# -- commands -------------------------------------------------------------


def cmd_token(_args: argparse.Namespace) -> int:
    print(secrets.token_urlsafe(32))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    try:
        import uvicorn

        from .api import create_app
    except ImportError as exc:
        print(f"error: server dependencies missing ({exc}); pip install -e '.[server]'")
        return 2
    load_dotenv()
    settings = Settings.from_env()
    host = args.host or settings.host
    port = args.port or settings.port
    if host not in {"127.0.0.1", "localhost", "::1"}:
        print(
            "warning: listening on a non-loopback address. The API uses bearer tokens and has\n"
            "         no TLS of its own; put it behind an HTTPS reverse proxy.",
            file=sys.stderr,
        )
    uvicorn.run(create_app(settings), host=host, port=port)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    hardware = _hardware(args)
    ok = hardware.probe(force=True)
    print(json.dumps(hardware.status(), indent=2))
    hardware.close()
    return 0 if ok else 1


def cmd_capture(args: argparse.Namespace) -> int:
    hardware = _hardware(args)
    output = Path(args.output)
    if output.exists() and not args.force:
        print(f"error: {output} exists (use --force)")
        return 2
    remaining = args.bytes
    with open(output, "wb") as handle:
        while remaining:
            chunk = hardware.get_bytes(min(4096, remaining))
            handle.write(chunk)
            remaining -= len(chunk)
            print(f"\r{args.bytes - remaining:,} / {args.bytes:,} bytes", end="", file=sys.stderr)
    print(file=sys.stderr)
    hardware.close()
    print(f"wrote {args.bytes:,} health-tested bytes to {output}")
    return 0


def cmd_analyze(args: argparse.Namespace) -> int:
    data = Path(args.file).read_bytes()
    report = stats.analyze(data)
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(stats.format_report(report, args.file))
    return 0


def cmd_encrypt(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.is_file():
        print(f"error: {source} is not a file")
        return 2
    extension = source.suffix.lstrip(".") or "bin"
    # The key is escrowed *before* the ciphertext is written, so a failure can
    # never leave an encrypted file whose key was not stored.
    if args.url:
        client = KeyAuthorityClient(args.url, _remote_token("Master token: "))
        issued = client.request_key()
        key, file_id, provenance = issued["key"], issued["file_id"], issued.get("entropy", {})
        release_token = client.commit(file_id, key, extension)["release_token"]
    else:
        keygen = KeyGenerator(_hardware(args), require_hardware=not args.allow_os_fallback)
        generated = keygen.generate()
        key, provenance = generated.fernet_key, generated.provenance()
        file_id = new_file_id()
        release_token = _vault(args).add(file_id, key, extension)
    target = encrypt_file(key, source, force=args.force)
    print(f"encrypted      : {target}")
    print(f"file ID        : {file_id}")
    print(f"release token  : {release_token}")
    print(f"entropy source : {provenance.get('source', 'unknown')}")
    print("Give the recipient the encrypted file, the file ID and the release token")
    print("over separate channels. The release token is shown only once.")
    return 0


def cmd_decrypt(args: argparse.Namespace) -> int:
    source = Path(args.file)
    if not source.is_file():
        print(f"error: {source} is not a file")
        return 2
    extension: str | None = None
    if args.key_prompt:
        key = validate_key(getpass.getpass("Fernet key: ").strip())
    elif not args.file_id:
        print("error: give --file-id (with --url or a local vault) or --key-prompt")
        return 2
    elif args.url:
        client = KeyAuthorityClient(args.url, _remote_token("Release or master token: "))
        released = client.release(validate_file_id(args.file_id))
        key, extension = released["key"], released.get("extension")
    else:
        entry = _vault(args).get(args.file_id)
        if entry is None:
            print("error: unknown file ID in local vault")
            return 1
        key, extension = entry["key"], entry["extension"]
    target = decrypt_file(
        key,
        source,
        Path(args.output) if args.output else None,
        extension=extension,
        force=args.force,
    )
    print(f"decrypted: {target}")
    return 0


def cmd_vault_list(args: argparse.Namespace) -> int:
    entries = _vault(args).list_metadata()
    if not entries:
        print("vault is empty")
    for file_id, meta in entries.items():
        print(f"{file_id}  .{meta['extension']:<8} {meta['created_at'] or '-'}")
    return 0


def cmd_vault_revoke(args: argparse.Namespace) -> int:
    if _vault(args).remove(args.file_id):
        print(f"revoked {validate_file_id(args.file_id)}")
        return 0
    print("error: unknown file ID")
    return 1


# -- parser ---------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="phyrand", description="PhyRand hardware entropy and key-escrow toolkit."
    )
    parser.add_argument("--version", action="version", version=f"phyrand {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("token", help="print a new random master token")
    p.set_defaults(func=cmd_token)

    p = sub.add_parser("serve", help="run the key-authority API and web client")
    p.add_argument("--host", default=None, help="bind address (default 127.0.0.1)")
    p.add_argument("--port", type=int, default=None, help="TCP port (default 8000)")
    p.set_defaults(func=cmd_serve)

    p = sub.add_parser("status", help="open the board, run the start-up health test, report")
    _add_serial_options(p)
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("capture", help="capture health-tested bytes from the board to a file")
    _add_serial_options(p)
    p.add_argument("-n", "--bytes", type=int, default=1_000_000)
    p.add_argument("-o", "--output", required=True)
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_capture)

    p = sub.add_parser("analyze", help="entropy statistics for a capture (stdlib only)")
    p.add_argument("file")
    p.add_argument("--json", action="store_true")
    p.set_defaults(func=cmd_analyze)

    p = sub.add_parser("encrypt", help="encrypt a file with a freshly generated key")
    p.add_argument("file")
    p.add_argument("--url", default=os.environ.get("PHYRAND_API_URL"), help="key-authority URL")
    p.add_argument(
        "--allow-os-fallback",
        action="store_true",
        help="local mode: if the board is unavailable, use an OS-only key instead of failing",
    )
    p.add_argument("--force", action="store_true", help="overwrite an existing output file")
    _add_serial_options(p)
    _add_vault_option(p)
    p.set_defaults(func=cmd_encrypt)

    p = sub.add_parser("decrypt", help="decrypt a .quantum file")
    p.add_argument("file")
    p.add_argument("--file-id")
    p.add_argument("--url", default=os.environ.get("PHYRAND_API_URL"), help="key-authority URL")
    p.add_argument("--key-prompt", action="store_true", help="type/paste the key (not echoed)")
    p.add_argument("-o", "--output")
    p.add_argument("--force", action="store_true", help="overwrite an existing output file")
    _add_vault_option(p)
    p.set_defaults(func=cmd_decrypt)

    p = sub.add_parser("vault", help="inspect or modify the local vault")
    vault_sub = p.add_subparsers(dest="vault_command", required=True)
    q = vault_sub.add_parser("list", help="list entries (never prints keys)")
    _add_vault_option(q)
    q.set_defaults(func=cmd_vault_list)
    q = vault_sub.add_parser("revoke", help="delete an escrowed key")
    q.add_argument("file_id")
    _add_vault_option(q)
    q.set_defaults(func=cmd_vault_revoke)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    load_dotenv()
    args = build_parser().parse_args(argv)
    try:
        return int(args.func(args))
    except (ConfigError, EntropyError, VaultError, ApiError, DecryptionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
