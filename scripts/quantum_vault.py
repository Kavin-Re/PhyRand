import sys

def quantum_xor(file_path, key_path, output_path):
    with open(file_path, 'rb') as f_in, open(key_path, 'rb') as f_key:
        plaintext = f_in.read()
        key = f_key.read(len(plaintext))
        ciphertext = bytes([p ^ k for p, k in zip(plaintext, key)])
        with open(output_path, 'wb') as f_out:
            f_out.write(ciphertext)
    print(f"Success! Created {output_path}")

if __name__ == "__main__":
    if len(sys.argv) == 4:
        quantum_xor(sys.argv[1], sys.argv[2], sys.argv[3])
    else:
        print("Usage: python3 quantum_vault.py [input] [key] [output]")
