# SPDX-License-Identifier: Apache-2.0

"""
Database module for ViPPET.

Provides SQLAlchemy ORM models and database session management.
"""

import logging
import os
from pathlib import Path
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger("database")

# Database file path - directory will be created in init_db()
DB_DIR = Path(os.environ.get("DB_DIR", "/shared/database"))
DB_PATH = DB_DIR / "vippet.db"

# Create SQLite database engine
DATABASE_URL = f"sqlite:///{DB_PATH}"
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # Required for SQLite
    echo=False,  # Set to True for SQL query logging
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
    Creates the database directory if it doesn't exist.
    """
    # Create database directory if it doesn't exist
    DB_DIR.mkdir(parents=True, exist_ok=True)
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info(f"Database initialized at {DB_PATH}")


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
