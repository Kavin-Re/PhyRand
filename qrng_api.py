import os, json, serial, secrets, base64
from fastapi import FastAPI, Header, HTTPException
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from datetime import datetime
from dotenv import load_dotenv

# --- INITIALIZATION ---
load_dotenv() 
app = FastAPI()

# --- CONFIGURATION FROM .ENV ---
MASTER_TOKEN = os.getenv("VAULT_MASTER_TOKEN", "password")
PORT = os.getenv("QRNG_SERIAL_PORT", "/dev/quantum_qrng")

VAULT_DIR = os.path.join(os.getcwd(), "vault")
VAULT_FILE = os.path.join(VAULT_DIR, "quantum_vault.json")

if not os.path.exists(VAULT_DIR):
    os.makedirs(VAULT_DIR)
if not os.path.exists(VAULT_FILE):
    with open(VAULT_FILE, 'w') as f: json.dump({}, f)

def get_vault():
    with open(VAULT_FILE, 'r') as f: return json.load(f)

def save_vault(data):
    with open(VAULT_FILE, 'w') as f: json.dump(data, f, indent=4)

# --- ROUTES ---

@app.get("/heartbeat")
async def heartbeat():
    status = "ONLINE" if os.path.exists(PORT) else "OFFLINE"
    sample = "----"
    if status == "ONLINE":
        try:
            with serial.Serial(PORT, 115200, timeout=0.1) as ser:
                sample = ser.read(8).hex()
        except: status = "ERROR"
    return {"status": status, "sample": sample}

@app.get("/vault/list")
async def list_vault(x_api_token: str = Header(None)):
    # Security Comparison
    if x_api_token != MASTER_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized Access Attempt")
    return get_vault()

@app.get("/request-keys")
async def request_keys(x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    key = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()
    file_id = secrets.token_hex(3).upper() 
    return {"key": key, "file_id": file_id}

class CommitRequest(BaseModel):
    file_id: str
    key: str
    extension: str

@app.post("/vault/commit")
async def commit_vault(data: CommitRequest, x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    vault = get_vault()
    vault[data.file_id] = {
        "quantum_key": data.key,
        "extension": data.extension,
        "timestamp": datetime.now().isoformat()
    }
    save_vault(vault)
    return {"status": "committed"}

@app.delete("/vault/revoke/{file_id}")
async def revoke_key(file_id: str, x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    vault = get_vault()
    if file_id in vault:
        del vault[file_id]
        save_vault(vault)
    return {"status": "revoked"}

@app.get("/release/{file_id}")
async def release_key(file_id: str, x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    vault = get_vault()
    if file_id not in vault: raise HTTPException(status_code=404)
    return {"key": vault[file_id].get("quantum_key", ""), "extension": vault[file_id].get("extension", "bin")}

app.mount("/", StaticFiles(directory="static", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
