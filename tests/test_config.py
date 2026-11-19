import tempfile
import unittest
from pathlib import Path

from phyrand.config import ConfigError, Settings, check_token_strength, load_dotenv

from .helpers import STRONG_TOKEN


class TokenStrengthTests(unittest.TestCase):
    def test_strong_token_accepted(self):
        self.assertEqual(check_token_strength(STRONG_TOKEN), STRONG_TOKEN)

    def test_weak_tokens_rejected(self):
        weak = [
            None,
            "",
            "password",  # the old built-in default
            "hunter2",
            "a" * 64,
            "abcabcabcabcabcabcabcabcabcabcabcabc",
            "my-super-long-password-0123456789-abcdef",
            "CHANGE-ME-0123456789abcdefghijklmnopqrstuv",
            "token with spaces 0123456789abcdefghijk",
        ]
        for token in weak:
            with self.subTest(token=token), self.assertRaises(ConfigError):
                check_token_strength(token)


class SettingsTests(unittest.TestCase):
    def test_refuses_to_load_without_token(self):
        with self.assertRaises(ConfigError):
            Settings.from_env({})
        with self.assertRaises(ConfigError):
            Settings.from_env({"VAULT_MASTER_TOKEN": "password"})

    def test_safe_defaults(self):
        settings = Settings.from_env({"VAULT_MASTER_TOKEN": STRONG_TOKEN})
        self.assertEqual(settings.host, "127.0.0.1")
        self.assertTrue(settings.require_hardware)
        self.assertEqual(settings.cors_origins, ())
        self.assertEqual(settings.vault_file, Path("vault") / "quantum_vault.json")
        self.assertNotIn(STRONG_TOKEN, repr(settings))

    def test_overrides(self):
        settings = Settings.from_env(
            {
                "VAULT_MASTER_TOKEN": STRONG_TOKEN,
                "QRNG_SERIAL_PORT": "/dev/ttyACM3",
                "PHYRAND_REQUIRE_HARDWARE": "false",
                "PHYRAND_ASSUMED_MIN_ENTROPY": "6",
                "PHYRAND_CORS_ORIGINS": "https://a.example, https://b.example",
                "PHYRAND_PORT": "9000",
            }
        )
        self.assertEqual(settings.serial_port, "/dev/ttyACM3")
        self.assertFalse(settings.require_hardware)
        self.assertEqual(settings.assumed_min_entropy, 6.0)
        self.assertEqual(settings.cors_origins, ("https://a.example", "https://b.example"))
        self.assertEqual(settings.port, 9000)

    def test_invalid_values(self):
        base = {"VAULT_MASTER_TOKEN": STRONG_TOKEN}
        for extra in (
            {"PHYRAND_CORS_ORIGINS": "*"},
            {"PHYRAND_REQUIRE_HARDWARE": "maybe"},
            {"PHYRAND_PORT": "eighty"},
            {"PHYRAND_ASSUMED_MIN_ENTROPY": "12"},
            {"PHYRAND_RAW_BYTES_PER_KEY": "4"},
        ):
            with self.subTest(extra=extra), self.assertRaises(ConfigError):
                Settings.from_env({**base, **extra})


class DotenvTests(unittest.TestCase):
    def test_parses_and_does_not_override(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / ".env"
            path.write_text(
                "# comment\n\nA=1\nexport B = 'two words'\nC=\"x=y\"\nEXISTING=new\nnot a line\n"
            )
            env = {"EXISTING": "old"}
            self.assertTrue(load_dotenv(path, env))
            self.assertEqual(env, {"EXISTING": "old", "A": "1", "B": "two words", "C": "x=y"})
            self.assertFalse(load_dotenv(Path(tmp) / "missing", env))


if __name__ == "__main__":
    unittest.main()
