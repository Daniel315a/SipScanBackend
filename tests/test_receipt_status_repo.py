"""Unit tests for receipt_status_repo."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

import repositories.receipt_status_repo as repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status(code="uploaded", label="Uploaded", is_final=False, sort_order=10):
    s = MagicMock()
    s.code = code
    s.label = label
    s.is_final = is_final
    s.is_active = True
    s.sort_order = sort_order
    return s


def _session_returning(scalars_list):
    """Build an AsyncMock session whose execute() returns the given scalars list."""
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = scalars_list
    session.execute.return_value = result
    return session


def _session_scalar(value):
    """Build an AsyncMock session whose execute() returns scalar_one_or_none = value."""
    session = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    session.execute.return_value = result
    return session


# ---------------------------------------------------------------------------
# list_statuses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_statuses_empty():
    """Returns empty sequence when no statuses exist."""
    session = _session_returning([])
    result = await repo.list_statuses(session)
    assert list(result) == []


@pytest.mark.asyncio
async def test_list_statuses_returns_all():
    """Returns all statuses provided by the DB."""
    statuses = [_make_status("uploaded"), _make_status("failed", is_final=True)]
    session = _session_returning(statuses)
    result = await repo.list_statuses(session)
    assert list(result) == statuses


@pytest.mark.asyncio
async def test_list_statuses_calls_execute():
    """Calls session.execute() exactly once."""
    session = _session_returning([])
    await repo.list_statuses(session)
    session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# get_status_by_code
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_status_by_code_found():
    """Returns the status when it exists."""
    status = _make_status("uploaded")
    session = _session_scalar(status)
    result = await repo.get_status_by_code(session, "uploaded")
    assert result is status


@pytest.mark.asyncio
async def test_get_status_by_code_not_found():
    """Returns None when code does not exist."""
    session = _session_scalar(None)
    result = await repo.get_status_by_code(session, "nonexistent")
    assert result is None


# ---------------------------------------------------------------------------
# ensure_default_statuses
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ensure_default_statuses_inserts_missing():
    """Adds a ReceiptStatus for each code not already in the DB."""
    session = AsyncMock()
    # All queries return None → everything needs to be inserted
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    session.execute.return_value = result

    await repo.ensure_default_statuses(session)

    expected_count = len(repo.DEFAULT_RECEIPT_STATUSES)
    assert session.add.call_count == expected_count
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_default_statuses_skips_existing():
    """Does not add a ReceiptStatus when it already exists."""
    session = AsyncMock()
    existing = _make_status("uploaded")
    result = MagicMock()
    # All codes already exist
    result.scalar_one_or_none.return_value = existing
    session.execute.return_value = result

    await repo.ensure_default_statuses(session)

    session.add.assert_not_called()
    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_default_statuses_partial():
    """Inserts only codes that are missing."""
    session = AsyncMock()
    existing = _make_status("uploaded")

    # Return existing for "uploaded", None for everything else
    call_count = 0
    async def execute_side_effect(stmt):
        nonlocal call_count
        result = MagicMock()
        result.scalar_one_or_none.return_value = existing if call_count == 0 else None
        call_count += 1
        return result

    session.execute.side_effect = execute_side_effect

    await repo.ensure_default_statuses(session)

    # 1 existing → skip, rest → insert
    assert session.add.call_count == len(repo.DEFAULT_RECEIPT_STATUSES) - 1
    session.commit.assert_called_once()
