"""Context-aware Geo QR verification API (educational prototype)."""
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
import math
import re
import secrets
import sqlite3
from typing import Iterator

import qrcode
from fastapi import FastAPI, HTTPException, Path as ApiPath
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, ConfigDict

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "geo_qr_demo.db"
QR_DIR = BASE_DIR / "qr_codes"
QR_DIR.mkdir(parents=True, exist_ok=True)
TOKEN_PATTERN = re.compile(r"^[A-Za-z0-9_-]{20,100}$")

app = FastAPI(
    title="Context-Aware Geo QR Verification Service",
    description=(
        "Educational API for short-lived QR tokens and location-radius checks. "
        "Client-submitted GPS coordinates are not trusted proof of physical presence."
    ),
    version="1.1.0",
)

SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS locations (
    location_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    latitude REAL NOT NULL CHECK(latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK(longitude BETWEEN -180 AND 180),
    allowed_radius_m REAL NOT NULL CHECK(allowed_radius_m > 0)
);
CREATE TABLE IF NOT EXISTS tokens (
    token TEXT PRIMARY KEY,
    location_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used_at TEXT,
    FOREIGN KEY(location_id) REFERENCES locations(location_id)
);
CREATE TABLE IF NOT EXISTS verifications (
    verification_id INTEGER PRIMARY KEY AUTOINCREMENT,
    token TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    submitted_latitude REAL NOT NULL,
    submitted_longitude REAL NOT NULL,
    distance_m REAL,
    result TEXT NOT NULL CHECK(result IN ('accepted', 'rejected')),
    reason TEXT NOT NULL,
    FOREIGN KEY(token) REFERENCES tokens(token)
);
CREATE INDEX IF NOT EXISTS idx_tokens_location_id ON tokens(location_id);
CREATE INDEX IF NOT EXISTS idx_verifications_checked_at ON verifications(checked_at);
"""


@contextmanager
def db() -> Iterator[sqlite3.Connection]:
    """Open a connection and always commit/rollback and close it safely."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db() -> None:
    with db() as conn:
        conn.executescript(SCHEMA)
        # Migrate databases created by v1.0.0 without destroying existing data.
        token_columns = {row["name"] for row in conn.execute("PRAGMA table_info(tokens)")}
        if "used_at" not in token_columns:
            conn.execute("ALTER TABLE tokens ADD COLUMN used_at TEXT")


init_db()


class LocationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    allowed_radius_m: float = Field(gt=0, le=5000, allow_inf_nan=False)


class TokenCreate(BaseModel):
    location_id: int = Field(gt=0)
    valid_minutes: int = Field(default=60, ge=1, le=1440)


class VerifyRequest(BaseModel):
    token: str = Field(min_length=20, max_length=100)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return great-circle distance in metres using the Haversine formula."""
    earth_radius_m = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    # Clamp against tiny floating-point overshoots outside [0, 1].
    a = min(1.0, max(0.0, a))
    return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def validate_token(token: str) -> None:
    if not TOKEN_PATTERN.fullmatch(token):
        raise HTTPException(status_code=404, detail="QR token not found")


@app.get("/", tags=["System"])
def home():
    return {
        "message": "Geo QR Verification API is running",
        "version": app.version,
        "docs": "/docs",
        "health": "/health",
        "warning": "Educational prototype only; submitted GPS coordinates can be spoofed.",
    }


@app.get("/health", tags=["System"])
def health():
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok", "database": "connected"}


@app.post("/locations", status_code=201, tags=["Locations"])
def create_location(payload: LocationCreate):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Location name cannot be blank")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO locations(name, latitude, longitude, allowed_radius_m) VALUES(?,?,?,?)",
            (name, payload.latitude, payload.longitude, payload.allowed_radius_m),
        )
        location_id = cur.lastrowid
    return {"location_id": location_id, "name": name, "latitude": payload.latitude,
            "longitude": payload.longitude, "allowed_radius_m": payload.allowed_radius_m}


@app.get("/locations", tags=["Locations"])
def list_locations():
    with db() as conn:
        rows = conn.execute(
            "SELECT location_id, name, latitude, longitude, allowed_radius_m "
            "FROM locations ORDER BY location_id DESC"
        ).fetchall()
    return [dict(row) for row in rows]


@app.post("/tokens", status_code=201, tags=["Tokens"])
def create_token(payload: TokenCreate):
    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=payload.valid_minutes)
    token = secrets.token_urlsafe(32)
    with db() as conn:
        location = conn.execute(
            "SELECT location_id FROM locations WHERE location_id = ?", (payload.location_id,)
        ).fetchone()
        if location is None:
            raise HTTPException(status_code=404, detail="Location not found")
        conn.execute(
            "INSERT INTO tokens(token, location_id, created_at, expires_at, used_at) VALUES(?,?,?,?,NULL)",
            (token, payload.location_id, now.isoformat(), expires.isoformat()),
        )
    # QR contains only the opaque random token, never the coordinates.
    image_path = QR_DIR / f"{token}.png"
    qrcode.make(token).save(image_path)
    return {
        "token": token,
        "location_id": payload.location_id,
        "created_at": now.isoformat(),
        "expires_at": expires.isoformat(),
        "single_use": True,
        "qr_image_endpoint": f"/tokens/{token}/qr",
    }


@app.get("/tokens/{token}/qr", tags=["Tokens"])
def get_qr(token: str = ApiPath(min_length=20, max_length=100)):
    validate_token(token)
    path = QR_DIR / f"{token}.png"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="QR image not found")
    return FileResponse(path, media_type="image/png", filename="verification-qr.png")


@app.post("/verify", tags=["Verification"])
def verify(payload: VerifyRequest):
    now = datetime.now(timezone.utc)
    with db() as conn:
        # BEGIN IMMEDIATE serializes competing attempts so a token cannot be accepted twice.
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            """SELECT t.token, t.expires_at, t.used_at, l.latitude, l.longitude, l.allowed_radius_m
               FROM tokens t JOIN locations l ON l.location_id = t.location_id
               WHERE t.token = ?""",
            (payload.token,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Unknown token")

        expires = datetime.fromisoformat(row["expires_at"])
        dist = distance_m(row["latitude"], row["longitude"], payload.latitude, payload.longitude)
        if row["used_at"] is not None:
            result, reason = "rejected", "Token has already been used"
        elif now > expires:
            result, reason = "rejected", "Token expired"
        elif dist > row["allowed_radius_m"]:
            result, reason = "rejected", "Outside allowed location radius"
        else:
            result, reason = "accepted", "Token is valid and location is within radius"

        # Consume any known token on the first verification attempt, including a failed
        # location/expiry check, to make the token one-time-use and reduce replay attempts.
        if row["used_at"] is None:
            conn.execute("UPDATE tokens SET used_at = ? WHERE token = ? AND used_at IS NULL",
                         (now.isoformat(), payload.token))
        conn.execute(
            """INSERT INTO verifications(token, checked_at, submitted_latitude,
               submitted_longitude, distance_m, result, reason) VALUES(?,?,?,?,?,?,?)""",
            (payload.token, now.isoformat(), payload.latitude, payload.longitude, dist, result, reason),
        )

    return {
        "result": result,
        "reason": reason,
        "distance_m": round(dist, 2),
        "allowed_radius_m": row["allowed_radius_m"],
        "checked_at": now.isoformat(),
        "token_single_use": True,
    }


@app.get("/verifications", tags=["Verification"])
def list_verifications(limit: int = 50):
    limit = max(1, min(limit, 100))
    with db() as conn:
        rows = conn.execute(
            """SELECT verification_id, token, checked_at, submitted_latitude,
                      submitted_longitude, distance_m, result, reason
               FROM verifications ORDER BY verification_id DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(row) for row in rows]
