# services/receipt_service.py
import csv, io, re, json, os

from uuid import UUID
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Iterable

from repositories import receipt_repo
from repositories import receipt_status_repo
from services.s3_service import presign_url
from services.llm_service import LLMService, render_template
from services.erp_service import erp_service
from services.receipt_image_service import create_images, get_images, get_first
from repositories import receipt_image_repo

DEFAULT_STATUS_CODE = "uploaded"
SUGGESTED_STATUS = "suggested"
_RES_DIR = os.getenv("RESOURCES_DIR", "/app/resources")

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

    rec_id = rec.id

    created_images = await create_images(
        session,
        uploader_nit=uploader_nit,
        receipt_id=rec_id,
        images=images or [],
    )

    await session.refresh(rec, attribute_names=["updated_at", "status_id"])

    status_obj = {
        "id": status.id,
        "code": status.code,
        "label": status.label,
        "is_final": status.is_final,
    }

    primary = created_images[0] if created_images else await get_first(session, receipt_id=rec_id)
    url = primary.get("url") if primary else None
    mime_type = primary.get("mime_type") if primary else None
    size_bytes = primary.get("size_bytes") if primary else None

    return {
        "id": str(rec_id),
        "created_at": rec.created_at,
        "status": status_obj,
        "summary": rec.summary,
        "url": url,
        "mime_type": mime_type,
        "size_bytes": size_bytes,
        "status_id": rec.status_id,
        "accounting_json": rec.accounting_json,
        "updated_at": rec.updated_at
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
        "summary": rec.summary,
        "images": images
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
            "summary": rec.summary,
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
    """
    Build the LLM prompt using:
      - OCR texts per image (prefixed with a page header).
      - PUC as a compact pipe-delimited CSV (via cuentas_to_pipe_csv).
    Then call the LLM, parse the JSON, and persist the suggested accounting.
    """
    
    rec = await receipt_repo.get_receipt(session, receipt_id)
    if not rec:
        raise ValueError("Receipt missing")

    images = await receipt_image_repo.get_by_receipt(session, receipt_id)
    if not images:
        raise ValueError("No images for this receipt")

    ocr_text: List[str] = []

    for img in images:
        header = f"--- Image-text-{img.img_number} ---"
        body = (img.extracted_text or "").strip()
        ocr_text.append(f"{header}\n{body}")

    ocr_text = "\n\n".join(ocr_text).strip()

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
    puc_csv = cuentas_to_pipe_csv(cuentas)

    prompt = render_template(
        "prompts/conta_v2.txt",
        {
            "ocr_text": ocr_text,
            "puc_csv": puc_csv,
            "example_json": json.dumps(example_json, ensure_ascii=False),
        },
    )

    open(os.path.join(os.getenv("RESOURCES_DIR", "/app/resources"), "debug_prompt.txt"), "w", encoding="utf-8").write(prompt)

    reply = await LLMService().generate(prompt)
    reply = re.sub(r"^```(?:json)?\s*|\s*```$", "", reply.strip(), flags=re.IGNORECASE | re.MULTILINE)

    open(os.path.join(os.getenv("RESOURCES_DIR", "/app/resources"), "reply.txt"), "w", encoding="utf-8").write(reply)

    doc = json.loads(reply)
    rec.accounting_json = doc

    desc = (doc.get("descripcion") or doc.get("description") or "").strip()

    if desc:
        rec.summary = desc[:52]
    else:
        rec.summary = "Contabilización sugerida"[:52]
    
    suggested = await receipt_status_repo.get_status_by_code(session, SUGGESTED_STATUS)

    if suggested:
        rec.status_id = suggested.id
    await session.commit() 

    return {
        "id": str(rec.id),
        "uploader_nit": rec.uploader_nit,
        "s3_bucket": getattr(rec, "s3_bucket", None),
        "s3_key": getattr(rec, "s3_key", None),
        "mime_type": getattr(rec, "mime_type", None),
        "size_bytes": getattr(rec, "size_bytes", None),
        "extracted_text": getattr(rec, "extracted_text", None),
        "url": None,
        "created_at": rec.created_at,
        "status_id": rec.status_id,
        "accounting_json": rec.accounting_json,
        "summary": rec.summary
    }

async def accept_accounting(session: AsyncSession, *, receipt_id: UUID) -> dict:
    return await _set_status(session, receipt_id=receipt_id, status_code="accepted_accounting")

async def reject_accounting(session: AsyncSession, *, receipt_id: UUID) -> dict:
    return await _set_status(session, receipt_id=receipt_id, status_code="rejected_accounting")

async def _set_status(session: AsyncSession, *, receipt_id: UUID, status_code: str) -> dict:
    rec = await receipt_repo.get_receipt(session, receipt_id)
    if not rec:
        raise ValueError("Receipt not found")

    st = await receipt_status_repo.get_status_by_code(session, status_code)
    if not st:
        raise RuntimeError(f"Status '{status_code}' not configured")

    rec.status_id = st.id
    await session.commit()

    await session.refresh(rec, attribute_names=["updated_at", "status", "summary", "created_at"])

    status_obj = {
        "id": st.id,
        "code": st.code,
        "label": st.label,
        "is_final": st.is_final,
    }

    return {
        "id": str(rec.id),
        "created_at": rec.created_at,
        "status": status_obj,
        "summary": rec.summary,
        "status_id": rec.status_id,
        "accounting_json": rec.accounting_json,
        "updated_at": rec.updated_at,
    }

def cuentas_to_pipe_csv(cuentas: Iterable[dict]) -> str:
    """
    Process PUC accounts into a compact pipe-delimited CSV (PUC → CSV).
    Rules (static, no configurable params):
      1) Drop any account whose field "numero" starts with '3' or '4'.
      2) Remove the property "cuenta_local" if present.
      3) Remove the property "pide_documento_referencia" if present.
    Column order is preserved by first appearance across the cleaned rows.

    Returns:
        str: CSV string delimited by '|', with a single header row.
    """

    cleaned: list[dict] = []
    for c in cuentas or []:
        numero = str(c.get("numero", "")).strip()
        if numero.startswith(("3", "4")):
            continue

        row = dict(c)
        row.pop("cuenta_local", None)
        row.pop("pide_documento_referencia", None)
        cleaned.append(row)

    columns: list[str] = []
    for row in cleaned:
        for k in row.keys():
            if k not in columns:
                columns.append(k)

    if not columns:
        return "numero|nombre\n"  # minimal header, no data rows

    buf = io.StringIO()
    writer = csv.DictWriter(
        buf,
        fieldnames=columns,
        delimiter="|",
        lineterminator="\n",
        extrasaction="ignore",
    )
    writer.writeheader()
    for row in cleaned:
        safe_row = {k: "" if row.get(k) is None else str(row.get(k)) for k in columns}
        writer.writerow(safe_row)

    return buf.getvalue()
