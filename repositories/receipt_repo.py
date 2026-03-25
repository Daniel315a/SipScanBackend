# repositories/receipt_repo.py
from typing import Optional, Sequence
from uuid import UUID
from datetime import datetime, timezone, timedelta

from sqlalchemy import func, select, delete as sqldelete, update as sqlupdate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import set_committed_value


from repositories.models import Receipt
from repositories import receipt_image_repo
from repositories import receipt_status_repo

async def create_receipt(
    session: AsyncSession,
    *,
    uploader_nit: str,
    status_id: int,
    accounting_json: dict | None = None,
) -> Receipt:
    """Insert a new receipt and return the ORM entity (no images here)."""
    rec = Receipt(
        uploader_nit=uploader_nit,
        status_id=status_id,
        accounting_json=accounting_json,
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec

async def get_receipt(session: AsyncSession, receipt_id: UUID) -> Receipt | None:
    """
    Fetch a receipt by id and attach its images using the receipt_image_repo.get_by_receipt,
    ordered by img_number ASC.
    """
    stmt = (
        select(Receipt)
        .options(selectinload(Receipt.status))
        .where(Receipt.id == receipt_id)
    )
    res = await session.execute(stmt)
    rec = res.scalar_one_or_none()
    if rec is None:
        return None

    images = await receipt_image_repo.get_by_receipt(session, receipt_id)

    set_committed_value(rec, "images", list(images))

    return rec

async def list_by_nit(
    session: AsyncSession,
    uploader_nit: str,
    limit: int = 50,
    offset: int = 0,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    summary_filter: Optional[str] = None,
) -> Sequence[Receipt]:
    """List receipts filtered by uploader_nit with pagination and optional filters."""
    conditions = [Receipt.uploader_nit == uploader_nit]
    if from_date:
        conditions.append(Receipt.created_at >= from_date)
    if to_date:
        conditions.append(Receipt.created_at <= to_date)
    if summary_filter:
        conditions.append(Receipt.summary.ilike(f"%{summary_filter}%"))

    order = Receipt.created_at.asc() if (from_date or to_date) else Receipt.created_at.desc()
    stmt = (
        select(Receipt)
        .options(selectinload(Receipt.status))
        .where(*conditions)
        .order_by(order)
        .offset(offset)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()


async def count_by_nit(
    session: AsyncSession,
    uploader_nit: str,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    summary_filter: Optional[str] = None,
) -> int:
    """Count receipts for a given NIT with the same optional filters as list_by_nit."""
    conditions = [Receipt.uploader_nit == uploader_nit]
    if from_date:
        conditions.append(Receipt.created_at >= from_date)
    if to_date:
        conditions.append(Receipt.created_at <= to_date)
    if summary_filter:
        conditions.append(Receipt.summary.ilike(f"%{summary_filter}%"))

    stmt = select(func.count()).select_from(Receipt).where(*conditions)
    res = await session.execute(stmt)
    return res.scalar_one()

async def delete_receipt(session: AsyncSession, receipt_id: UUID) -> bool:
    """
    Delete a receipt and all its images.
    Uses receipt_image_repo.delete_by_receipt before removing the receipt row.
    """
    
    await receipt_image_repo.delete_by_receipt(session, receipt_id)

    stmt = sqldelete(Receipt).where(Receipt.id == receipt_id)
    res = await session.execute(stmt)
    await session.commit()
    return (res.rowcount or 0) > 0

async def mark_stuck_as_failed(
    session: AsyncSession,
    *,
    stuck_status_code: str = "extracted_text",
    timeout_minutes: int = 15,
) -> int:
    """Bulk-update receipts stuck in `stuck_status_code` for more than `timeout_minutes`
    to 'failed' with summary 'Error al procesar'. Returns the number of updated rows."""
    failed_status = await receipt_status_repo.get_status_by_code(session, "failed")
    stuck_status = await receipt_status_repo.get_status_by_code(session, stuck_status_code)
    if not failed_status or not stuck_status:
        return 0

    cutoff = datetime.now(timezone.utc) - timedelta(minutes=timeout_minutes)
    stmt = (
        sqlupdate(Receipt)
        .where(Receipt.status_id == stuck_status.id, Receipt.updated_at < cutoff)
        .values(status_id=failed_status.id, summary="Error al procesar")
    )
    res = await session.execute(stmt)
    await session.commit()
    return res.rowcount or 0


async def update_status(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    status_code: str,
) -> None:
    """
    Updates the receipt's status (status_id) based on the given status_code.
    Throws a ValueError if the code doesn't exist.
    """
    status = await receipt_status_repo.get_status_by_code(session, status_code)
    if not status:
        raise ValueError(f"Unknown status code: {status_code}")

    stmt = (
        sqlupdate(Receipt)
        .where(Receipt.id == receipt_id)
        .values(status_id=status.id)
    )
    await session.execute(stmt)
    await session.commit()
