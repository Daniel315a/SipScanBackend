# repositories/receipt_repo.py
from typing import Sequence
from uuid import UUID

from sqlalchemy import select, delete as sqldelete, update as sqlupdate
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

async def list_by_nit(session: AsyncSession, uploader_nit: str, limit: int = 50, offset: int = 0) -> Sequence[Receipt]:
    """List receipts filtered by uploader_nit with basic pagination."""
    stmt = (
        select(Receipt)
        .options(selectinload(Receipt.status))
        .where(Receipt.uploader_nit == uploader_nit)
        .order_by(Receipt.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()

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
