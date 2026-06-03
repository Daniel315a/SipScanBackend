"""Unit tests for receipt_repo.mark_stuck_as_failed."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import repositories.receipt_repo as repo


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_status(id_=1, code="failed"):
    s = MagicMock()
    s.id = id_
    s.code = code
    return s


def _session_with_rowcount(rowcount=0):
    session = AsyncMock()
    result = MagicMock()
    result.rowcount = rowcount
    session.execute.return_value = result
    return session


def _patch_statuses(failed=None, stuck=None):
    """Returns a context manager that patches get_status_by_code."""
    async def _get(sess, code):
        if code == "failed":
            return failed
        return stuck

    return patch("repositories.receipt_repo.receipt_status_repo.get_status_by_code", _get)


# ---------------------------------------------------------------------------
# Early-exit when statuses are missing
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_zero_when_failed_status_missing():
    """Returns 0 without touching the DB when 'failed' status does not exist."""
    session = AsyncMock()

    with _patch_statuses(failed=None, stuck=_make_status(2, "extracted_text")):
        count = await repo.mark_stuck_as_failed(session)

    assert count == 0
    session.execute.assert_not_called()


@pytest.mark.asyncio
async def test_returns_zero_when_stuck_status_missing():
    """Returns 0 without touching the DB when the stuck status does not exist."""
    session = AsyncMock()

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=None):
        count = await repo.mark_stuck_as_failed(session)

    assert count == 0
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_returns_rowcount_on_update():
    """Returns the number of rows updated."""
    session = _session_with_rowcount(3)

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=_make_status(2, "extracted_text")):
        count = await repo.mark_stuck_as_failed(session)

    assert count == 3


@pytest.mark.asyncio
async def test_commits_after_update():
    """Calls session.commit() after executing the update."""
    session = _session_with_rowcount(1)

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=_make_status(2, "extracted_text")):
        await repo.mark_stuck_as_failed(session)

    session.commit.assert_called_once()


@pytest.mark.asyncio
async def test_returns_zero_when_rowcount_is_none():
    """Treats None rowcount as 0 (driver may return None on no-op updates)."""
    session = _session_with_rowcount(None)

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=_make_status(2, "extracted_text")):
        count = await repo.mark_stuck_as_failed(session)

    assert count == 0


@pytest.mark.asyncio
async def test_executes_exactly_once():
    """Issues a single UPDATE statement."""
    session = _session_with_rowcount(0)

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=_make_status(2, "extracted_text")):
        await repo.mark_stuck_as_failed(session)

    session.execute.assert_called_once()


# ---------------------------------------------------------------------------
# Custom parameters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_accepts_custom_stuck_status_code():
    """Works with a custom stuck_status_code ('uploaded')."""
    session = _session_with_rowcount(2)

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=_make_status(1, "uploaded")):
        count = await repo.mark_stuck_as_failed(session, stuck_status_code="uploaded")

    assert count == 2


@pytest.mark.asyncio
async def test_accepts_custom_timeout_minutes():
    """Does not raise when called with a non-default timeout_minutes."""
    session = _session_with_rowcount(0)

    with _patch_statuses(failed=_make_status(3, "failed"), stuck=_make_status(2, "extracted_text")):
        count = await repo.mark_stuck_as_failed(session, timeout_minutes=30)

    assert count == 0
