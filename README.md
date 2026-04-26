# SECURE EXCHANGE (v4.0)

This major update transitions the project from a terminal-based tool to a unified web appliance.

## Version 4.0: Secure Exchange Release

### Unified Dashboard Architecture
- Persona Separation: The interface is divided into a dedicated Unlock view for receivers and an Admin Tools view for vault management.
- Glassmorphism UI: Implemented a modern design language using deep-space gradients, glass-style transparency, and high-legibility typography (Inter and JetBrains Mono).

### Hardware-Verified Entropy Pipeline
- Real-Time Heartbeat: The dashboard features a live hardware status monitor and entropy seed preview sourced directly from the STM32 serial stream.
- Quantum Seeded Identifiers: File IDs and encryption keys are generated using the hardware entropy source, ensuring cryptographic-grade randomness for every session.

### Advanced Binary Vaulting
- Local Client-Side Encryption: Encryption and decryption logic now occurs in the browser. Plaintext data remains local, while the server only manages hardware keys and metadata.
- Universal Binary Support: Fully validated for securing high-density binary files including images and videos.
- Metadata Persistence: The system now automatically captures and restores original file extensions and encryption timestamps during the restoration process.
- Vault Revocation Suite: Integrated administrative controls to synchronize the active vault index and revoke access identifiers in real time.

### Diagnostic Monitoring
- System Stats Endpoint: Added a dedicated /stats API endpoint for comprehensive hardware and vault health reporting in JSON format.

---

# Quantum Random Number Generator (v3.0)

A hardware-driven TRNG and Automated Key Authority.

## Version 3.0: Automated API Handshake
This version transforms the vault into a network-accessible service:
- Persistent Hardware Path: Uses Linux udev rules to map the STM32 to /dev/quantum_qrng.
- FastAPI Backend: A high-performance REST API that acts as a Key Authority.
- Automated Handshake: The auto_unlock.py client automatically requests keys via HTTP, removing manual entry.
- Quantum Entropy Stats: Live hardware health checks served via JSON.

## System Architecture
1. Physics: Zener avalanche noise (STM32 v3.0 Immortal Firmware).
2. Logic: Python FastAPI server managing the hardware stream.
3. Transport: AES-256 (Fernet) encrypted files with hardware-seeded keys.

## Project Structure
- /firmware: STM32 source code.
- qrng_api.py: The Key Authority server.
- auto_unlock.py: The automated client decryptor.
- /vault: Secure local key storage (Git-ignored).

## How to Run
1. Connect hardware. Verify /dev/quantum_qrng exists.
2. Run server: python3 qrng_api.py
3. Unlock file: python3 auto_unlock.py

---

## Version 2.0: Quantum Lockbox
- **Feature:** Hardware-encrypted file vaulting.
- **Security:** Uses 256-bit AES keys seeded by live Zener noise ($2^{256}$ complexity).
- **Workflow:** Sender locks a file using `quantum_vault.py`, receiver unlocks using `receiver_decrypt.py` + shared Key ID.

---

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

---

# QRNG-Project
A Quantum TRNG harvesting entropy from Zener avalanche noise. Processed via STM32 firmware (Von Neumann/XOR) to achieve 7.9997 bits/byte entropy. Includes a Python real-time monitor and a One-Time Pad encryption vault. Validated for cryptographic-grade security using industry-standard statistical analysis. Perfect for secure data generation.
