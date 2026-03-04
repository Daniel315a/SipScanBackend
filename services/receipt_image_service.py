# services/receipt_image_service.py
from __future__ import annotations
from typing import List, Dict, Any
from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from datetime import datetime, timezone 
import asyncio

from repositories import receipt_image_repo
from repositories import receipt_repo
from services.s3_service import upload_image, presign_url
from services.ocr_service import get_ocr_provider

def _safe_filesize(upload: UploadFile) -> int | None:
    """
    Best-effort file size detection for UploadFile (works for in-memory/temporary files).
    Returns None if we can't determine size safely.
    """
    try:
        pos = upload.file.tell()
        upload.file.seek(0, 2)  # move to EOF
        size = upload.file.tell()
        upload.file.seek(pos, 0)  # restore position
        return int(size)
    except Exception:  # pragma: no cover
        return None

async def get_images(session: AsyncSession, *, receipt_id: UUID) -> List[Dict[str, Any]]:
    """
    Public: Return all images populated from DB with their S3 presigned URLs.
    Ordered by img_number ASC.
    """
    images = await receipt_image_repo.get_by_receipt(session, receipt_id)
    result: List[Dict[str, Any]] = []
    for img in images:
        result.append(
            {
                "id": str(img.id),
                "img_number": img.img_number,
                "mime_type": img.mime_type,
                "size_bytes": img.size_bytes,
                "s3_bucket": img.s3_bucket,
                "s3_key": img.s3_key,
                "url": presign_url(img.s3_bucket, img.s3_key),
                "created_at": img.created_at,
                "updated_at": img.updated_at,
            }
        )
    return result

async def create_images(
    session: AsyncSession,
    *,
    uploader_nit: str,
    receipt_id: UUID,
    images: List[UploadFile],
) -> List[Dict[str, Any]]:
    """
    Upload each image to S3 and create its ReceiptImage row.
    Enforces 10-images-per-receipt via repository constraint.
    Returns the populated image list (with presigned URLs).
    """
    if not images:
        return []

    for upload in images:
        mime = (upload.content_type or "").lower() if upload.content_type else None
        size = _safe_filesize(upload)

        bucket, key = await upload_image(upload, uploader_nit)

        await receipt_image_repo.create(
            session,
            receipt_id=receipt_id,
            s3_bucket=bucket,
            s3_key=key,
            mime_type=mime,
            size_bytes=size,
        )

    return await get_images(session, receipt_id=receipt_id)

async def get_first(session: AsyncSession, *, receipt_id: UUID) -> Dict[str, Any] | None:
    """
    Return the primary (first) image of a receipt (lowest img_number),
    enriched with a presigned URL. None if the receipt has no images.
    """
    imgs = await receipt_image_repo.get_by_receipt(session, receipt_id, limit=1, offset=0)
    if not imgs:
        return None

    img = imgs[0]

    return {
        "id": str(img.id),
        "mime_type": img.mime_type,
        "size_bytes": img.size_bytes,
        "url": presign_url(img.s3_bucket, img.s3_key),
    }

async def ocr_images_to_resources(  # pragma: no cover
    session: AsyncSession,
    *,
    receipt_id: UUID,
) -> List[Dict[str, Any]]:
    """
    Iterate over the receipt images (ordered by img_number), send each one to Textract,
    and UPDATE the ReceiptImage row:
    - Success -> extracted_text
    - Error   -> ocr_error, ocr_error_type, ocr_error_code, ocr_error_at (UTC)
    Return a per-image summary.
    """

    images = await receipt_image_repo.get_by_receipt(session, receipt_id)
    if not images:
        return []

    provider = get_ocr_provider()
    loop = asyncio.get_running_loop()

    results: List[Dict[str, Any]] = []

    for img in images:
        bucket = img.s3_bucket
        key = img.s3_key
        image_id = img.id

        text: str | None = None
        err_msg: str | None = None
        err_type: str | None = None
        err_code: str | None = None

        try:
            text = await loop.run_in_executor(
                None, lambda: provider.extract_text_from_s3(bucket=bucket, key=key)
            )
            
            await receipt_image_repo.update_ocr_result(
                session,
                image_id=image_id,
                extracted_text=text or "",
                ocr_error=None,
                ocr_error_type=None,
                ocr_error_code=None,
                ocr_error_at=None,
            )
            results.append(
                {
                    "image_id": str(image_id),
                    "ok": True,
                    "text_bytes": len((text or "").encode("utf-8")),
                }
            )

        except Exception as e:
            err_msg = str(e)
            err_type = type(e).__name__

            try:
                err_code = getattr(e, "response", {}).get("Error", {}).get("Code")
            except Exception:
                err_code = None

            await receipt_image_repo.update_ocr_result(
                session,
                image_id=image_id,
                extracted_text=None,
                ocr_error=err_msg,
                ocr_error_type=err_type,
                ocr_error_code=err_code,
                ocr_error_at=datetime.now(timezone.utc),
            )

            results.append(
                {
                    "image_id": str(image_id),
                    "ok": False,
                    "error": err_msg,
                    "error_type": err_type,
                    **({"error_code": err_code} if err_code else {}),
                }
            )

    await receipt_repo.update_status(session, receipt_id=receipt_id, status_code="extracted_text")

    return results

async def run_ocr_for_receipt(  # pragma: no cover
    session_factory: "async_sessionmaker[AsyncSession]",
    *,
    receipt_id: UUID,
) -> None:
    async with session_factory() as session:
        await ocr_images_to_resources(session, receipt_id=receipt_id)
