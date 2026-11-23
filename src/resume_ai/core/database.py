from collections.abc import AsyncIterator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from resume_ai.core.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_pre_ping=True,
)

SessionFactory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionFactory() as session:
        yield session


# Idempotent patches for columns added to tables that already exist.
# `create_all` only creates missing tables, never missing columns.
# Replace with Alembic migrations once the schema settles.
SCHEMA_PATCHES = [
    "ALTER TABLE resumes ADD COLUMN IF NOT EXISTS file_hash VARCHAR(64)",
    "CREATE INDEX IF NOT EXISTS ix_resumes_file_hash ON resumes (file_hash)",
]


async def create_tables() -> None:
    # Import models so they are registered on Base.metadata.
    import resume_ai.models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

        for statement in SCHEMA_PATCHES:
            await connection.execute(text(statement))


async def close_database() -> None:
    await engine.dispose()
