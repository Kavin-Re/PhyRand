#!/usr/bin/env python3
"""Live 128x128 greyscale view of the byte stream coming from the board.

A visual sanity check only (structure or stripes mean something is wrong);
it proves nothing about entropy.  Needs pyserial, numpy and matplotlib
(``pip install -r requirements-viz.txt``).

    python scripts/live_view.py --port /dev/ttyACM0
"""

import argparse
import os

SIZE = 128


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", default=os.environ.get("QRNG_SERIAL_PORT", "/dev/ttyACM0"))
    parser.add_argument("--baud", type=int, default=115200)
    args = parser.parse_args()

    import matplotlib.pyplot as plt
    import numpy as np
    import serial

    plt.ion()
    _fig, ax = plt.subplots()
    image = ax.imshow(np.zeros((SIZE, SIZE)), cmap="magma", vmin=0, vmax=255)
    plt.title("PhyRand live byte stream")

    with serial.Serial(args.port, args.baud, timeout=30) as ser:
        try:
            while True:
                raw = ser.read(SIZE * SIZE)
                if len(raw) < SIZE * SIZE:
                    print("timed out waiting for data; is the board streaming?")
                    return 1
                image.set_data(np.frombuffer(raw, dtype=np.uint8).reshape((SIZE, SIZE)))
                plt.pause(0.01)
        except KeyboardInterrupt:
            return 0


if __name__ == "__main__":
    raise SystemExit(main())
