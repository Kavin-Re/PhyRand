import serial
import base64
import os
import json
import time
from cryptography.fernet import Fernet

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/ttyACM1'
BAUD_RATE = 115200
VAULT_FILE = "quantum_vault.json"

def load_vault():
    if os.path.exists(VAULT_FILE):
        with open(VAULT_FILE, "r") as f:
            return json.load(f)
    return {}

def save_vault(vault_data):
    with open(VAULT_FILE, "w") as f:
        json.dump(vault_data, f, indent=4)

def get_quantum_key(byte_count=32):
    """Pulls live entropy from the STM32 v3.0 Immortal Firmware."""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=10) as ser:
            ser.reset_input_buffer()
            entropy = ser.read(byte_count)
            if len(entropy) < byte_count:
                raise Exception("Quantum source timed out.")
            return entropy
    except Exception as e:
        print(f"[-] Hardware Error: {e}")
        return None

def encrypt_file_action():
    filename = input("Enter filename to encrypt: ").strip()
    if not os.path.exists(filename):
        print("[-] Error: File not found.")
        return

    # 1. Harvest Entropy
    raw_bytes = get_quantum_key(32)
    if not raw_bytes: return
    
    # 2. Encrypt
    key = base64.urlsafe_b64encode(raw_bytes)
    cipher = Fernet(key)
    
    with open(filename, "rb") as f:
        data = f.read()
    
    encrypted_data = cipher.encrypt(data)
    output_path = filename + ".quantum"
    
    with open(output_path, "wb") as f:
        f.write(encrypted_data)
        
    # 3. Vault the key
    file_id = os.urandom(3).hex().upper()
    vault = load_vault()
    vault[file_id] = {
        "filename": filename,
        "key": key.decode(),
        "timestamp": time.ctime()
    }
    save_vault(vault)
    
    print("\n" + "="*40)
    print(f" SUCCESS: {output_path}")
    print(f" FILE ID: {file_id}")
    print("="*40)
    print(f"[!] Send the .quantum file to the receiver.")
    print(f"[!] Only release the key for ID {file_id} upon request.")

def list_keys():
    vault = load_vault()
    print("\n--- CURRENT VAULTED FILES ---")
    for fid, info in vault.items():
        print(f"ID: {fid} | File: {info['filename']} | Date: {info['timestamp']}")

def release_key():
    file_id = input("Enter File ID to release: ").strip().upper()
    vault = load_vault()
    if file_id in vault:
        print("\n" + "*"*40)
        print(f"RELEASED KEY: {vault[file_id]['key']}")
        print("*"*40)
    else:
        print("[-] Invalid ID.")

if __name__ == "__main__":
    while True:
        print("\n--- SENDER SIDE: QUANTUM VAULT v2.0 ---")
        print("1. Encrypt File (Pull STM32 Entropy)")
        print("2. List Vaulted Files")
        print("3. Release Key (Show string for ID)")
        print("4. Exit")
        choice = input("Choice: ")
        
        if choice == "1": encrypt_file_action()
        elif choice == "2": list_keys()
        elif choice == "3": release_key()
        elif choice == "4": break
