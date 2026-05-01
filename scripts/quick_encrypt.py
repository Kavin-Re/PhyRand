import os
import json
import base64
from cryptography.fernet import Fernet

VAULT_DB = "vault/quantum_vault.json"

def fast_encrypt(filename):
    # 1. Create a fresh key
    key = Fernet.generate_key()
    f = Fernet(key)
    
    # 2. Read the original data
    with open(filename, "rb") as file:
        data = file.read()
    
    # 3. Encrypt (This creates a Fernet token)
    token = f.encrypt(data)
    
    # 4. Save as RAW BINARY (This is crucial for the web portal)
    output_name = filename + ".quantum"
    with open(output_name, "wb") as out_file:
        out_file.write(token)
    
    # 5. Generate a unique 6-character ID
    file_id = base64.b32encode(os.urandom(5)).decode('utf-8')[:6].upper()
    
    # 6. Update the Vault
    if not os.path.exists("vault"): os.mkdir("vault")
    
    vault = {}
    if os.path.exists(VAULT_DB):
        with open(VAULT_DB, "r") as v_file:
            vault = json.load(v_file)
            
    vault[file_id] = {"quantum_key": key.decode()}
    
    with open(VAULT_DB, "w") as v_file:
        json.dump(vault, v_file, indent=4)
        
    print(f"\n[+] SUCCESS!")
    print(f"[*] File: {output_name}")
    print(f"[*] NEW FILE ID: {file_id}")
    print(f"[*] Key saved to vault. Ready for the portal.")

if __name__ == "__main__":
    target = input("Enter filename to encrypt (e.g. secret.txt): ")
    fast_encrypt(target)
