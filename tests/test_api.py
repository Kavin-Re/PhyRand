"""HTTP-level tests for the FastAPI layer.

Skipped automatically when FastAPI/httpx are not installed (they are installed
in CI via ``requirements-dev.txt``).  The same behaviour is covered at the
service level by ``test_service.py`` and over real HTTP by
``test_client_and_cli.py``.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

from .helpers import STRONG_TOKEN, FakeSource, make_keygen

HAVE_FASTAPI = all(importlib.util.find_spec(name) for name in ("fastapi", "httpx"))
AUTH = {"x-api-token": STRONG_TOKEN}


@unittest.skipUnless(HAVE_FASTAPI, "fastapi/httpx not installed")
class ApiTests(unittest.TestCase):
    def setUp(self):
        from fastapi.testclient import TestClient

        from phyrand.api import create_app
        from phyrand.config import Settings
        from phyrand.service import KeyAuthority
        from phyrand.vault import Vault

        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        tmp = Path(self._tmp.name)
        self.source = FakeSource()
        settings = Settings(master_token=STRONG_TOKEN, vault_dir=tmp / "vault")
        authority = KeyAuthority(STRONG_TOKEN, Vault(settings.vault_file), make_keygen(self.source))
        self.client = TestClient(create_app(settings, authority))

    def test_heartbeat_is_public_and_leaks_no_entropy(self):
        response = self.client.get("/heartbeat")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            set(response.json()), {"status", "hardware", "require_hardware", "can_issue_keys"}
        )

    def test_auth_required(self):
        for method, path in (
            ("GET", "/request-keys"),
            ("POST", "/request-keys"),
            ("GET", "/vault/list"),
            ("GET", "/health"),
            ("DELETE", "/vault/revoke/ABC123"),
            ("GET", "/release/ABC123"),
        ):
            with self.subTest(path=path):
                self.assertEqual(self.client.request(method, path).status_code, 401)
        response = self.client.post(
            "/vault/commit", json={"file_id": "ABC123", "key": "k", "extension": "bin"}
        )
        self.assertEqual(response.status_code, 401)

    def test_full_flow(self):
        issued = self.client.post("/request-keys", headers=AUTH).json()
        self.assertEqual(issued["entropy"]["source"], "hardware+os")
        committed = self.client.post(
            "/vault/commit",
            headers=AUTH,
            json={"file_id": issued["file_id"], "key": issued["key"], "extension": "pdf"},
        )
        self.assertEqual(committed.status_code, 200)
        release_token = committed.json()["release_token"]

        listing = self.client.get("/vault/list", headers=AUTH).json()
        self.assertEqual(listing[issued["file_id"]]["extension"], "pdf")
        self.assertNotIn(issued["key"], str(listing))

        released = self.client.get(
            f"/release/{issued['file_id']}", headers={"x-api-token": release_token}
        )
        self.assertEqual(released.json(), {"key": issued["key"], "extension": "pdf"})

        self.assertEqual(
            self.client.delete(f"/vault/revoke/{issued['file_id']}", headers=AUTH).status_code, 200
        )
        self.assertEqual(
            self.client.get(f"/release/{issued['file_id']}", headers=AUTH).status_code, 404
        )

    def test_fail_closed_returns_503(self):
        self.source.mode = "stuck"
        response = self.client.post("/request-keys", headers=AUTH)
        self.assertEqual(response.status_code, 503)
        self.assertIn("refusing", response.json()["detail"])

    def test_commit_without_pending_key_conflicts(self):
        response = self.client.post(
            "/vault/commit",
            headers=AUTH,
            json={"file_id": "ABC123", "key": "A" * 43 + "=", "extension": "bin"},
        )
        self.assertEqual(response.status_code, 409)

    def test_security_headers(self):
        for path in ("/heartbeat", "/"):
            response = self.client.get(path)
            self.assertEqual(response.headers["cache-control"], "no-store")
            self.assertEqual(response.headers["x-content-type-options"], "nosniff")
            self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertNotIn("access-control-allow-origin", self.client.get("/heartbeat").headers)

    def test_static_client_is_served_and_cannot_shadow_api(self):
        self.assertIn("PhyRand", self.client.get("/").text)
        self.assertEqual(self.client.get("/app.js").status_code, 200)
        self.assertEqual(self.client.get("/../.env").status_code, 404)

    def test_refuses_to_start_with_default_token(self):
        from phyrand.config import ConfigError, Settings

        with self.assertRaises(ConfigError):
            Settings.from_env({"VAULT_MASTER_TOKEN": "password"})


if __name__ == "__main__":
    unittest.main()
