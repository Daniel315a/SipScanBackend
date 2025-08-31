import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sipscan_user:supersecretpassword@db:5432/sipscan",
)

# Async engine for SQLAlchemy 2.x
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Session factory for DI in FastAPI
SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False, class_=AsyncSession)

class Base(DeclarativeBase):
    """Declarative base for ORM models."""
    pass

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    async with SessionLocal() as session:
        yield session
