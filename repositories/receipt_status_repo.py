from typing import Sequence
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from repositories.models import ReceiptStatus

DEFAULT_RECEIPT_STATUSES: list[tuple[str, str, bool, int]] = [
    ("uploaded",  "Uploaded",  False, 10),
    ("processed", "Processed", True,  20),
    ("failed",    "Failed",    True,  30),
]

async def get_status_by_code(session: AsyncSession, code: str) -> ReceiptStatus | None:
    stmt = select(ReceiptStatus).where(ReceiptStatus.code == code)
    res = await session.execute(stmt)
    return res.scalar_one_or_none()

async def list_statuses(session: AsyncSession) -> Sequence[ReceiptStatus]:
    stmt = (
        select(ReceiptStatus)
        .where(ReceiptStatus.is_active.is_(True))
        .order_by(ReceiptStatus.sort_order, ReceiptStatus.id)
    )
    res = await session.execute(stmt)

    return res.scalars().all()

async def ensure_default_statuses(session: AsyncSession) -> None:
    for code, label, is_final, sort_order in DEFAULT_RECEIPT_STATUSES:
        existing = await get_status_by_code(session, code)
        if not existing:
            session.add(ReceiptStatus(code=code, label=label, is_final=is_final, sort_order=sort_order))
    await session.commit()
