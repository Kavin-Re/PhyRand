"""PhyRand: physical-noise entropy source, health-tested key generation and key escrow.

The package is split so that everything security-relevant can be unit-tested
without hardware:

* :mod:`phyrand.health`        -- NIST SP 800-90B style continuous health tests
* :mod:`phyrand.conditioning`  -- HKDF-SHA256 conditioning and OS-CSPRNG mixing
* :mod:`phyrand.entropy`       -- serial entropy source and key generator
* :mod:`phyrand.stats`         -- stdlib-only statistical analysis of captures
* :mod:`phyrand.vault`         -- atomic, validated key-escrow store
* :mod:`phyrand.service`       -- framework-independent key-authority logic
* :mod:`phyrand.api`           -- FastAPI transport layer
* :mod:`phyrand.cli`           -- ``phyrand`` command-line interface
"""

__version__ = "0.2.0"
