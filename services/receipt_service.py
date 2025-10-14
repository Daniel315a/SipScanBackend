import asyncio
import logging
import json
import os
import re

from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from repositories import receipt_repo
from repositories import receipt_status_repo
from services.s3_service import upload_image, presign_url
from services.ocr_service import get_ocr_provider
from services.llm_service import LLMService, render_template
from services.erp_service import erp_service

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

    try:
        ocr = get_ocr_provider()
        text = await asyncio.to_thread(ocr.extract_text_from_s3, bucket=bucket, key=key)
        rec.extracted_text = text
        processed = await receipt_status_repo.get_status_by_code(session, "processed")
        if processed:
            rec.status_id = processed.id
        await session.commit()
        await session.refresh(rec)
    except Exception as e:
        logging.getLogger(__name__).exception("OCR failed for %s/%s", bucket, key)

        err_type = type(e).__name__
        err_code = None
        err_msg = str(e)
        resp = getattr(e, "response", None)
        if isinstance(resp, dict):
            err_code = (resp.get("Error") or {}).get("Code") or err_code
            err_msg = (resp.get("Error") or {}).get("Message") or err_msg

        rec.ocr_error_type = err_type
        rec.ocr_error_code = err_code
        rec.ocr_error = f"{err_type}{f' [{err_code}]' if err_code else ''}: {err_msg}"
        rec.ocr_error_at = datetime.now(timezone.utc)

        failed = await receipt_status_repo.get_status_by_code(session, "failed")
        if failed:
            rec.status_id = failed.id

    url = presign_url(bucket, key)

    return receipt_to_dict(rec)

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
