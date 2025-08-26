from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from repositories import receipt_repo
from repositories import receipt_status_repo
from services.s3_service import upload_image, presign_url

DEFAULT_STATUS_CODE = "uploaded"

async def create_receipt_from_upload_s3(
    session: AsyncSession,
    *,
    uploader_nit: str,
    image: UploadFile,
) -> dict:
    status = await receipt_status_repo.get_status_by_code(session, DEFAULT_STATUS_CODE)
    if not status:
        raise ValueError("Default status not configured")

    mime = image.content_type
    
    try:
        pos = image.file.tell()
        image.file.seek(0, 2)  # EOF
        size = image.file.tell()
        image.file.seek(pos, 0)
    except Exception:
        size = None

    bucket, key = await upload_image(image, uploader_nit)

    rec = await receipt_repo.create_receipt(
        session,
        uploader_nit=uploader_nit,
        s3_bucket=bucket,
        s3_key=key,
        mime_type=mime,
        size_bytes=size,
        status_id=status.id,
        extracted_text=None,
    )

    url = presign_url(bucket, key)

    return {
        "id": str(rec.id),
        "uploader_nit": uploader_nit,
        "s3_bucket": bucket,
        "s3_key": key,
        "mime_type": mime,
        "size_bytes": size,
        "url": url,
    }

async def get_receipt(session: AsyncSession, receipt_id: UUID):
    return await receipt_repo.get_receipt(session, receipt_id)

async def list_receipts(session: AsyncSession, limit: int = 50, offset: int = 0):
    return await receipt_repo.list_receipts(session, limit=limit, offset=offset)

async def list_by_nit(session: AsyncSession, uploader_nit: str, limit: int = 50, offset: int = 0):
    return await receipt_repo.list_by_nit(session, uploader_nit, limit=limit, offset=offset)

async def get_image_url(session: AsyncSession, receipt_id: UUID) -> str:
    rec = await receipt_repo.get_receipt(session, receipt_id)
    if not rec:
        raise ValueError("Receipt not found")
    if not getattr(rec, "status_id", None):
        raise ValueError("Receipt not fully initialized")

    return presign_url(rec.s3_bucket, rec.s3_key)
