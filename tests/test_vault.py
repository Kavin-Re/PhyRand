import base64
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from phyrand import vault as vault_module
from phyrand.vault import (
    DuplicateEntryError,
    ValidationError,
    Vault,
    VaultCorruptError,
    sanitize_extension,
    validate_file_id,
    validate_key,
)

KEY = base64.urlsafe_b64encode(bytes(range(32))).decode()
KEY2 = base64.urlsafe_b64encode(bytes(range(1, 33))).decode()


class ValidationTests(unittest.TestCase):
    def test_file_id(self):
        self.assertEqual(validate_file_id(" ab12cd "), "AB12CD")
        for bad in (
            "",
            "abc",
            "../../etc/passwd",
            "AB12CD<script>",
            "A" * 33,
            "AB 12CD",
            None,
            5,
            "AB12CD\nX",
            "__proto__",
            "ÀB12CD",
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_file_id(bad)

    def test_extension_is_sanitised_not_trusted(self):
        self.assertEqual(sanitize_extension("PDF"), "pdf")
        self.assertEqual(sanitize_extension(".tar"), "tar")
        for bad in (
            "",
            "../x",
            "a/b",
            "exe\x00",
            "<img src=x onerror=alert(1)>",
            "a" * 17,
            None,
            "p df",
            "'onclick='",
        ):
            with self.subTest(bad=bad):
                self.assertEqual(sanitize_extension(bad), "bin")

    def test_key(self):
        self.assertEqual(validate_key(KEY), KEY)
        for bad in (
            "",
            "short",
            KEY[:-1],
            KEY[:-2] + "!=",
            "A" * 44,
            None,
            KEY + "A",
            base64.urlsafe_b64encode(b"x" * 31).decode(),
        ):
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                validate_key(bad)


class VaultTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "vault" / "quantum_vault.json"
        self.vault = Vault(self.path)

    def test_add_get_remove(self):
        token = self.vault.add("ABC123", KEY, "pdf")
        entry = self.vault.get("abc123")
        self.assertEqual(entry["key"], KEY)
        self.assertEqual(entry["extension"], "pdf")
        self.assertTrue(Vault.release_token_matches(entry, token))
        self.assertFalse(Vault.release_token_matches(entry, token + "x"))
        self.assertFalse(Vault.release_token_matches(entry, ""))
        self.assertTrue(self.vault.remove("ABC123"))
        self.assertFalse(self.vault.remove("ABC123"))
        self.assertIsNone(self.vault.get("ABC123"))

    def test_release_token_is_stored_only_as_a_hash(self):
        token = self.vault.add("ABC123", KEY)
        self.assertNotIn(token, self.path.read_text())

    def test_entries_are_never_overwritten(self):
        self.vault.add("ABC123", KEY)
        with self.assertRaises(DuplicateEntryError):
            self.vault.add("ABC123", KEY2)
        self.assertEqual(self.vault.get("ABC123")["key"], KEY)

    def test_listing_contains_no_key_material(self):
        self.vault.add("ABC123", KEY, "txt")
        listing = self.vault.list_metadata()
        self.assertEqual(set(listing["ABC123"]), {"extension", "created_at"})
        self.assertNotIn(KEY, json.dumps(listing))

    @unittest.skipIf(os.name == "nt", "POSIX permissions")
    def test_file_and_directory_are_owner_only(self):
        self.vault.add("ABC123", KEY)
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(self.path.parent.stat().st_mode), 0o700)

    def test_failed_write_keeps_previous_vault_intact(self):
        self.vault.add("ABC123", KEY)
        before = self.path.read_bytes()
        failing_replace = mock.patch.object(
            vault_module.os, "replace", side_effect=OSError("disk full")
        )
        with failing_replace, self.assertRaises(OSError):
            self.vault.add("DEF456", KEY2)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual(
            [p.name for p in self.path.parent.iterdir()], [self.path.name], "temp file cleaned up"
        )

    def test_reads_legacy_formats(self):
        self.path.parent.mkdir(parents=True)
        legacy = {
            "AAA111": {"quantum_key": KEY, "extension": "png", "timestamp": "2026-01-01T00:00:00"},
            "BBB222": {"key": KEY2, "filename": "notes.txt", "timestamp": "Mon Jan  1"},
            "CCC333": {"quantum_key": KEY, "extension": "<b>x</b>"},
        }
        self.path.write_text(json.dumps(legacy))
        self.assertEqual(self.vault.get("AAA111")["key"], KEY)
        self.assertEqual(self.vault.get("AAA111")["extension"], "png")
        self.assertEqual(self.vault.get("BBB222")["key"], KEY2)
        self.assertEqual(self.vault.get("CCC333")["extension"], "bin")
        # First write migrates to the versioned schema.
        self.vault.add("DDD444", KEY)
        on_disk = json.loads(self.path.read_text())
        self.assertEqual(on_disk["version"], 2)
        self.assertEqual(set(on_disk["entries"]), {"AAA111", "BBB222", "CCC333", "DDD444"})

    def test_corrupt_vault_is_an_error_not_an_empty_vault(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ truncated")
        with self.assertRaises(VaultCorruptError):
            self.vault.get("ABC123")
        with self.assertRaises(VaultCorruptError):
            self.vault.add("ABC123", KEY)
        self.assertEqual(self.path.read_text(), "{ truncated")

    def test_invalid_input_is_rejected_before_touching_disk(self):
        with self.assertRaises(ValidationError):
            self.vault.add("../evil", KEY)
        with self.assertRaises(ValidationError):
            self.vault.add("ABC123", "not-a-key")
        self.assertFalse(self.path.exists())


if __name__ == "__main__":
    unittest.main()
