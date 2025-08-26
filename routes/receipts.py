from uuid import UUID
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form
from pydantic import BaseModel, ConfigDict, AnyHttpUrl, computed_field
from typing import cast
from sqlalchemy.ext.asyncio import AsyncSession

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
    s3_bucket: str
    s3_key: str
    mime_type: str | None = None
    size_bytes: int | None = None
    model_config = ConfigDict(from_attributes=True)

class ReceiptRead(BaseModel):
    id: UUID
    uploader_nit: str
    s3_bucket: str
    s3_key: str
    mime_type: str | None = None
    size_bytes: int | None = None

    model_config = ConfigDict(from_attributes=True)

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
