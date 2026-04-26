import serial
import base64
import os
import json
import uvicorn
from fastapi import FastAPI, HTTPException, Header
from cryptography.fernet import Fernet
from dotenv import load_dotenv

# Load secrets from .env file
load_dotenv()

app = FastAPI(title="Quantum QRNG API v3.1 - Production")

# Configuration from Environment Variables
SERIAL_PORT = os.getenv("QRNG_SERIAL_PORT", "/dev/quantum_qrng")
BAUD_RATE = 115200
VAULT_DB = "vault/quantum_vault.json"
MASTER_TOKEN = os.getenv("VAULT_MASTER_TOKEN")

def get_live_entropy(n=32):
    """Harvests raw entropy from the STM32 hardware."""
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=5) as ser:
            ser.reset_input_buffer()
            data = ser.read(n)
            return data if len(data) == n else None
    except Exception as e:
        print(f"[-] Hardware Error: {e}")
        return None

@app.get("/")
def home():
    return {"status": "Quantum Engine Online", "device": SERIAL_PORT}

@app.get("/stats")
def hardware_stats():
    """Live diagnostic check for Zener noise."""
    sample = get_live_entropy(4)
    if sample:
        return {"hardware": "Healthy", "entropy_sample": sample.hex()}
    return {"hardware": "Offline", "detail": "Check USB connection"}

@app.get("/release/{file_id}")
def release_key(file_id: str, x_api_token: str = Header(None)):
    """
    Secure Key Release. 
    Requires 'x-api-token' matching the .env MASTER_TOKEN.
    """
    # 1. Security Handshake Check
    if not MASTER_TOKEN or x_api_token != MASTER_TOKEN:
        print(f"[!] SECURITY ALERT: Unauthorized access attempt for ID {file_id}")
        raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing token")
    
    # 2. Vault Access
    if not os.path.exists(VAULT_DB):
        raise HTTPException(status_code=500, detail="Vault database missing")
        
    with open(VAULT_DB, "r") as f:
        vault = json.load(f)
    
    clean_id = file_id.strip().upper()
    
    if clean_id in vault:
        print(f"[+] Authorized release for ID: {clean_id}")
        return {
            "file_id": clean_id,
            "key": vault[clean_id]["quantum_key"],
            "status": "Success"
        }
    
    raise HTTPException(status_code=404, detail="File ID not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
