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

# Límites del pool de conexiones, configurables por entorno (sin recompilar).
# Regla de oro:  pods × UVICORN_WORKERS × (POOL_SIZE + MAX_OVERFLOW) <= Postgres max_connections
#   Ej. 3 pods × 2 workers × (5 + 5) = 60  <  100 (max_connections por defecto).
DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "5"))        # conexiones persistentes por proceso
DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "5"))  # extra temporales bajo pico
DB_POOL_TIMEOUT = int(os.getenv("DB_POOL_TIMEOUT", "30")) # s esperando una conexión libre antes de fallar
DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))  # recicla conexiones cada 30 min

# Async engine for SQLAlchemy 2.x
engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,       # descarta conexiones muertas antes de usarlas
    pool_size=DB_POOL_SIZE,
    max_overflow=DB_MAX_OVERFLOW,
    pool_timeout=DB_POOL_TIMEOUT,
    pool_recycle=DB_POOL_RECYCLE,
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
