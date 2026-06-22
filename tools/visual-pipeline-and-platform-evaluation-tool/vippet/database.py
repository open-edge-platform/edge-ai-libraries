"""
Database configuration and initialization for ViPPET backend.

Handles SQLAlchemy async engine setup, session factory, and database lifecycle.
"""

import logging
import os
from typing import Any, AsyncGenerator

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
