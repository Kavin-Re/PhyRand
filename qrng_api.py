import serial
import base64
import os
import json
import uvicorn
from fastapi import FastAPI, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from dotenv import load_dotenv

# Load configuration
load_dotenv()

app = FastAPI(title="Quantum QRNG Web Portal v3.2")

# --- CONFIGURATION ---
SERIAL_PORT = os.getenv("QRNG_SERIAL_PORT", "/dev/quantum_qrng")
MASTER_TOKEN = os.getenv("VAULT_MASTER_TOKEN")
VAULT_DB = "vault/quantum_vault.json"

# --- MIDDLEWARE: ENABLE CORS ---
# Required for browsers to talk to the API across different domains (Ngrok)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_live_entropy(n=32):
    try:
        with serial.Serial(SERIAL_PORT, 115200, timeout=5) as ser:
            ser.reset_input_buffer()
            data = ser.read(n)
            return data if len(data) == n else None
    except Exception:
        return None

# --- WEB ROUTES ---

@app.get("/")
async def serve_portal():
    """Serves the main web interface."""
    return FileResponse('static/index.html')

@app.get("/stats")
def hardware_stats():
    sample = get_live_entropy(4)
    return {"hardware": "Healthy" if sample else "Offline", "entropy": sample.hex() if sample else None}

@app.get("/release/{file_id}")
def release_key(file_id: str, x_api_token: str = Header(None)):
    """Secure key release for the Web Portal."""
    if not MASTER_TOKEN or x_api_token != MASTER_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized Handshake")
    
    if not os.path.exists(VAULT_DB):
        raise HTTPException(status_code=500, detail="Vault database missing")
        
    with open(VAULT_DB, "r") as f:
        vault = json.load(f)
    
    clean_id = file_id.strip().upper()
    if clean_id in vault:
        return {"file_id": clean_id, "key": vault[clean_id]["quantum_key"], "status": "Success"}
    
    raise HTTPException(status_code=404, detail="File ID not found")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
