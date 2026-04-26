import serial
import numpy as np
import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt

# Update to ACM1 if needed!
ser = serial.Serial('/dev/ttyACM1', 115200)
size = 128 
grid = np.zeros((size, size))

plt.ion()
fig, ax = plt.subplots()
img = ax.imshow(grid, cmap='magma', vmin=0, vmax=255)

try:
    while True:
        raw_data = ser.read(size * size)
        new_grid = np.frombuffer(raw_data, dtype=np.uint8).reshape((size, size))
        img.set_data(new_grid)
        plt.pause(0.01)
except KeyboardInterrupt:
    ser.close()
