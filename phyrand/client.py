"""Tiny HTTP client for the key authority (standard library only)."""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from .vault import validate_file_id


class ApiError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(f"HTTP {status}: {detail}")
        self.status = status
        self.detail = detail


class KeyAuthorityClient:
    """Talks to a PhyRand server.  Plain ``http://`` is only allowed for loopback."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 15.0) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("base URL must be http(s)://host[:port]")
        if parsed.scheme == "http" and parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError(
                "refusing to send a bearer token over plain HTTP to a non-loopback host; use https"
            )
        self._base = base_url.rstrip("/")
        self._token = token
        self._timeout = timeout

    def _call(self, method: str, path: str, body: dict[str, Any] | None = None) -> Any:
        data = json.dumps(body).encode("utf-8") if body is not None else None
        request = urllib.request.Request(self._base + path, data=data, method=method)  # noqa: S310
        request.add_header("x-api-token", self._token)
        request.add_header("Accept", "application/json")
        if data is not None:
            request.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as response:  # noqa: S310
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            try:
                detail = json.loads(exc.read().decode("utf-8")).get("detail", exc.reason)
            except (ValueError, AttributeError):
                detail = exc.reason
            raise ApiError(exc.code, str(detail)) from exc
        except urllib.error.URLError as exc:
            raise ApiError(0, f"cannot reach {self._base}: {exc.reason}") from exc

    def heartbeat(self) -> Any:
        return self._call("GET", "/heartbeat")

    def request_key(self) -> Any:
        return self._call("POST", "/request-keys")

    def commit(self, file_id: str, key: str, extension: str) -> Any:
        return self._call(
            "POST", "/vault/commit", {"file_id": file_id, "key": key, "extension": extension}
        )

    def release(self, file_id: str) -> Any:
        return self._call("GET", f"/release/{validate_file_id(file_id)}")

    def revoke(self, file_id: str) -> Any:
        return self._call("DELETE", f"/vault/revoke/{validate_file_id(file_id)}")

    def list_entries(self) -> Any:
        return self._call("GET", "/vault/list")
