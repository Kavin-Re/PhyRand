import json
import tempfile
import unittest
from pathlib import Path

from phyrand.entropy import KeyGenerator
from phyrand.service import (
    AuthError,
    BadRequestError,
    ConflictError,
    EntropyUnavailableError,
    FailureLimiter,
    KeyAuthority,
    NotFoundError,
    RateLimitedError,
    tokens_equal,
)
from phyrand.vault import Vault

from .helpers import STRONG_TOKEN, FakeClock, FakeSource, make_keygen


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.vault_path = Path(self._tmp.name) / "vault.json"
        self.clock = FakeClock()
        self.source = FakeSource()
        self.authority = self.make_authority(make_keygen(self.source))

    def make_authority(self, keygen: KeyGenerator) -> KeyAuthority:
        return KeyAuthority(STRONG_TOKEN, Vault(self.vault_path), keygen, clock=self.clock)

    def issue_and_commit(self, extension="pdf"):
        issued = self.authority.request_key(STRONG_TOKEN)
        committed = self.authority.commit(STRONG_TOKEN, issued["file_id"], issued["key"], extension)
        return issued, committed


class TokenComparisonTests(unittest.TestCase):
    def test_tokens_equal(self):
        self.assertTrue(tokens_equal(STRONG_TOKEN, STRONG_TOKEN))
        for wrong in (None, "", STRONG_TOKEN[:-1], STRONG_TOKEN + "x", "pässword", "\udcff"):
            self.assertFalse(tokens_equal(wrong, STRONG_TOKEN))


class AuthenticationTests(ServiceTestCase):
    def test_every_privileged_operation_requires_the_master_token(self):
        calls = [
            lambda t: self.authority.request_key(t),
            lambda t: self.authority.commit(t, "ABC123", "k", "bin"),
            lambda t: self.authority.list_entries(t),
            lambda t: self.authority.revoke(t, "ABC123"),
            lambda t: self.authority.health(t),
        ]
        for index, call in enumerate(calls):
            for token in (None, "", "password", STRONG_TOKEN[:-1]):
                with self.subTest(call=index, token=token), self.assertRaises(AuthError):
                    call(token)
                self.clock.advance(120)  # stay clear of the rate limiter

    def test_repeated_failures_are_rate_limited_per_client(self):
        for _ in range(10):
            with self.assertRaises(AuthError):
                self.authority.list_entries("wrong", client="10.0.0.9")
        with self.assertRaises(RateLimitedError):
            self.authority.list_entries("wrong", client="10.0.0.9")
        # Even the right token is refused while that client is locked out ...
        with self.assertRaises(RateLimitedError):
            self.authority.list_entries(STRONG_TOKEN, client="10.0.0.9")
        # ... other clients are unaffected, and the lock-out expires.
        self.assertEqual(self.authority.list_entries(STRONG_TOKEN, client="10.0.0.7"), {})
        self.clock.advance(61)
        self.assertEqual(self.authority.list_entries(STRONG_TOKEN, client="10.0.0.9"), {})

    def test_limiter_memory_is_bounded(self):
        limiter = FailureLimiter(clock=self.clock)
        for i in range(5000):
            limiter.record_failure(f"client-{i}")
        self.assertLessEqual(len(limiter._failures), 4096)


class KeyLifecycleTests(ServiceTestCase):
    def test_request_commit_release_revoke(self):
        issued, committed = self.issue_and_commit()
        self.assertEqual(issued["entropy"]["source"], "hardware+os")
        self.assertEqual(committed["status"], "committed")
        release_token = committed["release_token"]

        released = self.authority.release(release_token, issued["file_id"])
        self.assertEqual(released, {"key": issued["key"], "extension": "pdf"})
        self.assertEqual(self.authority.release(STRONG_TOKEN, issued["file_id"]), released)

        self.assertEqual(
            self.authority.revoke(STRONG_TOKEN, issued["file_id"])["status"], "revoked"
        )
        with self.assertRaises(AuthError):
            self.authority.release(release_token, issued["file_id"])
        with self.assertRaises(NotFoundError):
            self.authority.release(STRONG_TOKEN, issued["file_id"])
        with self.assertRaises(NotFoundError):
            self.authority.revoke(STRONG_TOKEN, issued["file_id"])

    def test_key_is_not_stored_until_committed(self):
        self.authority.request_key(STRONG_TOKEN)
        self.assertFalse(self.vault_path.exists())

    def test_release_token_only_opens_its_own_file(self):
        first, first_commit = self.issue_and_commit()
        second, _ = self.issue_and_commit()
        with self.assertRaises(AuthError):
            self.authority.release(first_commit["release_token"], second["file_id"])
        # ... and grants no administrative access.
        with self.assertRaises(AuthError):
            self.authority.list_entries(first_commit["release_token"])

    def test_unknown_id_is_indistinguishable_from_bad_token(self):
        issued, _ = self.issue_and_commit()
        with self.assertRaises(AuthError) as missing:
            self.authority.release("some-guess", "ZZZZZZ")
        with self.assertRaises(AuthError) as wrong:
            self.authority.release("some-guess", issued["file_id"])
        self.assertEqual(str(missing.exception), str(wrong.exception))

    def test_listing_never_contains_keys(self):
        issued, committed = self.issue_and_commit("txt")
        listing = self.authority.list_entries(STRONG_TOKEN)
        self.assertEqual(list(listing), [issued["file_id"]])
        dumped = json.dumps(listing)
        self.assertNotIn(issued["key"], dumped)
        self.assertNotIn(committed["release_token"], dumped)

    def test_commit_requires_a_matching_pending_key(self):
        issued = self.authority.request_key(STRONG_TOKEN)
        other = self.authority.request_key(STRONG_TOKEN)
        with self.assertRaises(ConflictError):  # never issued
            self.authority.commit(STRONG_TOKEN, "ABCDEF", issued["key"], "bin")
        with self.assertRaises(ConflictError):  # key swapped
            self.authority.commit(STRONG_TOKEN, issued["file_id"], other["key"], "bin")
        self.authority.commit(STRONG_TOKEN, issued["file_id"], issued["key"], "bin")
        with self.assertRaises(ConflictError):  # replay / overwrite
            self.authority.commit(STRONG_TOKEN, issued["file_id"], issued["key"], "bin")

    def test_pending_keys_expire(self):
        issued = self.authority.request_key(STRONG_TOKEN)
        self.clock.advance(601)
        with self.assertRaises(ConflictError):
            self.authority.commit(STRONG_TOKEN, issued["file_id"], issued["key"], "bin")

    def test_malformed_input_is_rejected(self):
        issued = self.authority.request_key(STRONG_TOKEN)
        with self.assertRaises(BadRequestError):
            self.authority.commit(STRONG_TOKEN, "../../x", issued["key"], "bin")
        with self.assertRaises(BadRequestError):
            self.authority.commit(STRONG_TOKEN, issued["file_id"], "not-a-key", "bin")
        with self.assertRaises(BadRequestError):
            self.authority.release(STRONG_TOKEN, "<script>")
        with self.assertRaises(BadRequestError):
            self.authority.revoke(STRONG_TOKEN, "a/b")

    def test_hostile_extension_is_neutralised(self):
        issued = self.authority.request_key(STRONG_TOKEN)
        self.authority.commit(
            STRONG_TOKEN, issued["file_id"], issued["key"], '"><img src=x onerror=alert(1)>'
        )
        self.assertEqual(
            self.authority.release(STRONG_TOKEN, issued["file_id"])["extension"], "bin"
        )


class EntropyPolicyTests(ServiceTestCase):
    def test_fail_closed_when_hardware_is_missing_or_unhealthy(self):
        for mode in ("timeout", "error", "stuck", "biased"):
            with self.subTest(mode=mode):
                authority = self.make_authority(make_keygen(FakeSource(mode)))
                with self.assertRaises(EntropyUnavailableError) as ctx:
                    authority.request_key(STRONG_TOKEN)
                self.assertEqual(ctx.exception.status, 503)
                status = authority.status()
                self.assertEqual(status["status"], "OFFLINE")
                self.assertFalse(status["can_issue_keys"])

    def test_opt_in_fallback_is_reported_to_the_caller(self):
        authority = self.make_authority(make_keygen(FakeSource("timeout"), require_hardware=False))
        issued = authority.request_key(STRONG_TOKEN)
        self.assertEqual(issued["entropy"]["source"], "os-only")
        self.assertEqual(authority.status()["status"], "DEGRADED")

    def test_status_is_public_but_carries_no_secrets(self):
        self.issue_and_commit()
        status = self.authority.status()
        self.assertEqual(
            status,
            {
                "status": "ONLINE",
                "hardware": "ok",
                "require_hardware": True,
                "can_issue_keys": True,
            },
        )

    def test_health_report(self):
        report = self.authority.health(STRONG_TOKEN)
        tests = report["entropy"]["health_tests"]
        self.assertEqual(tests["rct_cutoff"], 6)
        self.assertEqual(tests["apt_cutoff"], 62)
        self.assertEqual(report["raw_bytes_per_key"], 128)

    def test_source_recovers_without_restart(self):
        self.source.mode = "stuck"
        with self.assertRaises(EntropyUnavailableError):
            self.authority.request_key(STRONG_TOKEN)
        self.source.mode = "random"
        self.assertEqual(
            self.authority.request_key(STRONG_TOKEN)["entropy"]["source"], "hardware+os"
        )


if __name__ == "__main__":
    unittest.main()
