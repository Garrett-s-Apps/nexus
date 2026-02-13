"""
RSA key pair management for JWT signing.

Generates keys on first use, stores in ~/.nexus/keys/.
Rotation tracked by creation timestamp in key metadata.
"""

import json
import logging
import os
import time

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.config import NEXUS_DIR

logger = logging.getLogger("nexus.key_manager")

KEYS_DIR = os.path.join(NEXUS_DIR, "keys")
PRIVATE_KEY_PATH = os.path.join(KEYS_DIR, "nexus_private.pem")
PUBLIC_KEY_PATH = os.path.join(KEYS_DIR, "nexus_public.pem")
META_PATH = os.path.join(KEYS_DIR, "key_meta.json")

ROTATION_INTERVAL_SECONDS = 30 * 24 * 3600


def _ensure_keys_dir():
    os.makedirs(KEYS_DIR, mode=0o700, exist_ok=True)


def _generate_key_pair():
    """Generate a fresh RSA-2048 key pair and persist to disk."""
    _ensure_keys_dir()

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    fd = os.open(PRIVATE_KEY_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "wb") as f:
        f.write(private_pem)

    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    with open(PUBLIC_KEY_PATH, "wb") as f:
        f.write(public_pem)

    meta = {"created_at": time.time(), "algorithm": "RS256", "key_size": 2048}
    with open(META_PATH, "w") as f:
        json.dump(meta, f, indent=2)

    logger.info("Generated new RSA key pair at %s", KEYS_DIR)
    return private_key


def _should_rotate() -> bool:
    """Check if keys are older than the rotation interval."""
    if not os.path.exists(META_PATH):
        return True
    try:
        with open(META_PATH) as f:
            meta = json.load(f)
        age = time.time() - meta.get("created_at", 0)
        return bool(age > ROTATION_INTERVAL_SECONDS)
    except (json.JSONDecodeError, OSError):
        return True


def get_private_key() -> rsa.RSAPrivateKey:
    """Load or generate the RSA private key, rotating if stale."""
    if _should_rotate() or not os.path.exists(PRIVATE_KEY_PATH):
        return _generate_key_pair()  # type: ignore[return-value, no-any-return]

    with open(PRIVATE_KEY_PATH, "rb") as f:
        return serialization.load_pem_private_key(f.read(), password=None)  # type: ignore[return-value]


def get_public_key() -> rsa.RSAPublicKey:
    """Load or generate the RSA public key."""
    if not os.path.exists(PUBLIC_KEY_PATH):
        _generate_key_pair()

    with open(PUBLIC_KEY_PATH, "rb") as f:
        return serialization.load_pem_public_key(f.read())  # type: ignore[return-value]
