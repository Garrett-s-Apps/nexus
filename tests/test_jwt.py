"""Tests for JWT signing and key management."""

import os

import pytest

from src.security.jwt_auth import sign_response, verify_token
from src.security.key_manager import (
    _generate_key_pair,
    _should_rotate,
    get_private_key,
    get_public_key,
)


@pytest.fixture(autouse=True)
def temp_keys(tmp_path, monkeypatch):
    """Redirect key storage to a temp directory."""
    keys_dir = str(tmp_path / "keys")
    monkeypatch.setattr("src.security.key_manager.KEYS_DIR", keys_dir)
    monkeypatch.setattr("src.security.key_manager.PRIVATE_KEY_PATH", os.path.join(keys_dir, "nexus_private.pem"))
    monkeypatch.setattr("src.security.key_manager.PUBLIC_KEY_PATH", os.path.join(keys_dir, "nexus_public.pem"))
    monkeypatch.setattr("src.security.key_manager.META_PATH", os.path.join(keys_dir, "key_meta.json"))


class TestKeyManager:
    def test_generate_creates_files(self):
        _generate_key_pair()
        assert get_private_key() is not None
        assert get_public_key() is not None

    def test_get_private_key_returns_rsa_key(self):
        key = get_private_key()
        assert key is not None
        assert key.key_size == 2048

    def test_get_public_key_matches_private(self):
        priv = get_private_key()
        pub = get_public_key()
        # Verify they're a matching pair by checking public numbers
        assert priv.public_key().public_numbers() == pub.public_numbers()

    def test_should_rotate_true_when_no_meta(self):
        assert _should_rotate() is True

    def test_should_rotate_false_after_generation(self):
        _generate_key_pair()
        assert _should_rotate() is False


class TestJWTAuth:
    def test_sign_and_verify(self):
        data = {"status": "ok", "agents": 27}
        token = sign_response(data)
        assert isinstance(token, str)
        assert len(token) > 50
        assert verify_token(token, data) is True

    def test_verify_rejects_tampered_data(self):
        data = {"status": "ok"}
        token = sign_response(data)
        tampered = {"status": "compromised"}
        assert verify_token(token, tampered) is False

    def test_verify_rejects_garbage_token(self):
        assert verify_token("not.a.real.token", {"x": 1}) is False

    def test_sign_handles_list_payload(self):
        data = [{"id": 1}, {"id": 2}]
        token = sign_response(data)
        assert verify_token(token, data) is True

    def test_sign_handles_string_payload(self):
        data = "plain string response"
        token = sign_response(data)
        assert verify_token(token, data) is True

    def test_sign_includes_required_claims(self):
        import jwt as pyjwt
        data = {"test": True}
        token = sign_response(data)
        # Decode without verification to inspect claims
        decoded = pyjwt.decode(token, options={"verify_signature": False})
        assert decoded["sub"] == "nexus-api"
        assert "iat" in decoded
        assert "exp" in decoded
        assert "data_hash" in decoded
        assert decoded["exp"] - decoded["iat"] == 3600
