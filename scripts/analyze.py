import matplotlib.pyplot as plt
import numpy as np

def plot_random_walk(filename):
    with open(filename, 'rb') as f:
        data = f.read()
    
    # Convert bytes to a sequence of bits
    bits = np.unpackbits(np.frombuffer(data, dtype=np.uint8))
    
    # +1 for bit 1, -1 for bit 0
    steps = np.where(bits == 1, 1, -1)
    path = np.cumsum(steps)
    
    plt.figure(figsize=(10, 5))
    plt.plot(path, color='purple', linewidth=0.5)
    plt.axhline(0, color='black', linestyle='--')
    plt.title("Quantum Random Walk (Bias Detection)")
    plt.xlabel("Bits Processed")
    plt.ylabel("Cumulative Bias (1s vs 0s)")
    plt.grid(True)
    plt.show()

# Execute
# Change the last line of your analyze.py to:
plot_random_walk('random_whitened.bin')
