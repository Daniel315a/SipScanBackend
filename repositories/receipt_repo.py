from typing import Sequence
from uuid import UUID
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from repositories.models import Receipt

async def create_receipt(
    session: AsyncSession,
    *,
    uploader_nit: str,
    s3_bucket: str,
    s3_key: str,
    mime_type: str | None,
    size_bytes: int | None,
    status_id: int,
    extracted_text: str | None = None,
) -> Receipt:
    """Insert a new receipt and return the ORM entity."""
    rec = Receipt(
        uploader_nit=uploader_nit,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        mime_type=mime_type,
        size_bytes=size_bytes,
        status_id=status_id,
        extracted_text=extracted_text,
    )
    session.add(rec)
    await session.commit()
    await session.refresh(rec)
    return rec

async def get_receipt(session: AsyncSession, receipt_id: UUID) -> Receipt | None:
    stmt = (
        select(Receipt)
        .options(selectinload(Receipt.status))
        .where(Receipt.id == receipt_id)
    )
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def list_receipts(session: AsyncSession, limit: int = 50, offset: int = 0) -> Sequence[Receipt]:
    stmt = (
        select(Receipt)
        .options(selectinload(Receipt.status))
        .order_by(Receipt.created_at.desc())
        .offset(offset).limit(limit)
    )
    res = await session.execute(stmt)
    return res.scalars().all()

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
