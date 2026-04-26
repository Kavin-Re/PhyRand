import serial, base64, os, json, uvicorn
from fastapi import FastAPI, HTTPException, Header, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()
app = FastAPI(title="Secure Exchange v4.0")

SERIAL_PORT = os.getenv("QRNG_SERIAL_PORT", "/dev/quantum_qrng")
MASTER_TOKEN = os.getenv("VAULT_MASTER_TOKEN")
VAULT_DB = "vault/quantum_vault.json"

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

def get_hardware_entropy(n=32):
    try:
        with serial.Serial(SERIAL_PORT, 115200, timeout=2) as ser:
            ser.reset_input_buffer()
            data = ser.read(n)
            return data if len(data) == n else None
    except: return None

@app.get("/")
async def serve_dashboard(): return FileResponse('static/index.html')

@app.get("/heartbeat")
def hardware_status():
    sample = get_hardware_entropy(4)
    return {"status": "ONLINE" if sample else "OFFLINE", "sample": sample.hex() if sample else None}

@app.get("/stats")
def get_system_stats(x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    sample = get_hardware_entropy(8)
    count = 0
    if os.path.exists(VAULT_DB):
        with open(VAULT_DB, "r") as f: count = len(json.load(f))
    return {"build": "v4.0-Production", "hardware": "ONLINE" if sample else "OFFLINE", "vault_records": count}

@app.get("/request-keys")
def request_keys(x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    entropy = get_hardware_entropy(32)
    if not entropy: raise HTTPException(status_code=503)
    new_id = base64.b32encode(os.urandom(5)).decode()[:6].upper()
    new_key = base64.urlsafe_b64encode(entropy).decode()
    return {"file_id": new_id, "key": new_key}

@app.post("/vault/commit")
def commit_record(data: dict = Body(...), x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    if not os.path.exists("vault"): os.mkdir("vault")
    vault = {}
    if os.path.exists(VAULT_DB):
        with open(VAULT_DB, "r") as f: vault = json.load(f)
    file_id = data.get("file_id")
    vault[file_id] = {"key": data.get("key"), "extension": data.get("extension"), "timestamp": data.get("timestamp")}
    with open(VAULT_DB, "w") as f: json.dump(vault, f, indent=4)
    return {"status": "success"}

@app.get("/vault/list")
def list_records(x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    if not os.path.exists(VAULT_DB): return {}
    with open(VAULT_DB, "r") as f: return json.load(f)

@app.delete("/vault/revoke/{file_id}")
def revoke_record(file_id: str, x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    with open(VAULT_DB, "r") as f: vault = json.load(f)
    if file_id.upper() in vault:
        del vault[file_id.upper()]
        with open(VAULT_DB, "w") as f: json.dump(vault, f, indent=4)
        return {"status": "revoked"}
    raise HTTPException(status_code=404)

@app.get("/release/{file_id}")
def release_metadata(file_id: str, x_api_token: str = Header(None)):
    if x_api_token != MASTER_TOKEN: raise HTTPException(status_code=401)
    with open(VAULT_DB, "r") as f: vault = json.load(f)
    if file_id.upper() in vault: return vault[file_id.upper()]
    raise HTTPException(status_code=404)

if __name__ == "__main__": uvicorn.run(app, host="0.0.0.0", port=8000)
