# PhyRand: Physical Entropy and Zero-Knowledge Vault

**PhyRand** is a hardware-rooted cryptographic appliance designed to bridge the gap between physical phenomena and digital security. It utilizes Zener diode reverse-bias breakdown noise to generate non-deterministic AES-128-CBC keys.

---

## Technical Overview: True Randomness
Software-based random number generators (PRNGs) are inherently deterministic. PhyRand mitigates this risk by employing an Entropy Pipeline sourced from physical noise:

* Source: Zener diode reverse-bias breakdown noise (tunneling regime at 3V).
* Processing: Real-time Von Neumann debiasing performed on-chip via STM32.
* Validation: Achieves an entropy density of 7.9997 bits/byte (ent suite; NIST SP 800-22 pending on corrected firmware output).

---

## System Architecture
PhyRand operates as a decentralized Key Authority. The system architecture provides local client-side encryption with hardware entropy, where plaintext data remains local to the client environment.

1. Hardware Layer: Zener Core, Pre-Amplifier, and Main Amplifier stages.
2. Embedded Layer: STM32 ADC sampling and high-speed USB Serial data streaming.
3. Backend Layer: FastAPI Key Authority mapping the hardware entropy stream to a RESTful service.
4. Client Layer: Browser-based AES-128-CBC (Fernet) encryption suite.

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
Connect the STM32 hardware and ensure the device is mapped to /dev/hwrng.
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
