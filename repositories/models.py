# repositories/models.py
from __future__ import annotations
from datetime import datetime
from uuid import uuid4, UUID

from sqlalchemy import (
    String, Text, DateTime, ForeignKey, Boolean, SmallInteger, BigInteger,
    UniqueConstraint, Index, text
)

from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from repositories.db import Base

UTC_NOW_SQL = text("timezone('utc', now())")

class TimestampMixin:
    """Adds created_at / updated_at with UTC defaults at DB level."""
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=UTC_NOW_SQL,
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=UTC_NOW_SQL,
        server_onupdate=UTC_NOW_SQL,
        nullable=False,
    )

class ReceiptStatus(Base):
    __tablename__ = "receipt_statuses"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    sort_order: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0, server_default="0")

class Receipt(TimestampMixin, Base):
    __tablename__ = "receipts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)
    uploader_nit: Mapped[str] = mapped_column(String(30), nullable=False)
    accounting_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    status_id: Mapped[int] = mapped_column(ForeignKey("receipt_statuses.id"), nullable=False)
    status: Mapped[ReceiptStatus] = relationship(lazy="joined")

    images: Mapped[list["ReceiptImage"]] = relationship(
        "ReceiptImage",
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="ReceiptImage.img_number",
    )

class ReceiptImage(TimestampMixin, Base):
    __tablename__ = "receipt_images"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid4)

    receipt_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("receipts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    receipt: Mapped[Receipt] = relationship("Receipt", back_populates="images")

    s3_bucket: Mapped[str] = mapped_column(String(128), nullable=False)
    s3_key: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    img_number: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1, server_default="1")

    extracted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    textract_job_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    ocr_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    ocr_error_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ocr_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    ocr_error_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("receipt_id", "img_number", name="uq_receipt_img_number"),
        Index("ix_receipt_images_s3key_trgm", "s3_key",
              postgresql_using="gin",
              postgresql_ops={"s3_key": "gin_trgm_ops"}),
    )
