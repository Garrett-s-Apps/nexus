"""
JWT response signing for NEXUS API.

Signs outgoing responses with an RS256 JWT containing a SHA-256 hash of the
response body. This provides integrity verification — consumers can confirm
responses haven't been tampered with in transit.

Not access control (API is local-only). This is integrity attestation.
"""

import hashlib
import json
import logging
import time

import jwt as pyjwt

from src.security.key_manager import get_private_key, get_public_key

logger = logging.getLogger("nexus.jwt_auth")

ALGORITHM = "RS256"
TOKEN_TTL_SECONDS = 3600  # 1 hour


def sign_response(data: dict | list | str) -> str:
    """Create a JWT attesting to the integrity of a response payload.

    The token contains a SHA-256 hash of the canonical JSON representation,
    allowing consumers to verify the response body hasn't been modified.
    """
    body = json.dumps(data, sort_keys=True, default=str)
    data_hash = hashlib.sha256(body.encode()).hexdigest()

    now = int(time.time())
    payload = {
        "sub": "nexus-api",
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "data_hash": data_hash,
    }

    private_key = get_private_key()
    return str(pyjwt.encode(payload, private_key, algorithm=ALGORITHM))


def verify_token(token: str, data: dict | list | str) -> bool:
    """Verify a JWT and confirm the data hash matches the provided payload."""
    try:
        public_key = get_public_key()
        decoded = pyjwt.decode(token, public_key, algorithms=[ALGORITHM])

        body = json.dumps(data, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(body.encode()).hexdigest()

        return bool(decoded.get("data_hash") == expected_hash)
    except pyjwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        return False
    except pyjwt.InvalidTokenError as e:
        logger.warning("JWT verification failed: %s", e)
        return False
