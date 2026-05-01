# Hardware Specification: The Avalanche Core

This document details the Analog Front-End (AFE) responsible for harvesting and conditioning quantum noise for the Secure Exchange project.

## 1. Schematic Overview
The circuit is designed as a cascading waterfall. The Zener diode creates a microscopic "splash" of noise, which is captured and amplified through two BJT stages until it is large enough for the microcontroller to "hear."

### Signal Chain Connections
| Section | Component | From | To |
| :--- | :--- | :--- | :--- |
| **Core** | 1kΩ Resistor | 3.3V Pin | Row 34 |
| **Core** | 3V Zener Diode | Row 34 | GND Rail |
| **Stage 1** | 10nF Capacitor | Row 34 | Row 41 (Base 1) |
| **Stage 1** | 750kΩ Bias | 3.3V Rail | Row 41 (Base 1) |
| **Stage 1** | 1kΩ Load | 3.3V Rail | Row 40 (Collector 1) |
| **Stage 2** | 10nF Capacitor | Row 40 | Row 51 (Base 2) |
| **Stage 2** | 750kΩ Bias | 3.3V Rail | Row 51 (Base 2) |
| **Stage 2** | 1kΩ Load | 3.3V Rail | Row 50 (Collector 2) |
| **Interface**| Jumper Wire | Row 50 | STM32 Pin PA0 (A0) |

## 2. Component List
*   **MCU:** STM32F401RE Nucleo-64
*   **Transistors:** 2x BC547 (NPN BJT)
*   **Diodes:** 1x 3V Zener Diode
*   **Capacitors:** 2x 10nF Ceramic (labeled '103')
*   **Resistors:** 3x 1kΩ, 2x 750kΩ

## 3. Engineering & Debugging Log
The following table documents the critical hurdles cleared during the hardware assembly phase:

| Phase | Problem | Root Cause | Solution |
| :--- | :--- | :--- | :--- |
| **Power** | Dead Breadboard | Internal physical gap in rails. | Added jumper wire bridge. |
| **Zener** | No Ignition | 5.1V Zener exceeded 3.3V supply. | Swapped to 3V Zener. |
| **Amp** | Stage 1 Saturation | Base current too high. | Increased Bias to 750kΩ. |
| **Amp** | Stage 2 Cut-off | Emitter was "floating." | Fixed GND connection on Row 52. |
| **Verification** | 0.0V AC Reading | Multimeter too slow for noise. | Used "Human Antenna" test. |

## 4. Digital Sampling Path
The conditioned noise exits the amplifier at **Row 50** and enters the **STM32 at Pin PA0**. The firmware then applies Von Neumann debiasing and XOR whitening to ensure a final entropy of **7.9997 bits/byte**.
