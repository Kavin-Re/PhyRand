import requests
import os
from cryptography.fernet import Fernet

API_URL = "http://127.0.0.1:8000"

def automated_unlock():
    print("\n" + "="*45)
    print("      V3.0 AUTOMATED QUANTUM DECRYPTOR      ")
    print("="*45)
    
    # Use quotes if your path has spaces
    path_input = input("[?] Enter .quantum file path: ").strip().replace("'", "").replace('"', "")
    file_id = input("[?] Enter File ID: ").strip().upper()
    
    if not os.path.exists(path_input):
        print(f"[-] Error: File not found at {path_input}")
        return

    print(f"[*] Handshaking with Quantum API for ID {file_id}...")
    try:
        response = requests.get(f"{API_URL}/release/{file_id}", timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            key = data['key']
            
            cipher = Fernet(key.encode())
            with open(path_input, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = cipher.decrypt(encrypted_data)
            
            output_name = path_input.replace(".quantum", ".api_unlocked")
            with open(output_name, "wb") as f:
                f.write(decrypted_data)
                
            print(f"[+] SUCCESS! Key retrieved and file unlocked.")
            print(f"[+] Result: {output_name}")
        else:
            print(f"[-] API Error: {response.json().get('detail')}")
            
    except Exception as e:
        print(f"[-] Connection Error: {e}")

if __name__ == "__main__":
    automated_unlock()
