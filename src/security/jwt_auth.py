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
import uuid

import jwt as pyjwt

from src.security.audit_log import log_jwt_event
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
        "iss": "nexus-server",
        "aud": ["nexus-dashboard", "nexus-api"],
        "iat": now,
        "exp": now + TOKEN_TTL_SECONDS,
        "jti": str(uuid.uuid4()),
        "data_hash": data_hash,
    }

    private_key = get_private_key()
    token = str(pyjwt.encode(payload, private_key, algorithm=ALGORITHM))

    # Log JWT signing (SEC-015)
    log_jwt_event(
        event="signed",
        details={
            "algorithm": ALGORITHM,
            "ttl_seconds": TOKEN_TTL_SECONDS,
            "jti": payload["jti"],
        },
    )

    return token


def verify_token(token: str, data: dict | list | str) -> bool:
    """Verify a JWT and confirm the data hash matches the provided payload."""
    try:
        public_key = get_public_key()
        decoded = pyjwt.decode(
            token,
            public_key,
            algorithms=[ALGORITHM],
            audience="nexus-dashboard",
            issuer="nexus-server"
        )

        body = json.dumps(data, sort_keys=True, default=str)
        expected_hash = hashlib.sha256(body.encode()).hexdigest()

        is_valid = bool(decoded.get("data_hash") == expected_hash)

        # Log JWT verification (SEC-015)
        log_jwt_event(
            event="verified",
            details={
                "algorithm": ALGORITHM,
                "jti": decoded.get("jti"),
                "valid": is_valid,
            },
        )

        return is_valid
    except pyjwt.ExpiredSignatureError:
        logger.warning("JWT expired")
        # Log JWT verification failure (SEC-015)
        log_jwt_event(
            event="verify_failed",
            details={"reason": "expired_signature"},
        )
        return False
    except pyjwt.InvalidTokenError as e:
        logger.warning("JWT verification failed: %s", e)
        # Log JWT verification failure (SEC-015)
        log_jwt_event(
            event="verify_failed",
            details={"reason": str(e)},
        )
        return False
