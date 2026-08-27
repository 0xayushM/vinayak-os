"""
api/routes/auth.py
───────────────────
Platform authentication routes for Vinayak Brain OS.

Endpoints:
  POST /auth/login       — verify email+password, issue httpOnly JWT cookie
  POST /auth/logout      — clear JWT cookie
  GET  /auth/me          — return current user from cookie

JWT is issued as an httpOnly, Secure, SameSite=Strict cookie so it is never
accessible to client-side JavaScript.

For Phase 1 (single-tenant KBrushes), we use a simple shared secret approach.
Replace with a proper user table lookup in Phase 2.
"""
from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from typing import Optional

import psycopg2
from fastapi import APIRouter, Cookie, HTTPException, Request, Response, status
from passlib.context import CryptContext
from pydantic import BaseModel
from jose import JWTError, jwt

from vinayak.config import DATABASE_URL, SUPABASE_JWT_SECRET, SUPABASE_URL

logger = logging.getLogger(__name__)

router = APIRouter()

# ── JWT config ────────────────────────────────────────────────────────────────
# Fail hard if JWT_SECRET is missing: a guessable default would let anyone
# forge session tokens. In dev mode (VINAYAK_DEV_MODE=1) we fall back to a
# random ephemeral secret — safe, but sessions won't survive a restart.
from vinayak.config import DEV_MODE

JWT_SECRET = os.environ.get("JWT_SECRET", "")
if not JWT_SECRET:
    if DEV_MODE:
        import secrets as _secrets
        JWT_SECRET = _secrets.token_urlsafe(48)
        logging.getLogger(__name__).warning(
            "JWT_SECRET not set — using a random ephemeral secret (dev mode). "
            "Sessions will not survive a restart."
        )
    else:
        raise RuntimeError(
            "JWT_SECRET is not set. Refusing to start with an insecure default. "
            "Set JWT_SECRET in the environment (or VINAYAK_DEV_MODE=1 for local dev)."
        )
JWT_ALGORITHM = "HS256"
JWT_TTL_SECS  = 60 * 60 * 8  # 8 hours

# ── Internal API key (service-to-service) ─────────────────────────────────────
# Next.js BFF routes send this header; any request without it to private
# endpoints is rejected. Like JWT_SECRET, it is required outside dev mode —
# without it, the backend would silently accept requests that bypass the BFF.
INTERNAL_KEY = os.environ.get("INTERNAL_API_KEY", "")
if not INTERNAL_KEY and not DEV_MODE:
    raise RuntimeError(
        "INTERNAL_API_KEY is not set. Refusing to start with the BFF boundary "
        "unenforced. Set INTERNAL_API_KEY (or VINAYAK_DEV_MODE=1 for local dev)."
    )

COOKIE_NAME = "vb_access_token"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# ── Schemas ───────────────────────────────────────────────────────────────────
class LoginRequest(BaseModel):
    email: str
    password: str


class TokenPayload(BaseModel):
    sub: str          # user email
    company_id: str
    exp: float
    user_id: Optional[str] = None   # Supabase auth.users uuid (Supabase mode only)


# ── Supabase mode ─────────────────────────────────────────────────────────────
# When SUPABASE_JWT_SECRET is set, Supabase (GoTrue) owns login/passwords/sessions
# and issues the access token; the backend only VERIFIES it and maps the user's
# email → company_id via the existing `users` table (now purely a profile/mapping
# table — the password_hash column is no longer consulted). The frontend forwards
# the Supabase access token as `Authorization: Bearer <token>`.
SUPABASE_MODE = bool(SUPABASE_JWT_SECRET)


def _bearer_token(request: Request) -> Optional[str]:
    """The Supabase access token from the Authorization header (BFF forwards it),
    falling back to a Supabase/legacy cookie if present."""
    header = request.headers.get("Authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return request.cookies.get("sb-access-token") or request.cookies.get(COOKIE_NAME)


# Supabase signs access tokens either with the project's shared HS256 secret
# (legacy) or with asymmetric signing keys (ES256/RS256) published as JWKS. The
# token header says which, so both are supported without extra configuration.
SUPABASE_JWKS_URL = (
    f"{SUPABASE_URL.rstrip('/')}/auth/v1/.well-known/jwks.json" if SUPABASE_URL else ""
)
_ASYMMETRIC_ALGS = ("RS256", "RS512", "ES256", "ES512", "EdDSA")
_JWKS_TTL_SECS   = 600
_jwks_by_kid: dict[str, dict] = {}
_jwks_fetched_at = 0.0


def _supabase_jwks(force: bool = False) -> dict[str, dict]:
    """kid → JWK for the project's public signing keys, cached for 10 minutes."""
    global _jwks_fetched_at
    if not SUPABASE_JWKS_URL:
        return {}
    if _jwks_by_kid and not force and (time.time() - _jwks_fetched_at) < _JWKS_TTL_SECS:
        return _jwks_by_kid

    import httpx
    try:
        resp = httpx.get(SUPABASE_JWKS_URL, timeout=5.0)
        resp.raise_for_status()
        keys = resp.json().get("keys", [])
    except Exception as exc:  # network/JSON errors — keep serving with the cache
        logger.warning("Could not fetch Supabase JWKS from %s: %s", SUPABASE_JWKS_URL, exc)
        return _jwks_by_kid

    _jwks_by_kid.clear()
    _jwks_by_kid.update({k["kid"]: k for k in keys if k.get("kid")})
    _jwks_fetched_at = time.time()
    return _jwks_by_kid


def _verify_supabase_jwt(token: str) -> dict:
    """Verify a Supabase-issued access token (aud='authenticated')."""
    try:
        header = jwt.get_unverified_header(token)
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Malformed Supabase token: {exc}")

    alg = header.get("alg", "")
    if alg in _ASYMMETRIC_ALGS:
        kid = header.get("kid", "")
        key = _supabase_jwks().get(kid)
        if key is None:  # key rotated since we cached — refetch once
            key = _supabase_jwks(force=True).get(kid)
        if key is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail=f"Unknown Supabase signing key: {kid or '<none>'}")
        secret, algorithms = key, [alg]
    else:
        if not SUPABASE_JWT_SECRET:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="No Supabase JWT secret configured for HS256 tokens")
        secret, algorithms = SUPABASE_JWT_SECRET, ["HS256"]

    try:
        return jwt.decode(token, secret, algorithms=algorithms, audience="authenticated")
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail=f"Invalid or expired Supabase token: {exc}")


def _resolve_company(email: str) -> str:
    """Map an authenticated email → its company_id via the users profile table.
    Empty string = global admin (workspace then resolved from X-Workspace-Id)."""
    if not email:
        return ""
    from vinayak.db.session import db
    conn = db.connect()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT company_id FROM users WHERE LOWER(email) = LOWER(%s)", (email,))
            row = cur.fetchone()
    finally:
        conn.close()
    return (row[0] if row else "") or ""


# ── Helpers ───────────────────────────────────────────────────────────────────
def _issue_jwt(email: str, company_id: str) -> str:
    payload = {
        "sub": email,
        "company_id": company_id,
        "iat": time.time(),
        "exp": time.time() + JWT_TTL_SECS,
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def _verify_jwt(token: str) -> TokenPayload:
    try:
        data = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return TokenPayload(**data)
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
        )


def get_current_user(request: Request) -> TokenPayload:
    """FastAPI dependency — resolve the authenticated user.

    • Supabase mode (SUPABASE_JWT_SECRET set): verify the Supabase access token
      (Bearer header) and map email → company_id.
    • Legacy mode: verify the platform JWT from the httpOnly cookie.
    """
    if SUPABASE_MODE:
        token = _bearer_token(request)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                                detail="Not authenticated")
        claims = _verify_supabase_jwt(token)
        email = (claims.get("email") or "").strip()
        return TokenPayload(sub=email, company_id=_resolve_company(email),
                            exp=float(claims.get("exp", 0)), user_id=claims.get("sub"))

    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Not authenticated")
    return _verify_jwt(token)


def require_internal_key(request: Request) -> None:
    """FastAPI dependency — reject requests without the internal API key."""
    if not INTERNAL_KEY:
        return  # only reachable in dev mode (startup fails otherwise)
    import hmac
    provided = request.headers.get("X-Internal-Key", "")
    if not hmac.compare_digest(provided, INTERNAL_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Missing or invalid internal API key",
        )


# ── Routes ────────────────────────────────────────────────────────────────────
@router.post("/login", summary="Issue platform JWT as httpOnly cookie (legacy)")
def login(req: LoginRequest, response: Response):
    """
    Legacy email+password login. In Supabase mode this endpoint is disabled —
    the frontend authenticates directly with Supabase (signInWithPassword) and
    the backend only verifies the resulting token.
    """
    if SUPABASE_MODE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Login is handled by Supabase Auth on the client; this endpoint is disabled.",
        )
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT password_hash, company_id FROM users WHERE LOWER(email) = LOWER(%s)",
                (req.email,),
            )
            row = cur.fetchone()
    finally:
        conn.close()

    if not row or not row[0]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    password_hash, company_id = row

    if not pwd_context.verify(req.password, password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    company_id = company_id or ""  # empty = global admin; workspace resolved from X-Workspace-Id header
    token = _issue_jwt(req.email, company_id)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=True,          # HTTPS only
        samesite="strict",
        max_age=JWT_TTL_SECS,
        path="/",
    )
    logger.info("Login successful for %s", req.email)
    return {
        "status": "ok",
        "email": req.email,
        "company_id": company_id,
        "expires_at": datetime.fromtimestamp(
            time.time() + JWT_TTL_SECS, tz=timezone.utc
        ).isoformat(),
    }


@router.post("/logout", summary="Clear the platform JWT cookie")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"status": "ok"}


@router.get("/me", summary="Return current user info from JWT")
def me(user: TokenPayload = __import__("fastapi").Depends(get_current_user)):
    return {
        "email":      user.sub,
        "company_id": user.company_id,
    }
