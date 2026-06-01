from uuid import UUID
import asyncio

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repositories.db import get_session, get_sessionmaker
from repositories import receipt_repo
from services import receipt_service
from services import pdf_service
from routes.receipts import ReceiptFromTextInput, ReceiptRead, ws_manager

router = APIRouter(prefix="/receipts", tags=["receipts-v2"])


@router.post("/from-text", response_model=ReceiptRead, status_code=201)
async def create_receipt_from_text(
    body: ReceiptFromTextInput,
    session: AsyncSession = Depends(get_session),
    session_factory: "async_sessionmaker[AsyncSession]" = Depends(get_sessionmaker),
    request: Request = None,
):
    """Create a receipt from raw text, skipping image upload and OCR."""
    try:
        result = await receipt_service.create_from_text(
            session, uploader_nit=body.uploader_nit
        )

        receipt_id = UUID(str(result["id"]))
        receipt_text = body.text
        uploader_nit = body.uploader_nit

        async def _bg_generate():
            try:
                async with session_factory() as bg_session:
                    await receipt_service.generate_accounting(
                        bg_session,
                        app=request.app,
                        receipt_id=receipt_id,
                        receipt_text=receipt_text,
                    )

                    rec = await receipt_repo.get_receipt(bg_session, receipt_id)

                    status_obj = None
                    if getattr(rec, "status", None):
                        status_obj = {
                            "id": rec.status.id,
                            "code": rec.status.code,
                            "label": rec.status.label,
                            "is_final": rec.status.is_final,
                        }

                    await ws_manager.broadcast(uploader_nit, {
                        "event": "suggestion_completed",
                        "receipt_id": str(rec.id),
                        "created_at": rec.created_at.isoformat(),
                        "status": status_obj,
                        "summary": rec.summary,
                    })
            except Exception as e:
                import logging
                logging.exception("Background from-text generate task failed: %s", e)

        asyncio.create_task(_bg_generate())

        return result

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{receipt_id}/pdf")
async def get_receipt_pdf(
    receipt_id: UUID,
    session: AsyncSession = Depends(get_session),
):
    """Download an accounting PDF for the given receipt.

    Returns 404 if the receipt does not exist.
    Returns 422 if accounting_json is not yet available on the receipt.
    """
    receipt = await receipt_repo.get_receipt(session, receipt_id)
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")

    if not receipt.accounting_json:
        raise HTTPException(
            status_code=422,
            detail="El comprobante aún no tiene datos contables generados (accounting_json vacío).",
        )

    pdf_bytes = pdf_service.generate_accounting_pdf(receipt.accounting_json)

    filename = f"comprobante_{receipt_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
