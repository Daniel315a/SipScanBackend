from __future__ import annotations
from datetime import datetime
from uuid import uuid4, UUID

from sqlalchemy import String, Text, DateTime, func, ForeignKey, Boolean, SmallInteger, BigInteger
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from repositories.db import Base

class ReceiptStatus(Base):
    """Metadata table for receipt statuses."""
    __tablename__ = "receipt_statuses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

class Receipt(Base):
    """Expense receipt uploaded by a user (local image storage for now)."""
    __tablename__ = "receipts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    uploader_nit: Mapped[str] = mapped_column(String(30), nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    textract_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # --- Accounting
    accounting_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)  

    # --- OCR error tracking
    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ocr_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ocr_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status_id: Mapped[int] = mapped_column(ForeignKey("receipt_statuses.id"), nullable=False)
    status: Mapped[ReceiptStatus] = relationship(lazy="joined")

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
