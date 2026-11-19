"""FastAPI transport for the key authority.

Run with ``phyrand serve`` (or ``python api/qrng_api.py``).  All logic lives in
:mod:`phyrand.service`; this module maps HTTP onto it and adds response
hardening (no caching of key material, a strict Content-Security-Policy for
the bundled web client, no wildcard CORS).

Endpoints are plain ``def`` functions on purpose: FastAPI runs them in a
thread pool, so a blocking serial read cannot stall the event loop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import __version__
from .config import Settings, load_dotenv
from .entropy import HardwareEntropy, KeyGenerator, SerialSource
from .health import HealthMonitor
from .service import KeyAuthority, ServiceError
from .vault import Vault

REPO_STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": (
        "default-src 'self'; object-src 'none'; base-uri 'none'; "
        "frame-ancestors 'none'; form-action 'none'"
    ),
}


class CommitRequest(BaseModel):
    file_id: str = Field(max_length=64)
    key: str = Field(max_length=64)
    extension: str = Field(default="bin", max_length=64)


def build_authority(settings: Settings) -> KeyAuthority:
    """Wire the serial source, health monitor, key generator and vault together."""
    hardware = HardwareEntropy(
        SerialSource(settings.serial_port, settings.baud_rate, settings.serial_timeout),
        HealthMonitor(min_entropy=settings.assumed_min_entropy),
    )
    keygen = KeyGenerator(
        hardware,
        require_hardware=settings.require_hardware,
        raw_bytes_per_key=settings.raw_bytes_per_key,
    )
    return KeyAuthority(settings.master_token, Vault(settings.vault_file), keygen)


def _client_id(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def create_app(settings: Settings | None = None, authority: KeyAuthority | None = None) -> FastAPI:
    """Application factory.  Raises :class:`ConfigError` on unsafe configuration."""
    if settings is None:
        load_dotenv()
        settings = Settings.from_env()
    if authority is None:
        authority = build_authority(settings)

    app = FastAPI(
        title="PhyRand Key Authority",
        version=__version__,
        docs_url=None,  # the interactive docs pull scripts from a CDN; keep the CSP strict
        redoc_url=None,
    )

    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=list(settings.cors_origins),
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["x-api-token", "content-type"],
            allow_credentials=False,
        )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next: Any) -> Any:
        response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        return response

    @app.exception_handler(ServiceError)
    async def service_error_handler(_request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status, content={"detail": str(exc)})

    @app.get("/heartbeat")
    def heartbeat() -> dict[str, Any]:
        return authority.status()

    @app.get("/health")
    def health(request: Request, x_api_token: str | None = Header(default=None)) -> dict[str, Any]:
        return authority.health(x_api_token, _client_id(request))

    # GET is kept for backwards compatibility with the original client.
    @app.api_route("/request-keys", methods=["POST", "GET"])
    def request_keys(
        request: Request, x_api_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return authority.request_key(x_api_token, _client_id(request))

    @app.post("/vault/commit")
    def commit(
        data: CommitRequest, request: Request, x_api_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return authority.commit(
            x_api_token, data.file_id, data.key, data.extension, _client_id(request)
        )

    @app.get("/vault/list")
    def list_vault(
        request: Request, x_api_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return authority.list_entries(x_api_token, _client_id(request))

    @app.delete("/vault/revoke/{file_id}")
    def revoke(
        file_id: str, request: Request, x_api_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return authority.revoke(x_api_token, file_id, _client_id(request))

    @app.get("/release/{file_id}")
    def release(
        file_id: str, request: Request, x_api_token: str | None = Header(default=None)
    ) -> dict[str, Any]:
        return authority.release(x_api_token, file_id, _client_id(request))

    static_dir = settings.static_dir or REPO_STATIC_DIR
    if static_dir.is_dir():
        # Mounted last so it can never shadow an API route.
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    else:

        @app.get("/")
        def no_static() -> None:
            raise HTTPException(status_code=404, detail="web client not installed")

    return app
