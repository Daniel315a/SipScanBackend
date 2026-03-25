"""Unit tests for auth_service._decode_and_check_expiry and validate_token."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch
from jwt import InvalidTokenError
from fastapi import HTTPException

import services.auth_service  # ensure module loaded before patching


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _future_fin(minutes=60) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _past_fin(minutes=60) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def _make_request(app_state=None):
    req = MagicMock()
    req.app.state = app_state or MagicMock()
    return req


def _make_credentials(token="some.jwt.token"):
    creds = MagicMock()
    creds.credentials = token
    return creds


# ---------------------------------------------------------------------------
# _decode_and_check_expiry — happy path
# ---------------------------------------------------------------------------

def test_decode_returns_payload_when_valid():
    """Returns the decoded payload when token is valid and not expired."""
    payload = {"id_usuario": 1, "fin": _future_fin()}

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import _decode_and_check_expiry
        result = _decode_and_check_expiry("valid.token")

    assert result == payload


def test_decode_decodes_with_hs256():
    """jwt.decode is called with HS256 algorithm."""
    payload = {"id_usuario": 1, "fin": _future_fin()}
    mock_decode = MagicMock(return_value=payload)

    with patch("services.auth_service.jwt.decode", mock_decode):
        from services.auth_service import _decode_and_check_expiry
        _decode_and_check_expiry("token")

    _, _, kwargs = mock_decode.mock_calls[0]
    assert "HS256" in kwargs.get("algorithms", [])


# ---------------------------------------------------------------------------
# _decode_and_check_expiry — invalid signature / malformed token
# ---------------------------------------------------------------------------

def test_decode_invalid_token_raises_401():
    """Raises HTTP 401 when jwt.decode raises InvalidTokenError."""
    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import _decode_and_check_expiry
        with pytest.raises(HTTPException) as exc:
            _decode_and_check_expiry("bad.token")

    assert exc.value.status_code == 401


def test_decode_invalid_token_detail():
    """Detail mentions 'invalid'."""
    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import _decode_and_check_expiry
        with pytest.raises(HTTPException) as exc:
            _decode_and_check_expiry("bad.token")

    assert "invalid" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# _decode_and_check_expiry — missing fin field
# ---------------------------------------------------------------------------

def test_decode_missing_fin_raises_401():
    """Raises HTTP 401 when payload has no 'fin' field."""
    with patch("services.auth_service.jwt.decode", return_value={"id_usuario": 1}):
        from services.auth_service import _decode_and_check_expiry
        with pytest.raises(HTTPException) as exc:
            _decode_and_check_expiry("token")

    assert exc.value.status_code == 401


def test_decode_missing_fin_detail():
    """Detail mentions the missing expiration field."""
    with patch("services.auth_service.jwt.decode", return_value={"id_usuario": 1}):
        from services.auth_service import _decode_and_check_expiry
        with pytest.raises(HTTPException) as exc:
            _decode_and_check_expiry("token")

    assert "expiration" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# _decode_and_check_expiry — expired fin
# ---------------------------------------------------------------------------

def test_decode_expired_fin_raises_401():
    """Raises HTTP 401 when fin is in the past."""
    payload = {"id_usuario": 1, "fin": _past_fin()}

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import _decode_and_check_expiry
        with pytest.raises(HTTPException) as exc:
            _decode_and_check_expiry("token")

    assert exc.value.status_code == 401


def test_decode_expired_fin_detail():
    """Detail mentions 'expired'."""
    payload = {"id_usuario": 1, "fin": _past_fin()}

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import _decode_and_check_expiry
        with pytest.raises(HTTPException) as exc:
            _decode_and_check_expiry("token")

    assert "expired" in exc.value.detail.lower()


def test_decode_fin_with_z_suffix_is_parsed():
    """Handles ISO 8601 strings ending in 'Z' (UTC indicator)."""
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    payload = {"id_usuario": 1, "fin": future}

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import _decode_and_check_expiry
        result = _decode_and_check_expiry("token")

    assert result == payload


# ---------------------------------------------------------------------------
# validate_token — delegates to _decode_and_check_expiry
# ---------------------------------------------------------------------------

def test_validate_token_returns_payload():
    """Returns the decoded payload on a valid token."""
    payload = {"id_usuario": 1, "fin": _future_fin()}
    req = _make_request()
    creds = _make_credentials("valid.token")

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import validate_token
        result = validate_token(req, creds)

    assert result == payload


def test_validate_token_stores_token_in_app_state():
    """Stores the raw token string in request.app.state.erp_api_token."""
    payload = {"id_usuario": 1, "fin": _future_fin()}
    req = _make_request()
    creds = _make_credentials("my.raw.token")

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import validate_token
        validate_token(req, creds)

    assert req.app.state.erp_api_token == "my.raw.token"


def test_validate_token_invalid_raises_401():
    """Raises HTTP 401 when the token signature is invalid."""
    req = _make_request()
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException) as exc:
            validate_token(req, creds)

    assert exc.value.status_code == 401


def test_validate_token_expired_raises_401():
    """Raises HTTP 401 when fin is in the past."""
    payload = {"id_usuario": 1, "fin": _past_fin()}
    req = _make_request()
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException) as exc:
            validate_token(req, creds)

    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_validate_token_does_not_store_token_on_error():
    """app.state.erp_api_token is NOT set when token is invalid."""
    state = MagicMock(spec=[])
    req = _make_request(app_state=state)
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException):
            validate_token(req, creds)

    assert not hasattr(state, "erp_api_token")
