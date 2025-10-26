# services/receipt_service.py
import asyncio
import logging
import json
import os
import re

from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
from typing import List

from repositories import receipt_repo
from repositories import receipt_status_repo
from services.s3_service import upload_image, presign_url
from services.ocr_service import get_ocr_provider
from services.llm_service import LLMService, render_template
from services.erp_service import erp_service
from services.receipt_image_service import create_images, get_images, get_first

DEFAULT_STATUS_CODE = "uploaded"
SUGGESTED_STATUS = "suggested"
_RES_DIR = os.getenv("RESOURCES_DIR", "/app/resources")

def receipt_to_dict(rec) -> dict:
    return {
        "id": str(rec.id),
        "uploader_nit": rec.uploader_nit,
        "s3_bucket": rec.s3_bucket,
        "s3_key": rec.s3_key,
        "mime_type": rec.mime_type,
        "size_bytes": rec.size_bytes,
        "extracted_text": rec.extracted_text,
        "url": presign_url(rec.s3_bucket, rec.s3_key),
        "created_at": rec.created_at,
        "status_id": rec.status_id,
        "accounting_json": rec.accounting_json,
    }

async def create(
    session: AsyncSession,
    *,
    uploader_nit: str,
    images: List[UploadFile],
) -> dict:
    """
    Create a receipt and then upload its images using receipt_image_service.
    OCR calls intentionally removed for now.
    """
    status = await receipt_status_repo.get_status_by_code(session, DEFAULT_STATUS_CODE)
    if not status:
        raise ValueError("Default status not configured")

    rec = await receipt_repo.create_receipt(
        session,
        uploader_nit=uploader_nit,
        status_id=status.id,
        accounting_json=None,
    )

    created_images = await create_images(
        session,
        uploader_nit=uploader_nit,
        receipt_id=rec.id,
        images=images or [],
    )

    return {
        "id": str(rec.id),
        "uploader_nit": rec.uploader_nit,
        "status_id": rec.status_id,
        "status": getattr(rec, "status", None).code if getattr(rec, "status", None) else None,
        "accounting_json": rec.accounting_json,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "images": created_images if created_images is not None else await get_images(session, receipt_id=rec.id),
    }

async def get_receipt(session: AsyncSession, receipt_id: UUID):
    rec = await receipt_repo.get_receipt(session, receipt_id)
    if not rec:
        return None

    # Hydrate images with presigned URLs
    images = await get_images(session, receipt_id=receipt_id)

    return {
        "id": str(rec.id),
        "uploader_nit": rec.uploader_nit,
        "status_id": rec.status_id,
        "status": getattr(rec, "status", None).code if getattr(rec, "status", None) else None,
        "accounting_json": rec.accounting_json,
        "created_at": rec.created_at,
        "updated_at": rec.updated_at,
        "images": images,
    }

async def list_by_nit(session: AsyncSession, uploader_nit: str, limit: int = 50, offset: int = 0):
    """
    List receipts by uploader_nit including the primary image (lowest img_number).
    The returned dicts match ReceiptRead: inject s3_bucket/s3_key from the first image.
    """
    recs = await receipt_repo.list_by_nit(session, uploader_nit, limit=limit, offset=offset)

    results = []
    for rec in recs:
        first_img = await get_first(session, receipt_id=rec.id)

        print(first_img)

        mime_type = first_img.get("mime_type") if first_img else None
        size_bytes = first_img.get("size_bytes") if first_img else None

        # Build status dict for ReceiptStatusRead
        status_dict = None
        if getattr(rec, "status", None):
            status_dict = {
                "id": rec.status.id,
                "code": rec.status.code,
                "label": rec.status.label,
                "is_final": rec.status.is_final,
            }

        results.append({
            "id": str(rec.id),
            "created_at": rec.created_at,
            "status": status_dict,
            "url": first_img.get("url"),
            "mime_type": mime_type,
            "size_bytes": size_bytes
        })

    return results

async def generate_accounting(
    session: AsyncSession,
    *,
    app,
    receipt_id: UUID,
    example_filename: str | None = None,
) -> dict:
    rec = await receipt_repo.get_receipt(session, receipt_id)
    if not rec or not rec.extracted_text:
        raise ValueError("Receipt missing or OCR text not available")

    example_file = example_filename or os.getenv("EXAMPLE_JSON_FILE", "comp.json")
    example_path = os.path.join(_RES_DIR, example_file)

    try:
        with open(example_path, "r", encoding="utf-8") as f:
            example_json = json.load(f)
    except FileNotFoundError as e:
        raise RuntimeError(f"Example JSON not found: {example_path}") from e
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Invalid example JSON: {example_path}") from e

    pucs = await erp_service.get_pucs(app)
    puc_nif = erp_service._pick_puc_nif(pucs)
    cuentas = await erp_service.get_cuentas(app, puc_nif["id"])

    prompt = render_template(
        "prompts/conta_v1.txt",
        {
            "ocr_text": rec.extracted_text,
            "puc_json": json.dumps(cuentas, ensure_ascii=False),
            "example_json": json.dumps(example_json, ensure_ascii=False),
        },
    )

    open(os.path.join(os.getenv("RESOURCES_DIR", "/app/resources"), "debug_prompt.txt"), "w", encoding="utf-8").write(prompt)

    reply = await LLMService().generate(prompt)
    reply = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip(), flags=re.IGNORECASE | re.MULTILINE)

    open(os.path.join(os.getenv("RESOURCES_DIR", "/app/resources"), "reply.txt"), "w", encoding="utf-8").write(reply)

    doc = json.loads(reply)

    rec.accounting_json = doc
    suggested = await receipt_status_repo.get_status_by_code(session, SUGGESTED_STATUS)
    if suggested:
        rec.status_id = suggested.id
    await session.commit()
    return receipt_to_dict(rec)

async def _set_status(session: AsyncSession, *, receipt_id: UUID, status_code: str) -> dict:
    rec = await receipt_repo.get_receipt(session, receipt_id)
    if not rec:
        raise ValueError("Receipt not found")
    st = await receipt_status_repo.get_status_by_code(session, status_code)
    if not st:
        raise RuntimeError(f"Status '{status_code}' not configured")

    rec.status_id = st.id
    await session.commit()
    await session.refresh(rec, attribute_names=["status"])
    return receipt_to_dict(rec)

async def accept_accounting(session: AsyncSession, *, receipt_id: UUID) -> dict:
    return await _set_status(session, receipt_id=receipt_id, status_code="accepted_accounting")

async def reject_accounting(session: AsyncSession, *, receipt_id: UUID) -> dict:
    return await _set_status(session, receipt_id=receipt_id, status_code="rejected_accounting")
