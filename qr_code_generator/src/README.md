# QR Code Generator Prototype

FastAPI implementation for the dynamic QR code generator spec.

## Run

```bash
cd qr_code_generator/src
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

The local SQLite database defaults to `qr_code.db` in the current working directory.
