# Firmware (STM32F401RE Nucleo-64)

STM32CubeIDE / STM32 HAL project sources. Only `Core/` is tracked: the HAL
drivers, CMSIS, linker script and `.ioc` file are **not** in this repository,
so the firmware cannot be built from a clean checkout yet. To rebuild, create
an STM32CubeIDE project for the NUCLEO-F401RE with ADC1 IN0 (PA0), USART2
(PA2/PA3, 115200 8N1) and LD2 (PA5), then replace the generated `Core/` with
this one. Committing the `.ioc` and linker script is on the roadmap.

## What `Core/Src/main.c` does

```
loop:
    start ADC1, poll for one 12-bit conversion on PA0 (3-cycle sample time)
    raw_bit = sample & 1
    collect raw bits in non-overlapping pairs
        01 -> emit 0      10 -> emit 1      00 / 11 -> emit nothing   (Von Neumann)
    shift emitted bits MSB-first into a byte
    every 8 bits: blocking UART transmit of the byte (USART2 -> ST-LINK VCP), toggle LD2
```

| Setting | Value |
| :--- | :--- |
| System clock | HSI 16 MHz -> PLL -> 84 MHz |
| ADC | ADC1 channel 0 (PA0), 12-bit, software trigger, single conversion, PCLK2/4 = 21 MHz, 3-cycle sampling |
| Output | USART2, 115200 baud, 8N1, raw binary bytes, no framing |
| Indicator | LD2 (PA5) toggles once per transmitted byte |

A bit-exact Python model of the debiaser lives in `phyrand/debias.py` and is
tested in `tests/test_debias.py`.

## Review notes (no firmware source was changed in this revision)

The Von Neumann logic is correct: pairs do not overlap, equal pairs are
discarded, the first bit of an unequal pair is emitted, and state is reset
after each byte. No memory-safety or buffer-handling bug was found (the only
buffer is the two-element pair buffer, indexed by constants). The points below
are design limitations rather than clear bugs, so the code was left untouched;
each needs bench time to resolve.

| # | Observation | Where | Why it matters | Suggested follow-up |
| :- | :--- | :--- | :--- | :--- |
| 1 | Only the ADC's least-significant bit is used | `main.c:63` | The LSB of a 12-bit SAR ADC toggles from the converter's own noise even with a quiet input. The Zener stage may be contributing little or nothing to the output. | Control experiment: capture with PA0 tied to a quiet mid-rail divider (Zener removed) and compare. Export raw 12-bit samples for analysis. |
| 2 | Sampling is software-paced and interrupted by a blocking UART transmit (about 87 us per byte) plus an LED toggle | `main.c:57-62`, `main.c:80-87` | Sample spacing is irregular and the first pair after every transmit sees different conditions. The reference capture shows a matching bias in the first bit of each byte (`data/README.md`). | Timer-triggered ADC with DMA, UART via DMA/interrupt, no LED toggle in the sampling path; or discard the first pair after each transmit. |
| 3 | Von Neumann debiasing assumes independent samples | `main.c:65-90` | It removes bias but not correlation or periodic interference (see `tests/test_debias.py::test_does_not_remove_correlation`). | Measure raw-sample autocorrelation; lower the sample rate or add a proper conditioner. |
| 4 | No on-chip health tests, no framing, no raw-sample mode | whole file | A stuck source produces *no output* (the host sees a timeout, which is safe), but the host cannot tell bias from failure and cannot run SP 800-90B tests on raw data. | Add RCT/APT on raw samples, a framed protocol with a health flag, and a command to stream raw samples. |
| 5 | Return values of `HAL_ADC_Start`, `HAL_ADC_Stop` and `HAL_UART_Transmit` are ignored | `main.c:57`, `62`, `81` | A failed transmit silently drops a byte (harmless for randomness, but hides faults). | Count errors and signal them (LED pattern / status frame). |
| 6 | `__HAL_UART_CLEAR_OREFLAG` before every transmit | `main.c:80` | Clears a receive-overrun flag although nothing is received; harmless but unnecessary. | Remove when the firmware is next touched and re-tested. |
| 7 | Unused I2C1 MSP init/de-init code and `HAL_I2C_MODULE_ENABLED` | `stm32f4xx_hal_msp.c`, `stm32f4xx_hal_conf.h` | Left over from the CubeMX template; I2C1 is never initialised. | Regenerate from a cleaned-up `.ioc`. |
| 8 | The UART here is the ST-LINK virtual COM port, not native USB | `main.c:170-184` | Throughput is capped by 115200 baud (at most 11.5 kB/s) and by the debiaser's yield. | Documentation corrected; native USB CDC is a roadmap item. |

Any change addressing items 1-6 alters the entropy path and therefore
**needs a hardware re-test**: a fresh 1 MB capture analysed with
`phyrand analyze`, plus the control experiment in item 1.
