# Context-Aware Geo QR Verification

A beginner-friendly FastAPI + SQLite project that creates short-lived QR tokens for registered locations, checks submitted coordinates against a geofence radius, and stores verification results.

> **Important:** this is an educational prototype, not proof of physical presence. GPS coordinates submitted by a client can be spoofed. Do not use it to make high-stakes attendance, security, payment, or access-control decisions without a security review.

## Features

- Register locations with latitude, longitude, and permitted radius.
- Generate cryptographically random QR tokens with configurable expiry (1–1,440 minutes).
- QR codes contain only the opaque token, not coordinates.
- Check token expiry and distance using the Haversine formula.
- Consume a token on its first verification attempt to reduce simple replay/reuse.
- Record accepted/rejected results in SQLite.
- Health-check endpoint and interactive API documentation.
- Windows launch scripts automate virtual-environment creation, dependency installation, and startup.
- Existing v1.0 database files are migrated automatically to add the token-use field.

## Quick start (Windows 10/11)

1. Extract this ZIP to a folder such as `C:\Projects\context-aware-geo-qr-verification`.
2. Install Python 3.10 or newer and make sure the Python launcher `py` works in PowerShell.
3. Double-click `run_windows.bat`, or open PowerShell in the project folder and run:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\run_windows.ps1
   ```

4. When startup finishes, open <http://127.0.0.1:8000/docs>.
5. Keep the terminal open while using the API. Press `Ctrl+C` to stop the server.

You can also install manually:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
python -m uvicorn app:app --reload
```

## Demo workflow

### 1. Check the service

Open <http://127.0.0.1:8000/health>. Expected response:

```json
{"status":"ok","database":"connected"}
```

### 2. Register a demo location

Use `POST /locations` in Swagger with:

```json
{
  "name": "Campus Gate",
  "latitude": 17.385,
  "longitude": 78.4867,
  "allowed_radius_m": 200
}
```

Copy the returned `location_id`.

### 3. Generate a QR token

Use `POST /tokens`:

```json
{
  "location_id": 1,
  "valid_minutes": 60
}
```

Replace `1` with the ID returned by the previous step. Copy the returned token.

### 4. View the QR image

Open the returned `qr_image_endpoint` relative to `http://127.0.0.1:8000`, for example:

`http://127.0.0.1:8000/tokens/PASTE_TOKEN_HERE/qr`

### 5. Verify once

Use `POST /verify` with the token and coordinates close to the registered location:

```json
{
  "token": "PASTE_TOKEN_HERE",
  "latitude": 17.3851,
  "longitude": 78.4868
}
```

A successful verification returns `"result": "accepted"`. The first verification attempt consumes the token—even if the attempt is rejected—so generate a new token for another test. A second attempt with the same token is rejected.

### 6. Review logs

- `GET /verifications` — most recent verification records (limit can be 1–100).
- `GET /locations` — registered locations.

## Project structure

```text
context-aware-geo-qr-verification/
├── app.py                 # API, validation, SQLite, QR generation, geofence checks
├── requirements.txt        # Python dependencies
├── run_windows.bat         # One-click Windows setup/start
├── run_windows.ps1         # PowerShell setup/start
├── .gitignore              # Excludes local environment, database, and QR output
├── .env.example            # Placeholder for future environment settings
├── tests/
│   └── test_app.py         # Basic automated tests
├── scripts/
│   └── smoke_test.py       # Quick service check while API is running
└── README.md
```

Runtime-generated files (`geo_qr_demo.db`, `qr_codes/`, and `.venv/`) are intentionally not included in source control or this ZIP.

## Tests

After installing dependencies:

```powershell
python -m unittest discover -s tests -v
```

With the server running, check the live service:

```powershell
python scripts/smoke_test.py
```

## Security limitations and next steps

This prototype does **not** include user accounts, role-based authorization, HTTPS deployment, server-side proof of device location, signed device attestation, or comprehensive abuse/rate limiting. QR tokens are one-time-use, but a malicious client can still fake submitted GPS coordinates or relay a QR code to another person. Production use needs a threat model, authentication/authorization, HTTPS, monitoring, secure deployment, privacy/retention controls, and independent security testing.
