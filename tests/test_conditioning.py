import unittest

from phyrand import conditioning
from phyrand.conditioning import hkdf, hkdf_expand, hkdf_extract, mix_entropy


class HkdfRfc5869Tests(unittest.TestCase):
    def test_case_1(self):
        ikm = bytes.fromhex("0b" * 22)
        salt = bytes.fromhex("000102030405060708090a0b0c")
        info = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9")
        prk = hkdf_extract(salt, ikm)
        self.assertEqual(
            prk.hex(), "077709362c2e32df0ddc3f0dc47bba6390b6c73bb50f9c3122ec844ad7c2b3e5"
        )
        self.assertEqual(
            hkdf_expand(prk, info, 42).hex(),
            "3cb25f25faacd57a90434f64d0362f2a2d2d0a90cf1a5a4c5db02d56ecc4c5bf34007208d5b887185865",
        )

    def test_case_3_empty_salt_and_info(self):
        okm = hkdf(bytes.fromhex("0b" * 22), salt=b"", info=b"", length=42)
        self.assertEqual(
            okm.hex(),
            "8da4e775a563c18f715f802a063c5a31b8a11f5c5ee1879ec3454e5f3c738d2d9d201395faa4b61a96c8",
        )

    def test_expand_length_limits(self):
        with self.assertRaises(ValueError):
            hkdf_expand(b"k" * 32, b"", 0)
        with self.assertRaises(ValueError):
            hkdf_expand(b"k" * 32, b"", 255 * 32 + 1)


class MixTests(unittest.TestCase):
    @staticmethod
    def fixed_os(n):
        return b"\x42" * n

    def test_output_length_and_determinism_given_inputs(self):
        a = mix_entropy(b"hw" * 64, os_random=self.fixed_os)
        b = mix_entropy(b"hw" * 64, os_random=self.fixed_os)
        self.assertEqual(a, b)
        self.assertEqual(len(a), 32)
        self.assertEqual(len(mix_entropy(b"x", length=64, os_random=self.fixed_os)), 64)

    def test_both_inputs_influence_the_key(self):
        base = mix_entropy(b"\x01" * 128, os_random=self.fixed_os)
        self.assertNotEqual(base, mix_entropy(b"\x02" * 128, os_random=self.fixed_os))
        self.assertNotEqual(base, mix_entropy(b"\x01" * 128, os_random=lambda n: b"\x43" * n))

    def test_failed_hardware_cannot_weaken_the_key(self):
        # Even with constant "hardware" bytes, fresh OS randomness gives distinct keys.
        keys = {mix_entropy(b"\x00" * 128) for _ in range(50)}
        self.assertEqual(len(keys), 50)

    def test_key_is_not_the_raw_hardware_bytes(self):
        raw = bytes(range(32))
        self.assertNotEqual(mix_entropy(raw, os_random=self.fixed_os), raw)

    def test_length_prefix_prevents_input_boundary_confusion(self):
        # hw="A", os="BBB..."  vs  hw="AB", os="BB..." must not collide.
        first = mix_entropy(b"A", os_random=lambda n: b"B" * n)
        second = mix_entropy(b"AB", os_random=lambda n: b"B" * n)
        self.assertNotEqual(first, second)

    def test_domain_separation_by_info(self):
        self.assertNotEqual(
            mix_entropy(b"hw", os_random=self.fixed_os),
            mix_entropy(b"hw", info=b"other", os_random=self.fixed_os),
        )

    def test_empty_hardware_is_allowed(self):
        self.assertEqual(len(mix_entropy(b"")), 32)

    def test_short_os_read_is_fatal(self):
        with self.assertRaises(RuntimeError):
            mix_entropy(b"hw", os_random=lambda n: b"\x00" * (n - 1))

    def test_os_contribution_is_256_bits(self):
        self.assertEqual(conditioning.OS_ENTROPY_BYTES, 32)


if __name__ == "__main__":
    unittest.main()
