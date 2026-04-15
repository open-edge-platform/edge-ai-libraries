"""Application lifecycle helpers for the MCP REST proxy."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
import logging

from mcp.server.fastmcp import FastMCP

from .client import ProxyApiClient
from .config import Settings
from .filters import ProxyFilterConfig
from .models import ApiCatalog


@dataclass(slots=True)
class AppContext:
    """Typed lifespan context shared with all MCP handlers."""

    settings: Settings
    catalog: ApiCatalog
    filter_config: ProxyFilterConfig
    client: ProxyApiClient


def build_lifespan(
    settings: Settings,
    catalog: ApiCatalog,
    filter_config: ProxyFilterConfig,
    client: ProxyApiClient,
    logger: logging.Logger,
):
    """Create the FastMCP lifespan function for the configured settings."""

    @asynccontextmanager
    async def lifespan(_: FastMCP) -> AsyncIterator[AppContext]:
        """Create and clean up the shared proxy client used by tools and resources."""

        await client.open()

        logger.info(
            "Starting MCP REST proxy %s on %s:%s%s against %s",
            filter_config.server_name,
            settings.mcp_host,
            settings.mcp_port,
            settings.mcp_path,
            catalog.base_url,
        )
        try:
            yield AppContext(
                settings=settings,
                catalog=catalog,
                filter_config=filter_config,
                client=client,
            )
        finally:
            await client.close()
            logger.info("Stopped MCP REST proxy")

    return lifespan
