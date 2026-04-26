import serial
import base64
import os
import json
import uvicorn
from fastapi import FastAPI, HTTPException
from cryptography.fernet import Fernet

app = FastAPI(title="Quantum QRNG API v3.0 - Master")

# --- CONFIGURATION ---
SERIAL_PORT = '/dev/quantum_qrng'
BAUD_RATE = 115200
VAULT_DB = "vault/quantum_vault.json"

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
    """Live diagnostic check to verify Zener noise is reaching the web."""
    sample = get_live_entropy(4)
    if sample:
        return {"hardware": "Healthy", "entropy_sample": sample.hex()}
    return {"hardware": "Offline", "detail": "Check USB connection"}

@app.get("/release/{file_id}")
def release_key(file_id: str):
    """Automated Key Release for the auto_unlock.py client."""
    if not os.path.exists(VAULT_DB):
        raise HTTPException(status_code=500, detail="Vault database not found")
        
    with open(VAULT_DB, "r") as f:
        vault = json.load(f)
    
    clean_id = file_id.strip().upper()
    
    if clean_id in vault:
        # Returns the 'quantum_key' field from your specific JSON format
        return {
            "file_id": clean_id,
            "key": vault[clean_id]["quantum_key"],
            "status": "Success"
        }
    
    raise HTTPException(status_code=404, detail="File ID not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
