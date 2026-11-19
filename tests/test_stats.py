import math
import random
import unittest

from phyrand import stats

from .helpers import CAPTURE


class StatsTests(unittest.TestCase):
    def test_shannon_entropy_extremes(self):
        self.assertEqual(stats.shannon_entropy(b"\x00" * 1000), 0)
        self.assertAlmostEqual(stats.shannon_entropy(bytes(range(256)) * 10), 8.0)
        self.assertAlmostEqual(stats.shannon_entropy(b"\x00\x01" * 500), 1.0)

    def test_chi_square(self):
        self.assertAlmostEqual(stats.chi_square(bytes(range(256)) * 4), 0.0)
        # All mass on one value: (n - n/256)^2/(n/256) + 255 * n/256 = 255 n
        self.assertAlmostEqual(stats.chi_square(b"\x07" * 512), 255 * 512)

    def test_chi_square_p_value(self):
        # For 2 degrees of freedom the survival function is exactly exp(-x/2).
        for x in (0.5, 2.0, 7.0, 30.0):
            self.assertAlmostEqual(stats.chi_square_p_value(x, dof=2), math.exp(-x / 2), places=12)
        self.assertEqual(stats.chi_square_p_value(0.0), 1.0)
        # Median of chi-square(255) is about 255 * (1 - 2/(9*255))^3 = 254.33.
        self.assertAlmostEqual(stats.chi_square_p_value(254.334), 0.5, places=3)
        self.assertLess(stats.chi_square_p_value(400), 1e-7)

    def test_serial_correlation(self):
        self.assertAlmostEqual(stats.serial_correlation(b"\x00\xff" * 500), -1.0)
        self.assertEqual(stats.serial_correlation(b"\x05" * 100), 1.0)
        noise = random.Random(5).randbytes(100_000)
        self.assertLess(abs(stats.serial_correlation(noise)), 0.02)

    def test_bit_position_ones_fraction(self):
        fractions = stats.bit_position_ones_fraction(b"\x80\x80\x81\x00")
        self.assertEqual(fractions, (0.25, 0, 0, 0, 0, 0, 0, 0.75))

    def test_mean_and_ones_fraction(self):
        self.assertEqual(stats.arithmetic_mean(bytes(range(256))), 127.5)
        self.assertEqual(stats.ones_fraction(b"\x0f\xf0"), 0.5)
        self.assertEqual(stats.ones_fraction(b"\xff"), 1.0)

    def test_monte_carlo_pi(self):
        self.assertEqual(stats.monte_carlo_pi(b"\x00" * 600), 4.0)
        self.assertEqual(stats.monte_carlo_pi(b"\xff" * 600), 0.0)
        estimate = stats.monte_carlo_pi(random.Random(9).randbytes(600_000))
        self.assertAlmostEqual(estimate, math.pi, delta=0.05)

    def test_mcv_min_entropy(self):
        self.assertEqual(stats.mcv_min_entropy(1000, 1000), 0.0)
        # p_hat = 0.5, n = 10001: p_u = 0.5 + 2.5758 * sqrt(0.25 / 10000)
        expected = -math.log2(0.5 + 2.5758293035489 * 0.005)
        self.assertAlmostEqual(stats.mcv_min_entropy(5000.5, 10001), expected, places=6)
        # The estimate is always below the plug-in value -log2(p_hat).
        self.assertLess(stats.mcv_min_entropy(40, 10_000), -math.log2(40 / 10_000))
        with self.assertRaises(ValueError):
            stats.mcv_min_entropy(0, 10)

    def test_analyze_flags_bad_data(self):
        report = stats.analyze(b"\x00\x01\x02\x03" * 1000)
        self.assertAlmostEqual(report.shannon_entropy_bits_per_byte, 2.0)
        self.assertLess(report.chi_square_p_value, 1e-9)
        self.assertLess(report.mcv_min_entropy_bits_per_byte, 2.0)

    def test_analyze_rejects_tiny_input(self):
        with self.assertRaises(ValueError):
            stats.analyze(b"abc")

    def test_format_report_mentions_scope(self):
        text = stats.format_report(stats.analyze(random.Random(1).randbytes(6000)), "x.bin")
        self.assertIn("x.bin", text)
        self.assertIn("do not validate", text)

    @unittest.skipUnless(CAPTURE.is_file(), "sample capture not present")
    def test_repository_capture_matches_documented_figures(self):
        """Pins the numbers quoted in README.md and data/README.md."""
        report = stats.analyze(CAPTURE.read_bytes())
        self.assertEqual(report.length_bytes, 1_000_000)
        self.assertAlmostEqual(report.shannon_entropy_bits_per_byte, 7.99976, places=5)
        self.assertAlmostEqual(report.chi_square, 331.58, places=2)
        self.assertAlmostEqual(report.arithmetic_mean, 126.9575, places=4)
        self.assertAlmostEqual(report.serial_correlation, 0.006656, places=6)
        self.assertAlmostEqual(report.ones_fraction, 0.499225, places=6)
        self.assertAlmostEqual(report.mcv_min_entropy_bits_per_byte, 7.8692, places=4)
        self.assertAlmostEqual(report.chi_square_p_value, 0.0009, places=4)
        # The first bit of every byte is measurably biased in this capture
        # (see data/README.md); the other positions are within 3 sigma.
        z = report.bit_position_z_scores()
        self.assertAlmostEqual(report.bit_position_ones_fraction[7], 0.496082, places=6)
        self.assertAlmostEqual(z[7], -7.84, places=2)
        self.assertTrue(all(abs(value) < 3 for value in z[:7]))


if __name__ == "__main__":
    unittest.main()
