from uuid import UUID
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Request
from pydantic import BaseModel, ConfigDict, AnyHttpUrl, computed_field, Field
from typing import cast, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime

from repositories.db import get_session
from services import receipt_service

router = APIRouter(prefix="/receipts", tags=["receipts"])

# Restrict accepted content types (extend as needed)
ALLOWED_IMAGE_TYPES: set[str] = {
    "image/png", "image/jpeg", "image/webp", "image/gif", "image/bmp", "image/tiff", "image/heic"
}

class ReceiptCreated(BaseModel):
    id: UUID
    uploader_nit: str
    mime_type: str | None = None
    size_bytes: int | None = None
    extracted_text: str | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ReceiptStatusRead(BaseModel):
    id: int
    code: str
    label: str
    is_final: bool
    model_config = ConfigDict(from_attributes=True)

class ReceiptRead(BaseModel):
    id: UUID
    s3_bucket: str = Field(exclude=True)
    s3_key: str = Field(exclude=True)
    uploader_nit: str
    mime_type: str | None = None
    size_bytes: int | None = None
    extracted_text: str | None = None
    accounting_json: dict[str, Any] | None = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
    status: Optional[ReceiptStatusRead] = None

    @computed_field
    @property
    def url(self) -> AnyHttpUrl:
        from services.s3_service import presign_url
        return cast(AnyHttpUrl, presign_url(self.s3_bucket, self.s3_key))

@router.post("", response_model=ReceiptCreated, status_code=201)
async def create_receipt(
    uploader_nit: str = Form(..., min_length=3, max_length=30),
    image: UploadFile = File(..., description="Receipt image file"),
    session: AsyncSession = Depends(get_session),
):
    """Receive an image via multipart and create the receipt (local storage for now)."""
    if image.content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported media type. Please upload a valid image.")
            
    return await receipt_service.create_receipt_from_upload_s3(
        session, uploader_nit=uploader_nit, image=image
    )

@router.get("/{receipt_id}", response_model=ReceiptRead)
async def get_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    rec = await receipt_service.get_receipt(session, receipt_id)

    if not rec:
        raise HTTPException(status_code=404, detail="Receipt not found")
    
    return ReceiptRead.model_validate(rec)

@router.get("/by-nit/{uploader_nit}", response_model=List[ReceiptRead])
async def list_receipts_by_nit(
    uploader_nit: str,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    """List receipts filtered by uploader NIT."""
    recs = await receipt_service.list_by_nit(session, uploader_nit, limit=limit, offset=offset)

    return [ReceiptRead.model_validate(r) for r in recs]

@router.post("/{receipt_id}/suggest", response_model=ReceiptRead)
async def suggest_accounting(
    receipt_id: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
):
    try:
        rec_dict = await receipt_service.generate_accounting(
            session, app=request.app, receipt_id=receipt_id
        )
        return rec_dict
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Generation failed")

@router.post("/{receipt_id}/accept", response_model=ReceiptRead)
async def accept_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await receipt_service.accept_accounting(session, receipt_id=receipt_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{receipt_id}/reject", response_model=ReceiptRead)
async def reject_receipt(receipt_id: UUID, session: AsyncSession = Depends(get_session)):
    try:
        return await receipt_service.reject_accounting(session, receipt_id=receipt_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    