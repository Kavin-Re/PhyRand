## Version 2.0: Quantum Lockbox
- **Feature:** Hardware-encrypted file vaulting.
- **Security:** Uses 256-bit AES keys seeded by live Zener noise ($2^{256}$ complexity).
- **Workflow:** Sender locks a file using `quantum_vault.py`, receiver unlocks using `receiver_decrypt.py` + shared Key ID.

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

# QRNG-Project
A Quantum TRNG harvesting entropy from Zener avalanche noise. Processed via STM32 firmware (Von Neumann/XOR) to achieve 7.9997 bits/byte entropy. Includes a Python real-time monitor and a One-Time Pad encryption vault. Validated for cryptographic-grade security using industry-standard statistical analysis. Perfect for secure data generation.
