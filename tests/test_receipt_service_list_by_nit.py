"""Unit tests for receipt_service.list_by_nit"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import services.receipt_service

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_NIT = "123456789"
_NOW = datetime(2024, 6, 1, 10, 0, 0, tzinfo=timezone.utc)


def _make_status(id_=1, code="uploaded", label="Uploaded", is_final=False):
    s = MagicMock()
    s.id = id_
    s.code = code
    s.label = label
    s.is_final = is_final
    return s


def _make_rec(uid: str, status=None, summary="Factura"):
    rec = MagicMock()
    rec.id = UUID(uid)
    rec.created_at = _NOW
    rec.summary = summary
    rec.status = status
    return rec


def _make_image(url="https://s3.example.com/img.jpg", mime_type="image/jpeg", size_bytes=1024):
    return {"url": url, "mime_type": mime_type, "size_bytes": size_bytes}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_by_nit_empty():
    """Returns empty items list when no receipts exist for the NIT."""
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=[])),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=0)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT)

    assert result["items"] == []
    assert result["total_estimated"] == 0
    assert result["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_by_nit_happy_path():
    """Returns one receipt dict with all fields populated."""
    status = _make_status()
    rec = _make_rec("00000000-0000-0000-0000-000000000001", status=status)
    img = _make_image()
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=[rec])),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=1)),
        patch("services.receipt_service.get_first", AsyncMock(return_value=img)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT)

    assert len(result["items"]) == 1
    item = result["items"][0]
    assert item["id"] == "00000000-0000-0000-0000-000000000001"
    assert item["created_at"] == _NOW
    assert item["summary"] == "Factura"
    assert item["url"] == "https://s3.example.com/img.jpg"
    assert item["mime_type"] == "image/jpeg"
    assert item["size_bytes"] == 1024
    assert item["status"] == {
        "id": 1, "code": "uploaded", "label": "Uploaded", "is_final": False
    }
    assert result["total_estimated"] == 1


@pytest.mark.asyncio
async def test_list_by_nit_multiple_receipts():
    """Returns all receipts in the list."""
    status = _make_status()
    recs = [
        _make_rec("00000000-0000-0000-0000-000000000001", status=status, summary="Factura 1"),
        _make_rec("00000000-0000-0000-0000-000000000002", status=status, summary="Factura 2"),
    ]
    img = _make_image()
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=recs)),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=2)),
        patch("services.receipt_service.get_first", AsyncMock(return_value=img)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT)

    assert len(result["items"]) == 2
    assert result["items"][0]["summary"] == "Factura 1"
    assert result["items"][1]["summary"] == "Factura 2"


@pytest.mark.asyncio
async def test_list_by_nit_no_status():
    """Returns None for 'status' when rec.status is None."""
    rec = _make_rec("00000000-0000-0000-0000-000000000003", status=None)
    img = _make_image()
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=[rec])),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=1)),
        patch("services.receipt_service.get_first", AsyncMock(return_value=img)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT)

    assert result["items"][0]["status"] is None


@pytest.mark.asyncio
async def test_list_by_nit_no_image():
    """Returns None for url/mime_type/size_bytes when get_first returns None."""
    status = _make_status()
    rec = _make_rec("00000000-0000-0000-0000-000000000004", status=status)
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=[rec])),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=1)),
        patch("services.receipt_service.get_first", AsyncMock(return_value=None)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT)

    assert result["items"][0]["url"] is None
    assert result["items"][0]["mime_type"] is None
    assert result["items"][0]["size_bytes"] is None


@pytest.mark.asyncio
async def test_list_by_nit_passes_limit_and_offset():
    """Forwards limit, offset and optional filters to the repository."""
    session = AsyncMock()
    mock_list = AsyncMock(return_value=[])
    mock_count = AsyncMock(return_value=0)

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", mock_list),
        patch("services.receipt_service.receipt_repo.count_by_nit", mock_count),
    ):
        from services import receipt_service
        await receipt_service.list_by_nit(session, _NIT, limit=10, offset=5)

    mock_list.assert_called_once_with(
        session, _NIT, limit=10, offset=5, from_date=None, to_date=None, summary_filter=None
    )
    mock_count.assert_called_once_with(
        session, _NIT, from_date=None, to_date=None, summary_filter=None
    )


@pytest.mark.asyncio
async def test_list_by_nit_next_cursor_when_full_page():
    """next_cursor is the next offset when results fill the page."""
    status = _make_status()
    recs = [_make_rec(f"00000000-0000-0000-0000-00000000000{i}", status=status) for i in range(1, 3)]
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=recs)),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=5)),
        patch("services.receipt_service.get_first", AsyncMock(return_value=None)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT, limit=2, offset=0)

    assert result["next_cursor"] == 2
    assert result["page_size"] == 2
    assert result["total_estimated"] == 5


@pytest.mark.asyncio
async def test_list_by_nit_no_next_cursor_on_last_page():
    """next_cursor is None when results are fewer than the page size."""
    status = _make_status()
    rec = _make_rec("00000000-0000-0000-0000-000000000001", status=status)
    session = AsyncMock()

    with (
        patch("services.receipt_service.receipt_repo.list_by_nit", AsyncMock(return_value=[rec])),
        patch("services.receipt_service.receipt_repo.count_by_nit", AsyncMock(return_value=1)),
        patch("services.receipt_service.get_first", AsyncMock(return_value=None)),
    ):
        from services import receipt_service
        result = await receipt_service.list_by_nit(session, _NIT, limit=20, offset=0)

    assert result["next_cursor"] is None
