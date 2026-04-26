import base64
import os
from cryptography.fernet import Fernet

def decrypt_utility():
    print("\n" + "="*40)
    print("      RECEIVER SIDE: QUANTUM UNLOCK      ")
    print("="*40)
    
    # 1. Target the file
    path = input("[?] Enter path of the .quantum file: ").strip()
    if not os.path.exists(path):
        print("[-] Error: File not found.")
        return
    
    # 2. Input the Quantum Key
    key_str = input("[?] Enter the Quantum Key from the sender: ").strip()
    
    try:
        # Initialize Decryptor
        cipher = Fernet(key_str.encode())
        
        with open(path, "rb") as f:
            encrypted_data = f.read()
            
        # Decrypt
        decrypted_data = cipher.decrypt(encrypted_data)
        
        # Save output
        output_name = path.replace(".quantum", ".decrypted")
        with open(output_name, "wb") as f:
            f.write(decrypted_data)
            
        print("\n" + "-"*40)
        print(f"[+] SUCCESS! File unlocked: {output_name}")
        
        # Preview if text
        try:
            print(f"[+] MESSAGE CONTENT:\n{decrypted_data.decode('utf-8')}")
        except:
            print("[!] Binary file detected. See .decrypted file for content.")
        print("-"*40)
        
    except Exception as e:
        print(f"\n[-] DECRYPTION FAILED: {e}")
        print("[!] The key is incorrect or the file was corrupted.")

if __name__ == "__main__":
    decrypt_utility()
