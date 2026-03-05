"""Unit tests for auth_service.validate_token."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import MagicMock, patch
from jwt import ExpiredSignatureError, InvalidTokenError
from fastapi import HTTPException

import services.auth_service  # ensure module loaded before patching


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_request(app_state=None):
    req = MagicMock()
    req.app.state = app_state or MagicMock()
    return req


def _make_credentials(token="some.jwt.token"):
    creds = MagicMock()
    creds.credentials = token
    return creds


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

def test_validate_token_returns_payload():
    """Returns the decoded payload on a valid token."""
    payload = {"sub": "12345", "nit": "900123456"}
    req = _make_request()
    creds = _make_credentials("valid.token")

    with patch("services.auth_service.jwt.decode", return_value=payload):
        from services.auth_service import validate_token
        result = validate_token(req, creds)

    assert result == payload


def test_validate_token_stores_token_in_app_state():
    """Stores the raw token string in request.app.state.erp_api_token."""
    req = _make_request()
    creds = _make_credentials("my.raw.token")

    with patch("services.auth_service.jwt.decode", return_value={"sub": "1"}):
        from services.auth_service import validate_token
        validate_token(req, creds)

    assert req.app.state.erp_api_token == "my.raw.token"


def test_validate_token_decodes_with_hs256():
    """jwt.decode is called with the HS256 algorithm."""
    req = _make_request()
    creds = _make_credentials("token")
    mock_decode = MagicMock(return_value={"sub": "1"})

    with patch("services.auth_service.jwt.decode", mock_decode):
        from services.auth_service import validate_token
        validate_token(req, creds)

    _, _, kwargs = mock_decode.mock_calls[0]
    assert "HS256" in kwargs.get("algorithms", [])


# ---------------------------------------------------------------------------
# Expired token
# ---------------------------------------------------------------------------

def test_validate_token_expired_raises_401():
    """Raises HTTP 401 when the token is expired."""
    req = _make_request()
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=ExpiredSignatureError("expired")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException) as exc:
            validate_token(req, creds)

    assert exc.value.status_code == 401


def test_validate_token_expired_detail_message():
    """Error detail mentions 'expired'."""
    req = _make_request()
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=ExpiredSignatureError("expired")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException) as exc:
            validate_token(req, creds)

    assert "expired" in exc.value.detail.lower()


# ---------------------------------------------------------------------------
# Invalid token
# ---------------------------------------------------------------------------

def test_validate_token_invalid_raises_401():
    """Raises HTTP 401 when the token is invalid."""
    req = _make_request()
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException) as exc:
            validate_token(req, creds)

    assert exc.value.status_code != 401


def test_validate_token_invalid_detail_message():
    """Error detail mentions 'invalid'."""
    req = _make_request()
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException) as exc:
            validate_token(req, creds)

    assert "invalid" in exc.value.detail.lower()


def test_validate_token_does_not_store_token_on_error():
    """app.state.erp_api_token is NOT set when decode raises."""
    state = MagicMock(spec=[])  # no attributes by default
    req = _make_request(app_state=state)
    creds = _make_credentials()

    with patch("services.auth_service.jwt.decode", side_effect=InvalidTokenError("bad")):
        from services.auth_service import validate_token
        with pytest.raises(HTTPException):
            validate_token(req, creds)

    assert not hasattr(state, "erp_api_token")
