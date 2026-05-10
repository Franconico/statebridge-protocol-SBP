"""
Roaming Token — stdlib-only HS256 JWT implementation.

No PyJWT or cryptography library dependency. Uses Python's built-in
hmac and hashlib modules for signing and verification.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = 4 - len(s) % 4
    return base64.urlsafe_b64decode(s + "=" * (pad % 4))


def sign_token(payload: dict, secret: str) -> str:
    """Create a compact HS256 JWT."""
    header = _b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    body = _b64url(json.dumps(payload).encode())
    msg = f"{header}.{body}".encode()
    sig = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64url(sig)}"


def verify_token(token: str, secret: str) -> dict:
    """
    Verify an HS256 JWT and return its payload.
    Raises ValueError on signature failure or expiry.
    """
    try:
        header_b64, body_b64, sig_b64 = token.split(".")
    except ValueError:
        raise ValueError("Malformed token: expected three dot-separated segments")

    msg = f"{header_b64}.{body_b64}".encode()
    expected = hmac.new(secret.encode(), msg, hashlib.sha256).digest()
    actual = _b64url_decode(sig_b64)

    if not hmac.compare_digest(expected, actual):
        raise ValueError("Token signature invalid")

    payload = json.loads(_b64url_decode(body_b64))
    exp = payload.get("exp", 0)
    if datetime.now(UTC).timestamp() > exp:
        raise ValueError("Token has expired")

    return payload


def bundle_hash(bundle: dict) -> str:
    """SHA-256 over deterministically serialised bundle for integrity checks."""
    raw = json.dumps(bundle, sort_keys=True).encode()
    return hashlib.sha256(raw).hexdigest()
