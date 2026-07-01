"""
Database configuration and initialization for ViPPET backend.

Handles SQLAlchemy async engine setup, session factory, and database lifecycle.
"""

import logging
import os
from pathlib import Path
from typing import Any, AsyncGenerator
from sqlalchemy.engine import make_url

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    AsyncSession,
    async_sessionmaker,
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool

logger = logging.getLogger(__name__)

# Base class for all ORM models
Base = declarative_base()

# Database URL from environment or default
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",  # In-memory SQLite for development
)

# SQLAlchemy async engine configuration
engine = None
async_session_maker = None


def _load_orm_models() -> None:
    """
    Import ORM model modules so they register with Base metadata.

    Add SQLAlchemy ORM classes in orm_models.py (or modules imported from it).
    """
    import orm_models  # noqa: F401


def _ensure_sqlite_database_path() -> None:
    """
    Ensure the parent directory exists for file-based SQLite databases.

    Raises:
        PermissionError: If the database directory exists but is not writable.
    """
    if "sqlite" not in DATABASE_URL:
        return

    db_path = make_url(DATABASE_URL).database
    if not db_path or db_path == ":memory:":
        return

    db_dir = Path(db_path).expanduser().parent
    db_dir.mkdir(parents=True, exist_ok=True)

    if not os.access(db_dir, os.W_OK):
        raise PermissionError(
            f"SQLite directory is not writable: '{db_dir}'. "
            "Check docker volume permissions for shared/db."
        )


def _get_engine_kwargs() -> dict[str, Any]:
    """
    Get engine kwargs based on database type.

    Returns:
        dict: Engine configuration including pooling, echo, and type-specific options
    """
    engine_kwargs: dict[str, Any] = {
        "echo": os.environ.get("DB_ECHO", "false").lower() == "true",
        "future": True,
    }

    # Use NullPool for SQLite (avoids locking issues)
    if "sqlite" in DATABASE_URL:
        engine_kwargs["poolclass"] = NullPool
    else:
        # For production databases (PostgreSQL, MySQL, etc.)
        engine_kwargs.update(
            {
                "pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
                "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
                "pool_pre_ping": True,  # Verify connections before using
                "pool_recycle": 3600,  # Recycle connections every hour
            }
        )

    return engine_kwargs


async def init_db() -> None:
    """
    Initialize database engine and session factory.

    Call this during FastAPI startup to set up the database connection.
    """
    global engine, async_session_maker

    logger.info(f"Initializing database: {DATABASE_URL}")

    # For file-based SQLite, ensure the DB directory exists before connecting.
    _ensure_sqlite_database_path()

    # Ensure ORM models are imported before creating metadata-driven tables.
    _load_orm_models()

    # Create async engine
    engine = create_async_engine(
        DATABASE_URL,
        **_get_engine_kwargs(),
    )

    # Create async session factory
    async_session_maker = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    # Create tables if they don't exist
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Seed startup data in an idempotent way.
    if os.environ.get("DB_SEED_ON_STARTUP", "true").lower() == "true":
        from db_seed import seed_initial_data

        await seed_initial_data(async_session_maker)

    logger.info("Database initialization complete")


async def close_db() -> None:
    """
    Close database connections.

    Call this during FastAPI shutdown to clean up database resources.
    """
    global engine

    if engine:
        await engine.dispose()
        logger.info("Database connections closed")


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI routes to get a database session.

    Usage:
        @app.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            result = await session.execute(select(Item))
            return result.scalars().all()

    Yields:
        AsyncSession: SQLAlchemy async session

    Raises:
        RuntimeError: If database has not been initialized
    """
    if not async_session_maker:
        raise RuntimeError("Database not initialized. Call init_db() first.")

    async with async_session_maker() as session:
        try:
            yield session
        except Exception as e:
            await session.rollback()
            logger.error(f"Database session error: {e}")
            raise
        finally:
            await session.close()
