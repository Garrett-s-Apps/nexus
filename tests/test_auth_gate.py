"""Tests for the dashboard auth gate — passphrase, sessions, fingerprinting."""

import time
from unittest.mock import patch

import pytest

from src.security import auth_gate


@pytest.fixture(autouse=True)
def _reset_auth_state():
    """Clear session store and signing key between tests."""
    auth_gate._sessions.clear()
    auth_gate._signing_key = None
    yield
    auth_gate._sessions.clear()
    auth_gate._signing_key = None


@pytest.fixture
def passphrase():
    return "test-secret-phrase"


@pytest.fixture
def mock_passphrase(passphrase):
    with patch.object(auth_gate, "_get_passphrase", return_value=passphrase):
        yield passphrase


# ---- Passphrase verification ----

def test_verify_passphrase_correct(mock_passphrase):
    assert auth_gate.verify_passphrase(mock_passphrase) is True


def test_verify_passphrase_wrong(mock_passphrase):
    assert auth_gate.verify_passphrase("wrong-phrase") is False


def test_verify_passphrase_empty(mock_passphrase):
    assert auth_gate.verify_passphrase("") is False


# ---- Session creation and verification ----

def test_create_and_verify_session(mock_passphrase):
    ua = "Mozilla/5.0 TestBrowser"
    ip = "192.168.1.42"
    session_id = auth_gate.create_session(user_agent=ua, client_ip=ip)

    assert isinstance(session_id, str)
    assert "." in session_id
    assert auth_gate.verify_session(session_id, user_agent=ua, client_ip=ip) is True


def test_verify_session_none(mock_passphrase):
    assert auth_gate.verify_session(None) is False


def test_verify_session_empty_string(mock_passphrase):
    assert auth_gate.verify_session("") is False


def test_verify_session_garbage(mock_passphrase):
    assert auth_gate.verify_session("not-a-real-token") is False


def test_verify_session_fabricated_token(mock_passphrase):
    """Fabricated tokens that aren't in the session store must fail."""
    assert auth_gate.verify_session("faketoken.fakesig", user_agent="ua", client_ip="1.2.3.4") is False


# ---- Fingerprint binding (anti-substitution) ----

def test_session_rejected_from_different_ip(mock_passphrase):
    """Cookie stolen and replayed from a different IP must fail."""
    ua = "Mozilla/5.0"
    session_id = auth_gate.create_session(user_agent=ua, client_ip="10.0.0.1")
    assert auth_gate.verify_session(session_id, user_agent=ua, client_ip="10.0.0.1") is True
    # Same cookie, different IP — should be rejected
    assert auth_gate.verify_session(session_id, user_agent=ua, client_ip="10.0.0.99") is False


def test_session_rejected_from_different_user_agent(mock_passphrase):
    """Cookie replayed with a different User-Agent must fail."""
    ip = "10.0.0.1"
    session_id = auth_gate.create_session(user_agent="Chrome/120", client_ip=ip)
    assert auth_gate.verify_session(session_id, user_agent="Chrome/120", client_ip=ip) is True
    # Same cookie, different UA — should be rejected
    assert auth_gate.verify_session(session_id, user_agent="Firefox/119", client_ip=ip) is False


def test_session_rejected_after_fingerprint_mismatch_is_destroyed(mock_passphrase):
    """A fingerprint mismatch should destroy the session entirely."""
    session_id = auth_gate.create_session(user_agent="Chrome", client_ip="1.1.1.1")
    # Trigger mismatch
    auth_gate.verify_session(session_id, user_agent="Chrome", client_ip="2.2.2.2")
    # Now even the original client can't use it — session was invalidated
    assert auth_gate.verify_session(session_id, user_agent="Chrome", client_ip="1.1.1.1") is False


# ---- HMAC tamper resistance ----

def test_tampered_token_rejected(mock_passphrase):
    """Modifying any part of the cookie value must fail."""
    ua, ip = "TestUA", "10.0.0.1"
    session_id = auth_gate.create_session(user_agent=ua, client_ip=ip)
    token, sig = session_id.split(".", 1)

    # Tamper with token portion
    tampered = "AAAA" + token[4:] + "." + sig
    # Manually add to sessions dict to bypass lookup check
    auth_gate._sessions[tampered] = auth_gate._sessions[session_id].copy()
    assert auth_gate.verify_session(tampered, user_agent=ua, client_ip=ip) is False


def test_swapped_signature_rejected(mock_passphrase):
    """Swapping signatures between two sessions must fail."""
    ua, ip = "TestUA", "10.0.0.1"
    s1 = auth_gate.create_session(user_agent=ua, client_ip=ip)
    s2 = auth_gate.create_session(user_agent=ua, client_ip=ip)

    t1, sig1 = s1.split(".", 1)
    t2, sig2 = s2.split(".", 1)

    # Cross-wire: token from s1, signature from s2
    hybrid = f"{t1}.{sig2}"
    auth_gate._sessions[hybrid] = auth_gate._sessions[s1].copy()
    assert auth_gate.verify_session(hybrid, user_agent=ua, client_ip=ip) is False


# ---- Expiry ----

def test_expired_session_rejected(mock_passphrase):
    ua, ip = "TestUA", "10.0.0.1"
    session_id = auth_gate.create_session(user_agent=ua, client_ip=ip)
    # Fast-forward the expiry
    auth_gate._sessions[session_id]["expiry"] = time.time() - 1
    assert auth_gate.verify_session(session_id, user_agent=ua, client_ip=ip) is False
    # Session should be cleaned up
    assert session_id not in auth_gate._sessions


# ---- Logout ----

def test_invalidate_session(mock_passphrase):
    ua, ip = "TestUA", "10.0.0.1"
    session_id = auth_gate.create_session(user_agent=ua, client_ip=ip)
    assert auth_gate.verify_session(session_id, user_agent=ua, client_ip=ip) is True
    auth_gate.invalidate_session(session_id)
    assert auth_gate.verify_session(session_id, user_agent=ua, client_ip=ip) is False


def test_invalidate_nonexistent_session():
    """Invalidating a session that doesn't exist should not raise."""
    auth_gate.invalidate_session("does-not-exist.at-all")


# ---- Fingerprint computation ----

def test_fingerprint_deterministic():
    fp1 = auth_gate._compute_fingerprint("Chrome/120", "10.0.0.1")
    fp2 = auth_gate._compute_fingerprint("Chrome/120", "10.0.0.1")
    assert fp1 == fp2


def test_fingerprint_differs_by_ip():
    fp1 = auth_gate._compute_fingerprint("Chrome/120", "10.0.0.1")
    fp2 = auth_gate._compute_fingerprint("Chrome/120", "10.0.0.2")
    assert fp1 != fp2


def test_fingerprint_differs_by_ua():
    fp1 = auth_gate._compute_fingerprint("Chrome/120", "10.0.0.1")
    fp2 = auth_gate._compute_fingerprint("Firefox/119", "10.0.0.1")
    assert fp1 != fp2
