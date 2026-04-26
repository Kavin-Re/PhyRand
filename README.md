# Quantum Random Number Generator (v1.0)
A hardware-based TRNG using Zener avalanche noise, processed via STM32, and validated for cryptographic use.

## Features
- **Entropy Source:** Zener diode avalanche breakdown.
- **Processing:** Von Neumann debiasing & XOR whitening (STM32F401RE).
- **Quality:** 7.9997 bits/byte entropy (verified via `ent` suite).
- **Apps:** Live entropy monitor and One-Time Pad (OTP) vault.

## Project Structure
- `/firmware`: STM32 source code.
- `/scripts`: Python tools for analysis and encryption.
- `/data`: Sample entropy captures.
