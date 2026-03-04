"""Unit tests for receipt_service.accept_accounting and reject_accounting (_set_status)."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import services.receipt_service

_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000001")
_NOW = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def _make_rec(status_id=1):
    rec = MagicMock()
    rec.id = _RECEIPT_ID
    rec.created_at = _NOW
    rec.updated_at = _NOW
    rec.summary = "Factura de prueba"
    rec.status_id = status_id
    rec.accounting_json = None
    return rec


def _make_status(id_=1, code="accepted_accounting", label="Accepted accounting", is_final=False):
    s = MagicMock()
    s.id = id_
    s.code = code
    s.label = label
    s.is_final = is_final
    return s


# ---------------------------------------------------------------------------
# accept_accounting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accept_accounting_happy_path():
    """Returns expected dict when receipt and status exist."""
    rec = _make_rec()
    st = _make_status(code="accepted_accounting")
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=st)),
    ):
        from services import receipt_service
        result = await receipt_service.accept_accounting(session, receipt_id=_RECEIPT_ID)

    assert result["id"] == str(_RECEIPT_ID)
    assert result["status"]["code"] == "accepted_accounting"
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_accept_accounting_passes_correct_status_code():
    """Calls get_status_by_code with 'accepted_accounting'."""
    rec = _make_rec()
    session = AsyncMock()
    mock_get_status = AsyncMock(return_value=_make_status(code="accepted_accounting"))

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", mock_get_status),
    ):
        from services import receipt_service
        await receipt_service.accept_accounting(session, receipt_id=_RECEIPT_ID)

    mock_get_status.assert_called_once_with(session, "accepted_accounting")


@pytest.mark.asyncio
async def test_accept_accounting_receipt_not_found():
    """Raises ValueError when receipt does not exist."""
    session = AsyncMock()

    with patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=None)):
        from services import receipt_service
        with pytest.raises(ValueError, match="Receipt not found"):
            await receipt_service.accept_accounting(session, receipt_id=_RECEIPT_ID)


@pytest.mark.asyncio
async def test_accept_accounting_status_not_configured():
    """Raises RuntimeError when status code is not in DB."""
    rec = _make_rec()
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=None)),
    ):
        from services import receipt_service
        with pytest.raises(RuntimeError, match="accepted_accounting"):
            await receipt_service.accept_accounting(session, receipt_id=_RECEIPT_ID)


@pytest.mark.asyncio
async def test_accept_accounting_sets_status_id():
    """Sets rec.status_id to the status's id before committing."""
    rec = _make_rec(status_id=0)
    st = _make_status(id_=7, code="accepted_accounting")
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=st)),
    ):
        from services import receipt_service
        await receipt_service.accept_accounting(session, receipt_id=_RECEIPT_ID)

    assert rec.status_id == 7


# ---------------------------------------------------------------------------
# reject_accounting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_reject_accounting_happy_path():
    """Returns expected dict with rejected_accounting status."""
    rec = _make_rec()
    st = _make_status(code="rejected_accounting")
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=st)),
    ):
        from services import receipt_service
        result = await receipt_service.reject_accounting(session, receipt_id=_RECEIPT_ID)

    assert result["status"]["code"] == "rejected_accounting"
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_reject_accounting_passes_correct_status_code():
    """Calls get_status_by_code with 'rejected_accounting'."""
    rec = _make_rec()
    session = AsyncMock()
    mock_get_status = AsyncMock(return_value=_make_status(code="rejected_accounting"))

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", mock_get_status),
    ):
        from services import receipt_service
        await receipt_service.reject_accounting(session, receipt_id=_RECEIPT_ID)

    mock_get_status.assert_called_once_with(session, "rejected_accounting")


@pytest.mark.asyncio
async def test_reject_accounting_receipt_not_found():
    """Raises ValueError when receipt does not exist."""
    session = AsyncMock()

    with patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=None)):
        from services import receipt_service
        with pytest.raises(ValueError, match="Receipt not found"):
            await receipt_service.reject_accounting(session, receipt_id=_RECEIPT_ID)


@pytest.mark.asyncio
async def test_reject_accounting_status_not_configured():
    """Raises RuntimeError when status code is not in DB."""
    rec = _make_rec()
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=None)),
    ):
        from services import receipt_service
        with pytest.raises(RuntimeError, match="rejected_accounting"):
            await receipt_service.reject_accounting(session, receipt_id=_RECEIPT_ID)


# ---------------------------------------------------------------------------
# Return shape (_set_status)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_set_status_return_shape():
    """Returned dict contains all expected keys with correct values."""
    rec = _make_rec(status_id=5)
    rec.accounting_json = {"total": 100}
    st = _make_status(id_=5, code="accepted_accounting", label="Accepted", is_final=True)
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=st)),
    ):
        from services import receipt_service
        result = await receipt_service.accept_accounting(session, receipt_id=_RECEIPT_ID)

    assert set(result.keys()) >= {"id", "created_at", "status", "summary", "status_id", "accounting_json", "updated_at"}
    assert result["status"] == {
        "id": 5,
        "code": "accepted_accounting",
        "label": "Accepted",
        "is_final": True,
    }
    assert result["accounting_json"] == {"total": 100}
    assert result["id"] == str(_RECEIPT_ID)
