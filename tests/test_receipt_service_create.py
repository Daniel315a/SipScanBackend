"""Unit tests for receipt_service.create"""
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

_RECEIPT_ID = UUID("00000000-0000-0000-0000-000000000001")
_NOW = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)

def _make_status(id_=1, code="uploaded", label="Uploaded", is_final=False):
    s = MagicMock()
    s.id = id_
    s.code = code
    s.label = label
    s.is_final = is_final
    return s

def _make_rec(status):
    rec = MagicMock()
    rec.id = _RECEIPT_ID
    rec.created_at = _NOW
    rec.updated_at = _NOW
    rec.summary = "Procesando documento"
    rec.status_id = status.id
    rec.accounting_json = None
    rec.status = status
    return rec

def _make_image(url="https://s3.example.com/img.jpg", mime_type="image/jpeg", size_bytes=1024):
    img = MagicMock()
    img.content_type = mime_type
    img.read = AsyncMock(return_value=b"data")
    return img

def _make_created_image(url="https://s3.example.com/img.jpg", mime_type="image/jpeg", size_bytes=1024):
    return {"url": url, "mime_type": mime_type, "size_bytes": size_bytes}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_create_happy_path():
    """Returns a complete dict when status exists and images are uploaded."""
    status = _make_status()
    rec = _make_rec(status)
    created_image = _make_created_image()
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=status)),
        patch("services.receipt_service.receipt_repo.create_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.create_images", AsyncMock(return_value=[created_image])),
        patch("services.receipt_service.get_first", AsyncMock(return_value=created_image)),
    ):
        from services import receipt_service
        images = [_make_image()]
        result = await receipt_service.create(session, uploader_nit="123456", images=images)

    assert result["id"] == str(_RECEIPT_ID)
    assert result["status"]["code"] == "uploaded"
    assert result["url"] == "https://s3.example.com/img.jpg"
    assert result["mime_type"] == "image/jpeg"
    assert result["size_bytes"] == 1024
    assert result["accounting_json"] is None


@pytest.mark.asyncio
async def test_create_raises_when_default_status_missing():
    """Raises ValueError when the 'uploaded' status is not in the DB."""
    session = AsyncMock()

    with patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=None)):
        from services import receipt_service
        with pytest.raises(ValueError, match="Default status not configured"):
            await receipt_service.create(session, uploader_nit="123456", images=[_make_image()])


@pytest.mark.asyncio
async def test_create_with_no_images_falls_back_to_get_first():
    """When images list is empty, url/mime/size come from get_first."""
    status = _make_status()
    rec = _make_rec(status)
    first_image = _make_created_image(url="https://s3.example.com/first.jpg")
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=status)),
        patch("services.receipt_service.receipt_repo.create_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.create_images", AsyncMock(return_value=[])),
        patch("services.receipt_service.get_first", AsyncMock(return_value=first_image)),
    ):
        from services import receipt_service
        result = await receipt_service.create(session, uploader_nit="123456", images=[])

    assert result["url"] == "https://s3.example.com/first.jpg"


@pytest.mark.asyncio
async def test_create_url_is_none_when_no_images_anywhere():
    """url is None when create_images returns [] and get_first returns None."""
    status = _make_status()
    rec = _make_rec(status)
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_status_repo.get_status_by_code", AsyncMock(return_value=status)),
        patch("services.receipt_service.receipt_repo.create_receipt", AsyncMock(return_value=rec)),
        patch("services.receipt_service.create_images", AsyncMock(return_value=[])),
        patch("services.receipt_service.get_first", AsyncMock(return_value=None)),
    ):
        from services import receipt_service
        result = await receipt_service.create(session, uploader_nit="123456", images=[])

    assert result["url"] is None
    assert result["mime_type"] is None
    assert result["size_bytes"] is None
