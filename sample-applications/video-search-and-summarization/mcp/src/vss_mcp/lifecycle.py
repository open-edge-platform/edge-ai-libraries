"""Application lifecycle helpers for the VSS MCP server."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

from mcp.server.fastmcp import FastMCP

from .client import VSSApiClient
from .config import Settings


@dataclass(slots=True)
class AppContext:
    """Typed lifespan context shared with all MCP handlers."""

    settings: Settings
    client: VSSApiClient


def build_lifespan(settings: Settings, logger: logging.Logger):
    """Create the FastMCP lifespan function for the configured settings."""

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
        """Create and clean up the shared VSS client used by tools and resources."""

        client = VSSApiClient(settings)
        await client.open()

        logger.info(
            "Starting VSS MCP server on %s:%s%s against %s",
            settings.mcp_host,
            settings.mcp_port,
            settings.mcp_path,
            settings.vss_base_url,
        )
        try:
            yield AppContext(settings=settings, client=client)
        finally:
            await client.close()
            logger.info("Stopped VSS MCP server")

    return lifespan
