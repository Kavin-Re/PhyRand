import random
import unittest

from phyrand.debias import pack_bits_msb_first, von_neumann_bits, von_neumann_bytes


class VonNeumannTests(unittest.TestCase):
    def test_pair_rules(self):
        # 01 -> 0, 10 -> 1, 00 and 11 -> nothing (first bit of a differing pair).
        self.assertEqual(list(von_neumann_bits([0, 1])), [0])
        self.assertEqual(list(von_neumann_bits([1, 0])), [1])
        self.assertEqual(list(von_neumann_bits([0, 0, 1, 1])), [])

    def test_pairs_do_not_overlap(self):
        # Bits: (1,1) (0,1) (1,0) -> 0, 1.  An overlapping reader would see more.
        self.assertEqual(list(von_neumann_bits([1, 1, 0, 1, 1, 0])), [0, 1])

    def test_trailing_unpaired_bit_is_ignored(self):
        self.assertEqual(list(von_neumann_bits([1, 0, 1])), [1])

    def test_constant_input_produces_no_output(self):
        self.assertEqual(von_neumann_bytes([0xFFF] * 10_000), b"")
        self.assertEqual(von_neumann_bytes([0x800] * 10_000), b"")

    def test_bits_are_packed_msb_first_like_the_firmware(self):
        # result_byte = (result_byte << 1) | bit, eight times.
        self.assertEqual(pack_bits_msb_first([1, 0, 0, 0, 0, 0, 0, 0]), b"\x80")
        self.assertEqual(pack_bits_msb_first([0, 0, 0, 0, 0, 0, 0, 1]), b"\x01")
        self.assertEqual(pack_bits_msb_first([1] * 11), b"\xff")  # partial byte dropped

    def test_only_the_adc_lsb_is_used(self):
        samples = [0x123, 0x7FE] * 8  # LSBs 1,0 -> eight 1 bits
        self.assertEqual(von_neumann_bytes(samples), b"\xff")

    def test_removes_bias_from_independent_bits(self):
        rng = random.Random(11)
        raw = [1 if rng.random() < 0.8 else 0 for _ in range(400_000)]
        out = list(von_neumann_bits(raw))
        ones = sum(out) / len(out)
        self.assertAlmostEqual(ones, 0.5, delta=0.01)
        # Expected yield is p(1-p) output bits per input bit = 0.16.
        self.assertAlmostEqual(len(out) / len(raw), 0.16, delta=0.01)

    def test_does_not_remove_correlation(self):
        """Documents the known limitation: Von Neumann assumes independent samples."""
        rng = random.Random(12)
        raw, bit = [], 0
        for _ in range(400_000):
            if rng.random() < 0.9:  # strongly "sticky" source
                pass
            else:
                bit ^= 1
            raw.append(bit)
        out = list(von_neumann_bits(raw))
        repeats = sum(1 for a, b in zip(out, out[1:], strict=False) if a == b) / (len(out) - 1)
        self.assertLess(repeats, 0.45, "output of a correlated source is visibly non-random")


if __name__ == "__main__":
    unittest.main()
