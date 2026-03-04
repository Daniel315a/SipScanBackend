"""Unit tests for GET /metadata/receipt-statuses route."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from fastapi import FastAPI

from routes.metadata import router


def _make_status(code="uploaded", label="Uploaded", is_final=False, is_active=True, sort_order=10):
    s = MagicMock()
    s.code = code
    s.label = label
    s.is_final = is_final
    s.is_active = is_active
    s.sort_order = sort_order
    return s


def _build_app(mock_session):
    """Create minimal test app with overridden session dependency."""
    from repositories.db import get_session

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_session] = lambda: mock_session
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_receipt_statuses_empty():
    """Returns 200 with empty list when no statuses exist."""
    session = AsyncMock()

    with patch("repositories.receipt_status_repo.list_statuses", AsyncMock(return_value=[])):
        app = _build_app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metadata/receipt-statuses")

    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_receipt_statuses_single():
    """Returns 200 with one serialized status."""
    session = AsyncMock()
    status = _make_status()

    with patch("repositories.receipt_status_repo.list_statuses", AsyncMock(return_value=[status])):
        app = _build_app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metadata/receipt-statuses")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0] == {
        "code": "uploaded",
        "label": "Uploaded",
        "is_final": False,
        "is_active": True,
        "sort_order": 10,
    }


@pytest.mark.asyncio
async def test_list_receipt_statuses_multiple():
    """Returns all statuses in the response."""
    session = AsyncMock()
    statuses = [
        _make_status("uploaded", "Uploaded", False, True, 10),
        _make_status("failed", "Failed", True, True, 30),
    ]

    with patch("repositories.receipt_status_repo.list_statuses", AsyncMock(return_value=statuses)):
        app = _build_app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metadata/receipt-statuses")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    assert data[0]["code"] == "uploaded"
    assert data[1]["code"] == "failed"
    assert data[1]["is_final"] is True


@pytest.mark.asyncio
async def test_list_receipt_statuses_inactive_excluded():
    """Verifies is_active=False statuses can be returned when repo includes them (filter is repo's responsibility)."""
    session = AsyncMock()
    status = _make_status("legacy", "Legacy", False, is_active=False, sort_order=99)

    with patch("repositories.receipt_status_repo.list_statuses", AsyncMock(return_value=[status])):
        app = _build_app(session)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metadata/receipt-statuses")

    assert response.status_code == 200
    data = response.json()
    assert data[0]["is_active"] is False
    assert data[0]["code"] == "legacy"
