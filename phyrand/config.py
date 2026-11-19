"""Configuration, loaded from environment variables (optionally via a ``.env`` file)."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

MIN_TOKEN_LENGTH = 32
MIN_TOKEN_DISTINCT_CHARS = 10

_PLACEHOLDER_FRAGMENTS = ("password", "changeme", "change-me", "change_me", "example", "secret")


class ConfigError(Exception):
    """Raised when the configuration is missing or unsafe."""


def check_token_strength(token: str | None) -> str:
    """Return ``token`` if it is acceptable as the master token, else raise.

    The server refuses to start with a missing, short, low-variety or
    placeholder token.  Generate a good one with ``phyrand token``.
    """
    if not token:
        raise ConfigError(
            "VAULT_MASTER_TOKEN is not set. Generate one with `phyrand token` and put it in .env."
        )
    if len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            f"VAULT_MASTER_TOKEN is too short ({len(token)} chars; minimum {MIN_TOKEN_LENGTH})."
        )
    if len(set(token)) < MIN_TOKEN_DISTINCT_CHARS:
        raise ConfigError("VAULT_MASTER_TOKEN has too little variety to be a random token.")
    lowered = token.lower()
    if any(fragment in lowered for fragment in _PLACEHOLDER_FRAGMENTS):
        raise ConfigError("VAULT_MASTER_TOKEN looks like a placeholder; generate a random one.")
    if not token.isascii() or any(ch.isspace() for ch in token):
        raise ConfigError("VAULT_MASTER_TOKEN must be printable ASCII without whitespace.")
    return token


def load_dotenv(
    path: str | os.PathLike[str] = ".env", environ: dict[str, str] | None = None
) -> bool:
    """Minimal ``.env`` reader: ``KEY=VALUE`` lines, ``#`` comments, optional quotes.

    Existing environment variables are never overridden.  Returns whether the
    file existed.
    """
    env = os.environ if environ is None else environ
    file = Path(path)
    if not file.is_file():
        return False
    for raw_line in file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export ") :]
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in env:
            env[key] = value
    return True


def _as_bool(value: str) -> bool:
    lowered = value.strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ConfigError(f"not a boolean: {value!r}")


@dataclass(frozen=True)
class Settings:
    """Runtime settings.  See ``.env.example`` for the corresponding variables."""

    master_token: str = field(repr=False)
    serial_port: str = "/dev/ttyACM0"
    baud_rate: int = 115200
    serial_timeout: float = 5.0
    vault_dir: Path = Path("vault")
    require_hardware: bool = True
    assumed_min_entropy: float = 4.0
    raw_bytes_per_key: int = 128
    host: str = "127.0.0.1"
    port: int = 8000
    cors_origins: tuple[str, ...] = ()
    static_dir: Path | None = None

    @property
    def vault_file(self) -> Path:
        return self.vault_dir / "quantum_vault.json"

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> Settings:
        env = os.environ if environ is None else environ
        try:
            settings = cls(
                master_token=check_token_strength(env.get("VAULT_MASTER_TOKEN")),
                serial_port=env.get("QRNG_SERIAL_PORT", cls.serial_port),
                baud_rate=int(env.get("PHYRAND_BAUD_RATE", cls.baud_rate)),
                serial_timeout=float(env.get("PHYRAND_SERIAL_TIMEOUT", cls.serial_timeout)),
                vault_dir=Path(env.get("PHYRAND_VAULT_DIR", str(cls.vault_dir))),
                require_hardware=_as_bool(env.get("PHYRAND_REQUIRE_HARDWARE", "true")),
                assumed_min_entropy=float(
                    env.get("PHYRAND_ASSUMED_MIN_ENTROPY", cls.assumed_min_entropy)
                ),
                raw_bytes_per_key=int(env.get("PHYRAND_RAW_BYTES_PER_KEY", cls.raw_bytes_per_key)),
                host=env.get("PHYRAND_HOST", cls.host),
                port=int(env.get("PHYRAND_PORT", cls.port)),
                cors_origins=tuple(
                    origin.strip()
                    for origin in env.get("PHYRAND_CORS_ORIGINS", "").split(",")
                    if origin.strip()
                ),
                static_dir=(
                    Path(env["PHYRAND_STATIC_DIR"]) if env.get("PHYRAND_STATIC_DIR") else None
                ),
            )
        except ValueError as exc:
            raise ConfigError(f"invalid numeric setting: {exc}") from exc
        if "*" in settings.cors_origins:
            raise ConfigError("PHYRAND_CORS_ORIGINS must list explicit origins, not '*'.")
        if not 0 < settings.assumed_min_entropy <= 8:
            raise ConfigError("PHYRAND_ASSUMED_MIN_ENTROPY must be in (0, 8] bits per byte.")
        if settings.raw_bytes_per_key < 32:
            raise ConfigError("PHYRAND_RAW_BYTES_PER_KEY must be at least 32.")
        return settings
