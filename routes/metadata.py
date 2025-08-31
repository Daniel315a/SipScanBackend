from typing import List
from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.ext.asyncio import AsyncSession

from repositories.db import get_session
from repositories import receipt_status_repo

router = APIRouter(prefix="/metadata", tags=["metadata"])

class ReceiptStatusRead(BaseModel):
    code: str
    label: str
    is_final: bool
    is_active: bool
    sort_order: int

    model_config = ConfigDict(from_attributes=True)

@router.get("/receipt-statuses", response_model=List[ReceiptStatusRead])
async def list_receipt_statuses(session: AsyncSession = Depends(get_session)):
    statuses = await receipt_status_repo.list_statuses(session)
    return list(statuses)
