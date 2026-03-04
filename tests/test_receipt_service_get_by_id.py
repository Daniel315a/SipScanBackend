"""Unit tests for receipt_service.get_receipt (getById)"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import services.receipt_service  # ensures module is in sys.modules before patching

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000002")
_NOW = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def _make_status(id_=2, code="uploaded", label="Uploaded", is_final=False):
    s = MagicMock()
    s.id = id_
    s.code = code
    s.label = label
    s.is_final = is_final
    return s


def _make_rec(status=None, uploader_nit="987654"):
    rec = MagicMock()
    rec.id = _RECEIPT_ID
    rec.created_at = _NOW
    rec.updated_at = _NOW
    rec.uploader_nit = uploader_nit
    rec.summary = "Factura de prueba"
    rec.status_id = status.id if status else None
    rec.accounting_json = {"lineas": []}
    rec.status = status
    return rec


def _make_image_dict(url="https://s3.example.com/img.jpg", mime_type="image/jpeg", size_bytes=2048):
    return {"url": url, "mime_type": mime_type, "size_bytes": size_bytes}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_receipt_happy_path():
    """Returns a complete dict when receipt exists with status and images."""
    status = _make_status()
    rec = _make_rec(status=status)
    images = [_make_image_dict()]
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.get_images", AsyncMock(return_value=images)),
    ):
        from services import receipt_service
        result = await receipt_service.get_receipt(session, _RECEIPT_ID)

    assert result is not None
    assert result["id"] == str(_RECEIPT_ID)
    assert result["uploader_nit"] == "987654"
    assert result["status"] == "uploaded"
    assert result["status_id"] == status.id
    assert result["accounting_json"] == {"lineas": []}
    assert result["created_at"] == _NOW
    assert result["updated_at"] == _NOW
    assert result["summary"] == "Factura de prueba"
    assert result["images"] == images


@pytest.mark.asyncio
async def test_get_receipt_not_found_returns_none():
    """Returns None when the receipt does not exist."""
    session = AsyncMock()

    with patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=None)):
        from services import receipt_service
        result = await receipt_service.get_receipt(session, _RECEIPT_ID)

    assert result is None


@pytest.mark.asyncio
async def test_get_receipt_no_status_returns_none_for_status_field():
    """Returns None for 'status' field when rec.status is None."""
    rec = _make_rec(status=None)
    rec.status = None
    images = []
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.get_images", AsyncMock(return_value=images)),
    ):
        from services import receipt_service
        result = await receipt_service.get_receipt(session, _RECEIPT_ID)

    assert result is not None
    assert result["status"] is None
    assert result["images"] == []


@pytest.mark.asyncio
async def test_get_receipt_no_images_returns_empty_list():
    """Returns an empty images list when no images are associated."""
    status = _make_status(code="suggested")
    rec = _make_rec(status=status)
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.get_images", AsyncMock(return_value=[])),
    ):
        from services import receipt_service
        result = await receipt_service.get_receipt(session, _RECEIPT_ID)

    assert result["images"] == []
    assert result["status"] == "suggested"


@pytest.mark.asyncio
async def test_get_receipt_multiple_images():
    """Returns all images when receipt has more than one image."""
    status = _make_status()
    rec = _make_rec(status=status)
    images = [
        _make_image_dict(url="https://s3.example.com/img1.jpg"),
        _make_image_dict(url="https://s3.example.com/img2.jpg", mime_type="image/png"),
    ]
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.get_images", AsyncMock(return_value=images)),
    ):
        from services import receipt_service
        result = await receipt_service.get_receipt(session, _RECEIPT_ID)

    assert len(result["images"]) == 2
    assert result["images"][0]["url"] == "https://s3.example.com/img1.jpg"
    assert result["images"][1]["mime_type"] == "image/png"


@pytest.mark.asyncio
async def test_get_receipt_id_is_string():
    """The returned 'id' must be a string representation of the UUID."""
    status = _make_status()
    rec = _make_rec(status=status)
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.get_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.get_images", AsyncMock(return_value=[])),
    ):
        from services import receipt_service
        result = await receipt_service.get_receipt(session, _RECEIPT_ID)

    assert isinstance(result["id"], str)
    assert result["id"] == "00000000-0000-0000-0000-000000000002"
