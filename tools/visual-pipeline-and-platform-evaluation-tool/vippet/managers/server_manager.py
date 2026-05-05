# SPDX-License-Identifier: Apache-2.0

"""
ServerManager - Business logic for server/machine management.

Provides thread-safe singleton for managing server records in the database.
"""

import logging
import threading
from typing import Optional

from sqlalchemy.exc import IntegrityError

from database import Server, SessionLocal

logger = logging.getLogger("server_manager")


class ServerManager:
    """
    Thread-safe singleton that manages server/machine records.
    
    Implements singleton pattern using __new__ with double-checked locking.
    All database operations are performed within session context managers
    to ensure proper transaction handling and resource cleanup.
    """

    _instance: Optional["ServerManager"] = None
    _lock = threading.Lock()

    def __new__(cls) -> "ServerManager":
        """Create or return singleton instance with double-checked locking."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def add_server(
        self,
        uuid: str,
        ip_address: str,
        cpu_sku: str,
        ram_size: int,
        kernel_version: str,
    ) -> Server:
        """
        Add a new server to the database.
        
        Args:
            uuid: Unique identifier for the server
            ip_address: IP address of the server
            cpu_sku: CPU SKU/model identifier
            ram_size: RAM size in GB
            kernel_version: Ubuntu kernel version
        
        Returns:
            Server: The created server record
        
        Raises:
            ValueError: If server with given UUID already exists
            ValueError: If any required field is invalid
        """
        # Validate inputs
        if not uuid or not uuid.strip():
            raise ValueError("UUID cannot be empty")
        if not ip_address or not ip_address.strip():
            raise ValueError("IP address cannot be empty")
        if not cpu_sku or not cpu_sku.strip():
            raise ValueError("CPU SKU cannot be empty")
        if ram_size <= 0:
            raise ValueError("RAM size must be positive")
        if not kernel_version or not kernel_version.strip():
            raise ValueError("Kernel version cannot be empty")

        db = SessionLocal()
        try:
            server = Server(
                uuid=uuid.strip(),
                ip_address=ip_address.strip(),
                cpu_sku=cpu_sku.strip(),
                ram_size=ram_size,
                kernel_version=kernel_version.strip(),
            )
            db.add(server)
            db.commit()
            db.refresh(server)
            logger.info(f"Added server {uuid}")
            return server
        except IntegrityError:
            db.rollback()
            raise ValueError(f"Server with UUID {uuid} already exists")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add server {uuid}: {e}")
            raise
        finally:
            db.close()

    def get_server(self, uuid: str) -> Optional[Server]:
        """
        Get a server by UUID.
        
        Args:
            uuid: Unique identifier of the server
        
        Returns:
            Server if found, None otherwise
        """
        db = SessionLocal()
        try:
            return db.query(Server).filter(Server.uuid == uuid).first()
        finally:
            db.close()

    def list_servers(self) -> list[Server]:
        """
        List all servers.
        
        Returns:
            List of all server records
        """
        db = SessionLocal()
        try:
            return db.query(Server).all()
        finally:
            db.close()

    def update_server(
        self,
        uuid: str,
        ip_address: Optional[str] = None,
        cpu_sku: Optional[str] = None,
        ram_size: Optional[int] = None,
        kernel_version: Optional[str] = None,
    ) -> Server:
        """
        Update server details.
        
        Args:
            uuid: Unique identifier of the server to update
            ip_address: New IP address (optional)
            cpu_sku: New CPU SKU (optional)
            ram_size: New RAM size in GB (optional)
            kernel_version: New kernel version (optional)
        
        Returns:
            Server: The updated server record
        
        Raises:
            ValueError: If server not found or validation fails
        """
        db = SessionLocal()
        try:
            server = db.query(Server).filter(Server.uuid == uuid).first()
            if not server:
                raise ValueError(f"Server with UUID {uuid} not found")

            # Update provided fields
            if ip_address is not None:
                if not ip_address.strip():
                    raise ValueError("IP address cannot be empty")
                server.ip_address = ip_address.strip()

            if cpu_sku is not None:
                if not cpu_sku.strip():
                    raise ValueError("CPU SKU cannot be empty")
                server.cpu_sku = cpu_sku.strip()

            if ram_size is not None:
                if ram_size <= 0:
                    raise ValueError("RAM size must be positive")
                server.ram_size = ram_size

            if kernel_version is not None:
                if not kernel_version.strip():
                    raise ValueError("Kernel version cannot be empty")
                server.kernel_version = kernel_version.strip()

            db.commit()
            db.refresh(server)
            logger.info(f"Updated server {uuid}")
            return server
        except ValueError:
            db.rollback()
            raise
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update server {uuid}: {e}")
            raise
        finally:
            db.close()

    def delete_server(self, uuid: str) -> bool:
        """
        Delete a server from the database.
        
        Args:
            uuid: Unique identifier of the server to delete
        
        Returns:
            True if server was deleted, False if not found
        """
        db = SessionLocal()
        try:
            server = db.query(Server).filter(Server.uuid == uuid).first()
            if not server:
                return False

            db.delete(server)
            db.commit()
            logger.info(f"Deleted server {uuid}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to delete server {uuid}: {e}")
            raise
        finally:
            db.close()
