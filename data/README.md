# Reference capture

| File | Size | What it is |
| :--- | :--- | :--- |
| `random_whitened.bin` | 1,000,000 bytes | Byte stream captured from the board's UART **after** on-chip Von Neumann debiasing |

**Provenance caveat.** The capture was committed before the firmware fix in
commit `01ff2d5` ("remove XOR stage"). Which firmware revision produced it was
not recorded, so treat it as a historical sample.
`TODO(verify on hardware)`: re-capture with the current firmware
(`phyrand capture -n 1000000 -o data/<name>.bin`) and record the firmware
commit, board, supply and date next to the file.

## Reproducing the numbers

```bash
python -m phyrand analyze data/random_whitened.bin     # standard library only
```

Output for the committed file (pinned by `tests/test_stats.py`, so the
documentation cannot drift from the data):

| Statistic | Value | Ideal | Reading |
| :--- | :--- | :--- | :--- |
| Shannon entropy | 7.99976 bits/byte | 8 | The "7.9997" quoted for this project |
| Chi-square (255 d.o.f.) | 331.58, p = 0.0009 | p not extreme | **Fails** at the 1 % level |
| Arithmetic mean | 126.9575 | 127.5 | About 7.3 standard errors low |
| Serial correlation (lag 1, bytes) | +0.006656 | 0 | About 6.7 standard errors from 0 |
| Ones fraction (all bits) | 0.499225 | 0.5 | z = -4.4 (monobit p = 1.2e-5) |
| Ones fraction, bit 7 only | 0.496082 | 0.5 | z = -7.8 |
| Ones fraction, bits 0-6 | 0.4985 - 0.5008 | 0.5 | all within 3 sigma |
| Monte Carlo pi | 3.157381 | 3.141593 | 0.50 % error |
| MCV min-entropy (SP 800-90B 6.3.1) | 7.869 bits/byte | 8 | One estimator only, see below |
| RCT / APT health tests (H = 4 and H = 8) | 0 failures in 1,000,000 samples | 0 | |

## What this does and does not show

* A Shannon entropy of 7.9997 bits/byte only says the byte histogram is close
  to flat. It is a weak statistic: the same file **fails** a chi-square test
  and a monobit test, because with a million samples small defects become
  statistically visible.
* The defect is concentrated in **bit 7 of each byte, which is the first bit
  the firmware assembles after every UART transmission** (bits are packed
  MSB-first). Hypothesis, `TODO(verify on hardware)`: the blocking
  `HAL_UART_Transmit` and LED toggle disturb the sample timing and/or couple
  into the high-gain analogue front end, so the first sample pair after each
  transmitted byte is slightly skewed. Von Neumann debiasing only removes bias
  from *independent, identically distributed* samples, so a position-dependent
  effect like this passes straight through it.
* The MCV figure is one of the ten SP 800-90B estimators, applied to
  already-conditioned data. It is not an entropy assessment of the noise
  source and must not be quoted as one.
* None of these statistics can distinguish Zener noise from ADC quantisation
  noise or a good PRNG. Source validation needs raw (pre-debiasing) samples
  and a control experiment; both are on the roadmap.

These defects are the reason PhyRand never uses device bytes directly as key
material: every key is `HKDF-SHA256(device bytes || os.urandom)`, which is
unaffected by biases of this size (see `docs/ARCHITECTURE.md`).
