"""Standard-library HTTP front end for :class:`KeyAuthority`, used only by tests.

It mirrors the routes of ``phyrand/api.py`` so the HTTP client and the service
layer can be exercised end to end on machines where FastAPI is not installed.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from phyrand.service import KeyAuthority, ServiceError


def serve(authority: KeyAuthority) -> tuple[ThreadingHTTPServer, str]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):  # keep test output quiet
            pass

        def _reply(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _dispatch(self, method: str) -> None:
            token = self.headers.get("x-api-token")
            path = self.path
            try:
                if path == "/heartbeat":
                    result = authority.status()
                elif path == "/request-keys":
                    result = authority.request_key(token)
                elif path == "/vault/list":
                    result = authority.list_entries(token)
                elif path == "/vault/commit" and method == "POST":
                    length = int(self.headers.get("Content-Length", "0"))
                    data = json.loads(self.rfile.read(length))
                    result = authority.commit(
                        token, data["file_id"], data["key"], data["extension"]
                    )
                elif path.startswith("/release/"):
                    result = authority.release(token, path.split("/", 2)[2])
                elif path.startswith("/vault/revoke/") and method == "DELETE":
                    result = authority.revoke(token, path.split("/", 3)[3])
                else:
                    return self._reply(404, {"detail": "not found"})
            except ServiceError as exc:
                return self._reply(exc.status, {"detail": str(exc)})
            self._reply(200, result)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            self._dispatch("POST")

        def do_DELETE(self):
            self._dispatch("DELETE")

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_address[1]}"
