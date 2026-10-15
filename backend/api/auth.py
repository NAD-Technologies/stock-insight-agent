import base64
import hashlib
import hmac
import json
import os
import time

import httpx
from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/api/auth")

SESSION_TTL = 30 * 24 * 3600
TOKENINFO_URL = "https://oauth2.googleapis.com/tokeninfo"


def _client_id() -> str:
    return os.getenv("GOOGLE_CLIENT_ID", "").strip()


def _secret() -> bytes:
    # Set SESSION_SECRET in production; otherwise sessions reset on every restart.
    s = os.getenv("SESSION_SECRET", "").strip()
    if not s:
        s = _secret.__dict__.setdefault("fallback", base64.b64encode(os.urandom(32)).decode())
    return s.encode()


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _sign(payload: dict) -> str:
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def _verify(token: str) -> dict | None:
    try:
        body, sig = token.split(".")
        good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, good):
            return None
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
        return data if data.get("exp", 0) > time.time() else None
    except Exception:  # noqa: BLE001
        return None


class GoogleLogin(BaseModel):
    credential: str


@router.get("/config")
async def config():
    cid = _client_id()
    return {"googleEnabled": bool(cid), "googleClientId": cid or None}


@router.post("/google")
async def google_login(body: GoogleLogin):
    cid = _client_id()
    if not cid:
        raise HTTPException(503, "Google sign-in is not configured (GOOGLE_CLIENT_ID missing)")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(TOKENINFO_URL, params={"id_token": body.credential})
    except httpx.HTTPError:
        raise HTTPException(502, "Could not reach Google to verify sign-in")
    if r.status_code != 200:
        raise HTTPException(401, "Invalid Google credential")
    info = r.json()
    if info.get("aud") != cid or info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise HTTPException(401, "Google credential was issued for a different app")
    if str(info.get("email_verified")).lower() != "true":
        raise HTTPException(401, "Google email is not verified")
    user = {"id": info["sub"], "email": info.get("email"), "name": info.get("name") or info.get("email"),
            "picture": info.get("picture")}
    return {"token": _sign({**user, "exp": int(time.time()) + SESSION_TTL}), "user": user}


@router.get("/me")
async def me(authorization: str = Header("")):
    data = _verify(authorization.removeprefix("Bearer ").strip())
    if not data:
        raise HTTPException(401, "Not signed in")
    return {"user": {k: data.get(k) for k in ("id", "email", "name", "picture")}}
