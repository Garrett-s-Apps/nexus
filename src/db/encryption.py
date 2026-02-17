"""
Database encryption key derivation for SQLCipher.

Derives a per-installation encryption key from a master secret using
PBKDF2-HMAC-SHA256. The salt is stored in ~/.nexus/.db_salt and created
on first use.

Usage:
    from src.db.encryption import get_db_encryption_key
    key = get_db_encryption_key()  # returns base64-encoded 256-bit key

Requires:
    NEXUS_MASTER_SECRET environment variable (or ~/.nexus/.env.keys entry)
"""

import base64
import logging
import os
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from src.config import NEXUS_DIR

logger = logging.getLogger("nexus.db.encryption")

_SALT_PATH = Path(NEXUS_DIR) / ".db_salt"
_KDF_ITERATIONS = 480_000
_KEY_LENGTH = 32  # 256-bit key


def _get_master_secret() -> str:
    """Retrieve the master secret from environment or keys file.

    Checks NEXUS_MASTER_SECRET env var first, then falls back to the
    keys file at ~/.nexus/.env.keys.

    Raises:
        ValueError: If no master secret is configured.
    """
    secret = os.environ.get("NEXUS_MASTER_SECRET")
    if secret:
        return secret

    # Fall back to keys file
    from src.config import get_key
    secret = get_key("NEXUS_MASTER_SECRET")
    if secret:
        return secret

    raise ValueError(
        "NEXUS_MASTER_SECRET environment variable is required for database "
        "encryption. Set it in your environment or in ~/.nexus/.env.keys"
    )


def _get_or_create_salt() -> bytes:
    """Get existing salt or create a new one.

    The salt file is stored at ~/.nexus/.db_salt with 0600 permissions.
    """
    if _SALT_PATH.exists():
        return _SALT_PATH.read_bytes()

    # Create new salt
    os.makedirs(_SALT_PATH.parent, exist_ok=True)
    salt = os.urandom(32)
    _SALT_PATH.write_bytes(salt)
    try:
        os.chmod(_SALT_PATH, 0o600)
    except OSError:
        logger.warning("Could not set restrictive permissions on %s", _SALT_PATH)
    logger.info("Created new database encryption salt at %s", _SALT_PATH)
    return salt


def get_db_encryption_key() -> str:
    """Derive the database encryption key from the master secret.

    Returns:
        Base64-encoded 256-bit key suitable for SQLCipher PRAGMA key.

    Raises:
        ValueError: If NEXUS_MASTER_SECRET is not configured.
    """
    master_secret = _get_master_secret()
    salt = _get_or_create_salt()

    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=_KEY_LENGTH,
        salt=salt,
        iterations=_KDF_ITERATIONS,
    )
    derived = kdf.derive(master_secret.encode())
    return base64.b64encode(derived).decode()


def is_encryption_available() -> bool:
    """Check whether encryption can be configured (master secret is set).

    Returns False instead of raising if the secret is missing, allowing
    callers to fall back to unencrypted mode during development/testing.
    """
    try:
        _get_master_secret()
        return True
    except ValueError:
        return False
