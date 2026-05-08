# SPDX-License-Identifier: Apache-2.0

"""
Database module for ViPPET.

Provides SQLAlchemy ORM models and database session management.
"""

import logging
import os
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger("database")

# PostgreSQL connection URL from environment variable
# Format: postgresql://user:password@host:5432/dbname
DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://vippet:Intel123@10.158.108.69:5432/vippet_db",
)

engine = create_engine(
    DATABASE_URL,
    echo=False,  # Set to True for SQL query logging
    pool_pre_ping=True,  # Verify connections before use
    pool_size=5,
    max_overflow=10,
)

# Session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for ORM models
Base = declarative_base()


class Server(Base):
    """
    ORM model for server/machine information.
    
    Attributes:
        uuid: Unique identifier for the server (primary key)
        ip_address: IP address of the server
        cpu_sku: CPU SKU/model identifier
        ram_size: RAM size in GB
        kernel_version: Ubuntu kernel version
    """
    __tablename__ = "servers"

    uuid = Column(String, primary_key=True, index=True)
    ip_address = Column(String, nullable=False)
    cpu_sku = Column(String, nullable=False)
    ram_size = Column(Integer, nullable=False)  # in GB
    kernel_version = Column(String, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<Server(uuid={self.uuid}, ip={self.ip_address}, "
            f"cpu={self.cpu_sku}, ram={self.ram_size}GB)>"
        )


def init_db() -> None:
    """
    Initialize the database by creating all tables.
    
    This should be called once at application startup.
    Connects to the PostgreSQL database and creates tables if they don't exist.
    """
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized (PostgreSQL)")


def get_db() -> Session:
    """
    Get a database session.
    
    Yields:
        Session: SQLAlchemy database session
    
    Usage:
        with get_db() as db:
            # Use db session
            servers = db.query(Server).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
