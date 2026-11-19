import random
import unittest

from phyrand import health
from phyrand.health import (
    AdaptiveProportionTest,
    HealthMonitor,
    HealthTestError,
    RepetitionCountTest,
    apt_cutoff,
    critbinom,
    rct_cutoff,
)

from .helpers import CAPTURE


class CutoffTests(unittest.TestCase):
    def test_rct_cutoff_formula(self):
        # C = 1 + ceil(20 / H) for alpha = 2^-20
        self.assertEqual(rct_cutoff(8), 4)
        self.assertEqual(rct_cutoff(4), 6)
        self.assertEqual(rct_cutoff(1), 21)
        self.assertEqual(rct_cutoff(0.5), 41)
        self.assertEqual(rct_cutoff(8, alpha_exp=40), 6)

    def test_apt_cutoffs_match_sp800_90b_table(self):
        # Example cutoffs published in NIST SP 800-90B section 4.4.2 (alpha = 2^-20).
        self.assertEqual(apt_cutoff(1, 1024), 589)  # binary source
        self.assertEqual(apt_cutoff(1, 512), 311)
        self.assertEqual(apt_cutoff(2, 512), 177)
        self.assertEqual(apt_cutoff(4, 512), 62)
        self.assertEqual(apt_cutoff(8, 512), 13)

    def test_critbinom_small_exact_case(self):
        # X ~ Bin(4, 0.5): P[X > 3] = 1/16, P[X > 2] = 5/16
        self.assertEqual(critbinom(4, 0.5, 0.07), 3)
        self.assertEqual(critbinom(4, 0.5, 0.05), 4)
        self.assertEqual(critbinom(4, 0.5, 0.32), 2)

    def test_invalid_parameters(self):
        for bad in (0, -1):
            with self.assertRaises(ValueError):
                rct_cutoff(bad)
        with self.assertRaises(ValueError):
            rct_cutoff(4, alpha_exp=10)
        with self.assertRaises(ValueError):
            HealthMonitor(min_entropy=9)
        with self.assertRaises(ValueError):
            critbinom(10, 1.5, 0.1)


class RepetitionCountTests(unittest.TestCase):
    def test_fails_exactly_at_cutoff(self):
        test = RepetitionCountTest(cutoff=4)
        for _ in range(3):
            test.feed(7)
        with self.assertRaises(HealthTestError) as ctx:
            test.feed(7)
        self.assertEqual(ctx.exception.test, "repetition_count")

    def test_run_is_reset_by_a_different_value(self):
        test = RepetitionCountTest(cutoff=4)
        for value in [7, 7, 7, 8, 7, 7, 7, 9, 9, 9]:
            test.feed(value)  # never four in a row


class AdaptiveProportionTests(unittest.TestCase):
    def test_detects_overrepresented_value_without_long_runs(self):
        test = AdaptiveProportionTest(cutoff=13, window=512)
        rng = random.Random(1)
        with self.assertRaises(HealthTestError) as ctx:
            for i in range(512):
                test.feed(0x55 if i % 3 == 0 else rng.randrange(256))
        self.assertEqual(ctx.exception.test, "adaptive_proportion")

    def test_window_restarts(self):
        test = AdaptiveProportionTest(cutoff=3, window=4)
        # The reference value appears twice per window: below the cutoff of 3.
        for value in [1, 1, 2, 3] * 50:
            test.feed(value)

    def test_cutoff_bounds(self):
        with self.assertRaises(ValueError):
            AdaptiveProportionTest(cutoff=600, window=512)


class HealthMonitorTests(unittest.TestCase):
    def test_pseudo_random_data_passes(self):
        monitor = HealthMonitor(min_entropy=8.0)  # strictest cutoffs
        monitor.feed(random.Random(42).randbytes(200_000))
        self.assertEqual(monitor.failures, 0)
        self.assertEqual(monitor.samples_tested, 200_000)

    def test_stuck_source_is_rejected_quickly(self):
        monitor = HealthMonitor(min_entropy=4.0)
        with self.assertRaises(HealthTestError):
            monitor.feed(b"\x00" * 64)
        self.assertEqual(monitor.samples_tested, monitor.rct_cutoff)
        self.assertEqual(monitor.failures, 1)
        self.assertIn("repetition_count", monitor.last_failure)

    def test_short_repeating_pattern_is_rejected(self):
        # e.g. mains hum aliasing into the LSB: 0xAA 0x55 0xAA 0x55 ...
        monitor = HealthMonitor(min_entropy=4.0)
        with self.assertRaises(HealthTestError) as ctx:
            monitor.feed(b"\xaa\x55" * 512)
        self.assertEqual(ctx.exception.test, "adaptive_proportion")

    def test_monitor_recovers_after_reset(self):
        monitor = HealthMonitor(min_entropy=4.0)
        with self.assertRaises(HealthTestError):
            monitor.feed(b"\x11" * 10)
        monitor.feed(random.Random(3).randbytes(4096))
        self.assertEqual(monitor.failures, 1)

    def test_describe_reports_cutoffs(self):
        info = HealthMonitor(min_entropy=4.0).describe()
        self.assertEqual(info["rct_cutoff"], 6)
        self.assertEqual(info["apt_cutoff"], 62)
        self.assertEqual(info["apt_window"], health.APT_WINDOW_NON_BINARY)

    @unittest.skipUnless(CAPTURE.is_file(), "sample capture not present")
    def test_repository_capture_passes_default_tests(self):
        monitor = HealthMonitor()
        monitor.feed(CAPTURE.read_bytes())
        self.assertEqual(monitor.failures, 0)


if __name__ == "__main__":
    unittest.main()
