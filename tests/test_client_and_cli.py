import contextlib
import importlib.util
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phyrand import cli
from phyrand.client import ApiError, KeyAuthorityClient
from phyrand.service import KeyAuthority
from phyrand.vault import Vault

from .helpers import CAPTURE, STRONG_TOKEN, FakeSource, make_keygen
from .stub_server import serve

HAVE_CRYPTOGRAPHY = importlib.util.find_spec("cryptography") is not None


def run_cli(*argv: str) -> tuple[int, str]:
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)
        # Keep the developer's real environment and .env out of the tests.
        patcher = mock.patch.dict(os.environ, {}, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        cwd = os.getcwd()
        os.chdir(self.tmp)
        self.addCleanup(os.chdir, cwd)


def field(output: str, name: str) -> str:
    """Extract ``value`` from a ``name   : value`` line of CLI output."""
    return next(
        line.split(":", 1)[1].strip() for line in output.splitlines() if line.startswith(name)
    )


class ClientTests(TempDirTestCase):
    def setUp(self):
        super().setUp()
        authority = KeyAuthority(
            STRONG_TOKEN,
            Vault(self.tmp / "vault" / "quantum_vault.json"),
            make_keygen(FakeSource()),
        )
        self.server, self.url = serve(authority)
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)

    def test_full_flow_over_http(self):
        client = KeyAuthorityClient(self.url, STRONG_TOKEN)
        self.assertEqual(client.heartbeat()["status"], "ONLINE")
        issued = client.request_key()
        committed = client.commit(issued["file_id"], issued["key"], "txt")
        self.assertIn(issued["file_id"], client.list_entries())

        recipient = KeyAuthorityClient(self.url, committed["release_token"])
        self.assertEqual(recipient.release(issued["file_id"])["key"], issued["key"])
        with self.assertRaises(ApiError) as ctx:
            recipient.list_entries()
        self.assertEqual(ctx.exception.status, 401)

        client.revoke(issued["file_id"])
        with self.assertRaises(ApiError) as ctx:
            recipient.release(issued["file_id"])
        self.assertEqual(ctx.exception.status, 401)

    def test_wrong_token(self):
        with self.assertRaises(ApiError) as ctx:
            KeyAuthorityClient(self.url, "wrong").request_key()
        self.assertEqual(ctx.exception.status, 401)

    def test_refuses_plain_http_to_remote_hosts(self):
        with self.assertRaises(ValueError):
            KeyAuthorityClient("http://vault.example.com", STRONG_TOKEN)
        with self.assertRaises(ValueError):
            KeyAuthorityClient("ftp://localhost", STRONG_TOKEN)
        KeyAuthorityClient("https://vault.example.com", STRONG_TOKEN)

    def test_unreachable_server(self):
        self.server.shutdown()
        self.server.server_close()
        with self.assertRaises(ApiError):
            KeyAuthorityClient(self.url, STRONG_TOKEN, timeout=2).heartbeat()

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography not installed")
    def test_cli_remote_encrypt_then_decrypt_with_release_token(self):
        secret = self.tmp / "report.txt"
        secret.write_bytes(b"attack at dawn\n" * 100)
        os.environ["VAULT_MASTER_TOKEN"] = STRONG_TOKEN
        code, out = run_cli("encrypt", str(secret), "--url", self.url)
        self.assertEqual(code, 0, out)
        file_id = field(out, "file ID")
        release_token = field(out, "release token")
        self.assertIn("hardware+os", out)

        encrypted = self.tmp / "report.txt.quantum"
        self.assertNotIn(b"attack", encrypted.read_bytes())
        secret.unlink()

        del os.environ["VAULT_MASTER_TOKEN"]
        os.environ["PHYRAND_RELEASE_TOKEN"] = release_token
        code, out = run_cli("decrypt", str(encrypted), "--file-id", file_id, "--url", self.url)
        self.assertEqual(code, 0, out)
        self.assertEqual(secret.read_bytes(), b"attack at dawn\n" * 100)


class CliTests(TempDirTestCase):
    def test_token_command_produces_acceptable_tokens(self):
        from phyrand.config import check_token_strength

        code, out = run_cli("token")
        self.assertEqual(code, 0)
        check_token_strength(out.strip())

    @unittest.skipUnless(CAPTURE.is_file(), "sample capture not present")
    def test_analyze(self):
        code, out = run_cli("analyze", str(CAPTURE), "--json")
        self.assertEqual(code, 0)
        self.assertAlmostEqual(json.loads(out)["shannon_entropy_bits_per_byte"], 7.99976, places=5)

    def test_status_without_hardware_exits_nonzero(self):
        code, out = run_cli("status", "--port", str(self.tmp / "no-such-port"), "--timeout", "0.2")
        self.assertEqual(code, 1)
        self.assertEqual(json.loads(out)["state"], "unavailable")

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography not installed")
    def test_local_encrypt_fails_closed_without_hardware(self):
        target = self.tmp / "a.txt"
        target.write_text("data")
        code, out = run_cli("encrypt", str(target), "--port", str(self.tmp / "nope"))
        self.assertEqual(code, 1)
        self.assertIn("error", out)
        self.assertFalse((self.tmp / "a.txt.quantum").exists())
        self.assertFalse((self.tmp / "vault").exists())

    @unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography not installed")
    def test_local_fallback_round_trip_and_vault_commands(self):
        target = self.tmp / "photo.png"
        payload = bytes(range(256)) * 20
        target.write_bytes(payload)
        code, out = run_cli(
            "encrypt", str(target), "--allow-os-fallback", "--port", str(self.tmp / "nope")
        )
        self.assertEqual(code, 0, out)
        self.assertIn("os-only", out)
        file_id = field(out, "file ID")

        code, out = run_cli("vault", "list")
        self.assertIn(file_id, out)
        self.assertIn(".png", out)

        encrypted = self.tmp / "photo.png.quantum"
        code, out = run_cli("decrypt", str(encrypted), "--file-id", file_id)
        self.assertEqual(code, 1, "refuses to overwrite the original")
        restored = self.tmp / "restored.png"
        code, out = run_cli("decrypt", str(encrypted), "--file-id", file_id, "-o", str(restored))
        self.assertEqual(code, 0, out)
        self.assertEqual(restored.read_bytes(), payload)

        # Tampering is detected.
        blob = bytearray(encrypted.read_bytes())
        blob[40] = ord("B") if blob[40] == ord("A") else ord("A")
        encrypted.write_bytes(blob)
        code, out = run_cli(
            "decrypt", str(encrypted), "--file-id", file_id, "-o", str(self.tmp / "t.png")
        )
        self.assertEqual(code, 1)
        self.assertIn("authentication failed", out)

        self.assertEqual(run_cli("vault", "revoke", file_id)[0], 0)
        self.assertEqual(run_cli("decrypt", str(encrypted), "--file-id", file_id)[0], 1)


@unittest.skipUnless(HAVE_CRYPTOGRAPHY, "cryptography not installed")
class FileCryptTests(TempDirTestCase):
    def test_paths(self):
        from phyrand.filecrypt import decrypted_path, encrypted_path

        self.assertEqual(encrypted_path(Path("a/b.txt")), Path("a/b.txt.quantum"))
        self.assertEqual(decrypted_path(Path("a/b.txt.quantum")), Path("a/b.txt"))
        self.assertEqual(
            decrypted_path(Path("x.quantum.d/b.quantum"), "pdf"), Path("x.quantum.d/b.pdf")
        )
        self.assertEqual(decrypted_path(Path("blob")), Path("blob.decrypted"))
        self.assertEqual(decrypted_path(Path(".quantum")), Path(".quantum.decrypted"))

    def test_interoperates_with_reference_fernet(self):
        from cryptography.fernet import Fernet

        from phyrand.filecrypt import DecryptionError, decrypt_bytes, encrypt_bytes

        key = make_keygen(FakeSource()).generate().fernet_key
        token = encrypt_bytes(key, b"hello")
        self.assertEqual(Fernet(key).decrypt(token), b"hello")
        self.assertEqual(decrypt_bytes(key, token + b"\n"), b"hello")
        other = make_keygen(FakeSource()).generate().fernet_key
        with self.assertRaises(DecryptionError):
            decrypt_bytes(other, token)

    def test_decrypted_files_are_private(self):
        from phyrand.filecrypt import decrypt_file, encrypt_file

        key = make_keygen(FakeSource()).generate().fernet_key
        source = self.tmp / "s.txt"
        source.write_text("x")
        encrypted = encrypt_file(key, source)
        with self.assertRaises(FileExistsError):
            encrypt_file(key, source)
        target = decrypt_file(key, encrypted, self.tmp / "out.txt")
        if os.name != "nt":
            self.assertEqual(target.stat().st_mode & 0o077, 0)


if __name__ == "__main__":
    unittest.main()
