# PhyRand: Physical Entropy and Zero-Knowledge Vault

**PhyRand** is a hardware-rooted cryptographic appliance designed to bridge the gap between physical phenomena and digital security. It utilizes Zener diode avalanche noise to generate non-deterministic AES-256 keys.

---

## Technical Overview: True Randomness
Software-based random number generators (PRNGs) are inherently deterministic. PhyRand mitigates this risk by employing an Entropy Pipeline sourced from physical noise:

* Source: Zener diode avalanche breakdown (Quantum-level chaotic fluctuations).
* Processing: Real-time Von Neumann debiasing and XOR whitening performed on-chip via STM32.
* Validation: Achieves a verified entropy density of 7.9997 bits/byte.

---

## System Architecture
PhyRand operates as a decentralized Key Authority. The system architecture ensures zero-knowledge encryption, where plaintext data remains local to the client environment.

1. Hardware Layer: Zener Core, Pre-Amplifier, and Main Amplifier stages.
2. Embedded Layer: STM32 ADC sampling and high-speed USB Serial data streaming.
3. Backend Layer: FastAPI Key Authority mapping the hardware entropy stream to a RESTful service.
4. Client Layer: Browser-based AES-256 (Fernet) encryption suite.

---

## Repository Structure
* /api: FastAPI Key Authority server implementation.
* /firmware: STM32 source code and pre-compiled binaries.
* /scripts: Python utilities for entropy analysis and automated vault management.
* /data: Raw entropy captures and statistical validation records.
* /vault: Secure local storage for encrypted assets and session metadata.

---

## Installation and Usage

### 1. Key Authority Initialization
Connect the STM32 hardware and ensure the device is mapped to /dev/quantum_qrng.
```bash
# Install required dependencies
pip install -r requirements.txt

# Execute the FastAPI server
python3 api/qrng_api.py
```

### 2. File Encryption
Utilize the CLI utility for local file security:
```bash
python3 scripts/quantum_vault.py <filename>
```
---
**Author: Kavin-Re**
*Electronics Engineering | Embedded Systems | Applied Cryptography*
