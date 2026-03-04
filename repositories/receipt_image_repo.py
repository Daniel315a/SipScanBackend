# repositories/receipt_image_repo.py
from __future__ import annotations
from typing import Sequence, Optional
from uuid import UUID

from sqlalchemy import select, func, delete as sqldelete, update as sqlupdate
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from repositories.models import ReceiptImage
from datetime import datetime, timezone 

# ---- Mime-type validation ----
_ALLOWED_IMAGE_MIME_EXACT = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
    "image/tiff",
    "image/bmp",
    "image/gif",
}

def _validate_mime_type(mime_type: str | None) -> str | None:
    """Ensure mime_type is an allowed image type; returns the same value if valid."""
    if mime_type is None:
        return None
    mt = mime_type.strip().lower()
    if mt in _ALLOWED_IMAGE_MIME_EXACT or mt.startswith("image/"):
        return mt
    raise ValueError(f"Unsupported mime_type '{mime_type}'. Expected image/*.")

# ---- Helpers ----
async def _count_images_for_receipt(session: AsyncSession, receipt_id: UUID) -> int:
    stmt = select(func.count(ReceiptImage.id)).where(ReceiptImage.receipt_id == receipt_id)
    res = await session.execute(stmt)
    return int(res.scalar() or 0)

async def _next_img_number(session: AsyncSession, receipt_id: UUID) -> int:
    stmt = select(func.coalesce(func.max(ReceiptImage.img_number), 0) + 1).where(
        ReceiptImage.receipt_id == receipt_id
    )
    res = await session.execute(stmt)
    return int(res.scalar() or 1)

# ---- Public API ----
async def create(
    session: AsyncSession,
    *,
    receipt_id: UUID,
    s3_bucket: str,
    s3_key: str,
    mime_type: str | None,
    size_bytes: int | None = None,
    extracted_text: str | None = None,
    textract_job_id: str | None = None,
) -> ReceiptImage:
    """
    Create a new ReceiptImage for a receipt.
    - Enforces a max of 10 images per receipt.
    - Validates and stores mime_type.
    - If img_number is not provided, assigns the next sequential number (1..N).
    """
    
    existing = await _count_images_for_receipt(session, receipt_id)
    if existing >= 10:
        raise ValueError("Receipt already has the maximum of 10 images.")

    # Validate mime_type (must be image/*)
    valid_mime = _validate_mime_type(mime_type)

    number = await _next_img_number(session, receipt_id)

    if number < 1 or number > 10:
        raise ValueError("img_number must be between 1 and 10.")

    entity = ReceiptImage(
        receipt_id=receipt_id,
        s3_bucket=s3_bucket,
        s3_key=s3_key,
        mime_type=valid_mime,
        size_bytes=size_bytes,
        img_number=number,
        extracted_text=extracted_text,
        textract_job_id=textract_job_id,
    )

    session.add(entity)

    try:
        await session.commit()
    except IntegrityError as ie:
        await session.rollback()
        raise ValueError("Duplicate img_number for this receipt.") from ie

    await session.refresh(entity)
    return entity

async def get_by_receipt(
    session: AsyncSession,
    receipt_id: UUID,
    *,
    limit: Optional[int] = None,
    offset: int = 0,
) -> Sequence[ReceiptImage]:
    """Return images for a receipt ordered by img_number ASC, with optional pagination."""
    stmt = (
        select(ReceiptImage)
        .where(ReceiptImage.receipt_id == receipt_id)
        .order_by(ReceiptImage.img_number.asc())
        .offset(offset)
    )
    if limit is not None:
        stmt = stmt.limit(limit)

    res = await session.execute(stmt)
    return res.scalars().all()

async def delete(session: AsyncSession, image_id: UUID) -> bool:
    """Delete a single image by id. Returns True if a row was deleted."""
    stmt = sqldelete(ReceiptImage).where(ReceiptImage.id == image_id)
    res = await session.execute(stmt)
    await session.commit()
    return (res.rowcount or 0) > 0

async def delete_by_receipt(session: AsyncSession, receipt_id: UUID) -> int:
    """Delete all images for a receipt. Returns the number of deleted rows."""
    stmt = sqldelete(ReceiptImage).where(ReceiptImage.receipt_id == receipt_id)
    res = await session.execute(stmt)
    await session.commit()
    return int(res.rowcount or 0)

async def update_ocr_result(
    session: AsyncSession,
    *,
    image_id: UUID,
    extracted_text: str | None = None,
    ocr_error: str | None = None,
    ocr_error_type: str | None = None,
    ocr_error_code: str | None = None,
    ocr_error_at: datetime | None = None,
) -> None:
    """
    Update the OCR fields for a specific image.
    - On success: pass extracted_text and leave errors as None.
    - On error: pass ocr_error (+type/+code) and optionally extracted_text=None.

    """
    values: dict = {
        "extracted_text": extracted_text,
        "ocr_error": ocr_error,
        "ocr_error_type": ocr_error_type,
        "ocr_error_code": ocr_error_code,
        "ocr_error_at": ocr_error_at,
    }

    stmt = (
        sqlupdate(ReceiptImage)
        .where(ReceiptImage.id == image_id)
        .values(**values)
    )

    await session.execute(stmt)
    await session.commit()