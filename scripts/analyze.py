import matplotlib
matplotlib.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np

def plot_random_walk(filename):
    try:
        with open(filename, 'rb') as f:
            data = f.read()
        bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
        steps = np.where(bits == 1, 1, -1)
        path = np.cumsum(steps)
        plt.figure(figsize=(10, 5))
        plt.plot(path, color='purple', linewidth=0.5)
        plt.axhline(0, color='black', linestyle='--')
        plt.title("Quantum Random Walk (Bias Detection)")
        plt.show()
    except FileNotFoundError:
        print("Error: Capture some data first!")

plot_random_walk('../data/random_whitened.bin')
