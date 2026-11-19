import base64
import sys
import types
import unittest
from unittest import mock

from phyrand.entropy import (
    STATE_HEALTH_FAILURE,
    STATE_NOT_STARTED,
    STATE_OK,
    STATE_UNAVAILABLE,
    HardwareEntropy,
    KeyGenerator,
    SerialSource,
    SourceHealthError,
    SourceUnavailableError,
)
from phyrand.health import STARTUP_SAMPLES

from .helpers import FakeClock, FakeSource, make_hardware, make_keygen


class HardwareEntropyTests(unittest.TestCase):
    def test_startup_test_runs_once_and_is_discarded(self):
        source = FakeSource()
        hardware = make_hardware(source)
        self.assertEqual(hardware.state, STATE_NOT_STARTED)
        data = hardware.get_bytes(64)
        self.assertEqual(len(data), 64)
        self.assertEqual(source.bytes_read, STARTUP_SAMPLES + 64)
        hardware.get_bytes(64)
        self.assertEqual(source.bytes_read, STARTUP_SAMPLES + 128)
        self.assertEqual(hardware.state, STATE_OK)
        self.assertEqual(hardware.status()["bytes_delivered"], 128)

    def test_startup_must_cover_1024_samples(self):
        with self.assertRaises(ValueError):
            HardwareEntropy(FakeSource(), startup_samples=100)

    def test_stuck_source_fails_startup(self):
        hardware = make_hardware(FakeSource("stuck"))
        with self.assertRaises(SourceHealthError):
            hardware.get_bytes(32)
        self.assertEqual(hardware.state, STATE_HEALTH_FAILURE)
        self.assertIn("repetition_count", hardware.status()["last_error"])

    def test_biased_source_fails(self):
        hardware = make_hardware(FakeSource("biased"))
        with self.assertRaises(SourceHealthError) as ctx:
            hardware.get_bytes(32)
        self.assertIn("adaptive_proportion", str(ctx.exception))

    def test_failure_after_startup_discards_batch_and_forces_restart(self):
        source = FakeSource()
        hardware = make_hardware(source)
        hardware.get_bytes(32)
        source.mode = "stuck"
        with self.assertRaises(SourceHealthError):
            hardware.get_bytes(32)
        self.assertEqual(hardware.state, STATE_HEALTH_FAILURE)
        self.assertGreaterEqual(source.close_calls, 1)
        # Source recovers: a complete new start-up test is required first.
        source.mode = "random"
        before = source.bytes_read
        hardware.get_bytes(32)
        self.assertEqual(source.bytes_read - before, STARTUP_SAMPLES + 32)
        self.assertEqual(hardware.status()["startup_tests_passed"], 2)

    def test_timeout_and_open_error_report_unavailable(self):
        for mode in ("timeout", "error"):
            with self.subTest(mode=mode):
                hardware = make_hardware(FakeSource(mode))
                with self.assertRaises(SourceUnavailableError):
                    hardware.get_bytes(32)
                self.assertEqual(hardware.state, STATE_UNAVAILABLE)

    def test_short_reads_are_reassembled(self):
        class Dribble(FakeSource):
            def read(self, n):
                return super().read(min(n, 7))

        self.assertEqual(len(make_hardware(Dribble()).get_bytes(100)), 100)

    def test_probe_never_raises_and_is_rate_limited(self):
        clock = FakeClock()
        source = FakeSource("timeout")
        hardware = make_hardware(source, clock)
        self.assertFalse(hardware.probe())
        source.mode = "random"
        self.assertFalse(hardware.probe(), "second attempt inside retry interval is skipped")
        self.assertEqual(source.bytes_read, 0)
        clock.advance(11)
        self.assertTrue(hardware.probe())
        self.assertEqual(hardware.state, STATE_OK)

    def test_status_contains_no_entropy(self):
        hardware = make_hardware(FakeSource())
        data = hardware.get_bytes(64)
        self.assertNotIn(data.hex(), repr(hardware.status()))

    def test_invalid_request(self):
        with self.assertRaises(ValueError):
            make_hardware(FakeSource()).get_bytes(0)


class FakeSerialPort:
    """Minimal stand-in for ``serial.Serial``."""

    instances: list["FakeSerialPort"] = []
    fail_open = False

    def __init__(self, port, baudrate, timeout=None):
        if FakeSerialPort.fail_open:
            raise OSError(2, "No such file or directory", port)
        self.args = (port, baudrate, timeout)
        self.flushed = False
        self.closed = False
        self.fail_read = False
        FakeSerialPort.instances.append(self)

    def reset_input_buffer(self):
        self.flushed = True

    def read(self, n):
        if self.fail_read:
            raise OSError("device disconnected")
        return bytearray(b"\x5a" * n)

    def close(self):
        self.closed = True


class SerialSourceTests(unittest.TestCase):
    def setUp(self):
        FakeSerialPort.instances = []
        FakeSerialPort.fail_open = False
        fake_module = types.SimpleNamespace(Serial=FakeSerialPort)
        patcher = mock.patch.dict(sys.modules, {"serial": fake_module})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_port_is_opened_lazily_once_and_flushed(self):
        source = SerialSource("/dev/ttyFAKE", 115200, timeout=1.5)
        self.assertEqual(FakeSerialPort.instances, [])
        self.assertEqual(source.read(4), b"\x5a" * 4)
        self.assertIsInstance(source.read(4), bytes)
        self.assertEqual(len(FakeSerialPort.instances), 1, "port must not be reopened per read")
        port = FakeSerialPort.instances[0]
        self.assertEqual(port.args, ("/dev/ttyFAKE", 115200, 1.5))
        self.assertTrue(port.flushed)

    def test_open_failure_is_reported_as_unavailable(self):
        FakeSerialPort.fail_open = True
        with self.assertRaises(SourceUnavailableError):
            SerialSource("/dev/ttyFAKE").read(1)

    def test_read_error_closes_and_next_read_reopens(self):
        source = SerialSource("/dev/ttyFAKE")
        source.read(1)
        FakeSerialPort.instances[0].fail_read = True
        with self.assertRaises(SourceUnavailableError):
            source.read(1)
        self.assertTrue(FakeSerialPort.instances[0].closed)
        self.assertEqual(source.read(2), b"\x5a\x5a")
        self.assertEqual(len(FakeSerialPort.instances), 2)

    def test_close_is_idempotent(self):
        source = SerialSource("/dev/ttyFAKE")
        source.close()
        source.read(1)
        source.close()
        source.close()
        self.assertTrue(FakeSerialPort.instances[0].closed)

    def test_constant_stream_from_the_port_is_rejected_end_to_end(self):
        hardware = HardwareEntropy(SerialSource("/dev/ttyFAKE"))
        with self.assertRaises(SourceHealthError):
            hardware.get_bytes(32)


class KeyGeneratorTests(unittest.TestCase):
    def test_key_mixes_hardware_and_os(self):
        source = FakeSource()
        generated = make_keygen(source).generate()
        self.assertEqual(generated.source, "hardware+os")
        self.assertEqual(generated.hardware_bytes, 128)
        self.assertEqual(len(generated.key), 32)
        self.assertEqual(base64.urlsafe_b64decode(generated.fernet_key), generated.key)
        self.assertEqual(source.bytes_read, STARTUP_SAMPLES + 128)

    def test_keys_are_unique(self):
        keygen = make_keygen(FakeSource())
        self.assertEqual(len({keygen.generate().key for _ in range(20)}), 20)

    def test_identical_hardware_streams_still_give_different_keys(self):
        # Two boards replaying the same bytes (worst case) differ through os.urandom.
        a = make_keygen(FakeSource(seed=7)).generate().key
        b = make_keygen(FakeSource(seed=7)).generate().key
        self.assertNotEqual(a, b)

    def test_fail_closed_by_default(self):
        for mode, error in (
            ("timeout", SourceUnavailableError),
            ("error", SourceUnavailableError),
            ("stuck", SourceHealthError),
            ("biased", SourceHealthError),
        ):
            with self.subTest(mode=mode), self.assertRaises(error):
                make_keygen(FakeSource(mode)).generate()

    def test_no_hardware_configured_fails_closed(self):
        with self.assertRaises(SourceUnavailableError):
            KeyGenerator(None).generate()

    def test_explicit_fallback_is_labelled(self):
        for keygen in (
            make_keygen(FakeSource("stuck"), require_hardware=False),
            KeyGenerator(None, require_hardware=False),
        ):
            generated = keygen.generate()
            self.assertEqual(generated.source, "os-only")
            self.assertEqual(generated.hardware_bytes, 0)
            self.assertEqual(len(generated.key), 32)

    def test_unhealthy_bytes_never_reach_the_key(self):
        seen = []

        def spy(n):
            seen.append(n)
            return b"\x01" * n

        keygen = KeyGenerator(
            make_hardware(FakeSource("stuck")), require_hardware=False, os_random=spy
        )
        generated = keygen.generate()
        self.assertEqual(generated.hardware_bytes, 0)
        self.assertEqual(seen, [32])

    def test_minimum_raw_bytes(self):
        with self.assertRaises(ValueError):
            KeyGenerator(None, raw_bytes_per_key=8)


if __name__ == "__main__":
    unittest.main()
