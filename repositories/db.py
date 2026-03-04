# repositories/db.py
import os
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://sipscan_user:supersecretpassword@db:5432/sipscan",
)

# Render and other platforms may provide postgres:// or postgresql:// — normalize to asyncpg dialect.
DATABASE_URL = (
    DATABASE_URL
    .replace("postgresql://", "postgresql+asyncpg://", 1)
    .replace("postgres://", "postgresql+asyncpg://", 1)
)

# Async engine for SQLAlchemy 2.x
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
)

# Session factory for DI in FastAPI
session_factory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)

class Base(DeclarativeBase):
    """Declarative base for ORM models."""
    pass

async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields an AsyncSession."""
    async with session_factory() as session:
        yield session

def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Provide the async_sessionmaker for background jobs, etc."""
    return session_factory
