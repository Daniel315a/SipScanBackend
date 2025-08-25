from fastapi import FastAPI

app = FastAPI(title="SIPScan Backend")

@app.get("/health")
def health():
    return {"status": "ok"}