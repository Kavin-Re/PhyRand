import requests
import os
import sys
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load secrets from .env file
load_dotenv()

# CONFIGURATION
# Replace this with your current Ngrok URL
API_URL = "https://lid-nebulizer-baguette.ngrok-free.dev"
MASTER_TOKEN = os.getenv("VAULT_MASTER_TOKEN")

def automated_unlock():
    print("\n" + "="*45)
    print("      V3.1 SECURE QUANTUM DECRYPTOR      ")
    print("="*45)
    
    if not MASTER_TOKEN:
        print("[-] Error: VAULT_MASTER_TOKEN not found in .env file.")
        return

    path = input("[?] Enter .quantum file path: ").strip().replace("'", "").replace('"', "")
    file_id = input("[?] Enter File ID: ").strip().upper()
    
    if not os.path.exists(path):
        print(f"[-] Error: File not found at {path}")
        return

    print(f"[*] Initiating Secure Handshake via {API_URL}...")
    
    try:
        # Inject the secret token into the request headers
        headers = {"x-api-token": MASTER_TOKEN}
        response = requests.get(f"{API_URL}/release/{file_id}", headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            key = data['key']
            
            # Decryption Logic
            cipher = Fernet(key.encode())
            with open(path, "rb") as f:
                encrypted_data = f.read()
            
            decrypted_data = cipher.decrypt(encrypted_data)
            output_name = path.replace(".quantum", ".api_unlocked")
            
            with open(output_name, "wb") as f:
                f.write(decrypted_data)
                
            print(f"[+] SUCCESS! Key retrieved and file unlocked.")
            print(f"[+] Decrypted file saved to: {output_name}")
            
        elif response.status_code == 401:
            print("[-] ACCESS DENIED: The API Token in your .env is incorrect.")
        else:
            print(f"[-] API Error: {response.json().get('detail', 'Unknown error')}")
            
    except Exception as e:
        print(f"[-] Connection Error: {e}")

if __name__ == "__main__":
    automated_unlock()
