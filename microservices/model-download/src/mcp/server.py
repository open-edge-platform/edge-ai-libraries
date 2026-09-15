# SPDX-FileCopyrightText: (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""
MCP server for the Model Download microservice.

Exposes model download, conversion, and management capabilities as MCP tools
and resources so that LLM agents (Claude Desktop, Copilot, etc.) can interact
with the service programmatically.

Run via:
    python -m src.mcp                              # stdio
    python -m src.mcp --transport http --port 8080  # HTTP
    fastmcp run src/mcp/server.py:mcp               # FastMCP CLI
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
from typing import Any, Dict, List, Optional

from fastmcp import FastMCP, Context

from src.api.models import (
    ModelDownloadRequest,
    ModelHub,
    ModelListItem,
    ModelListRequest,
    ModelListResponse,
    ModelRequest,
)
from src.core.interfaces import ListingAuthError, ListingNotSupportedError
from src.core.model_manager import ModelManager
from src.core.model_submission import ModelSubmissionError, submit_models
from src.core.plugin_registry import PluginRegistry
from src.mcp.prompts import register_skill_prompts
from src.utils.helper import get_hub_config_keys
from src.utils.logging import logger

# ---------------------------------------------------------------------------
# Shared core initialisation (same as FastAPI's module-level setup)
# ---------------------------------------------------------------------------

plugin_registry = PluginRegistry()
plugins_package = importlib.import_module("src.plugins")
plugin_registry.discover_plugins(plugins_package)

models_dir = os.getenv("MODELS_DIR", "./models")
model_manager = ModelManager(plugin_registry, default_dir=models_dir)

_background_tasks: set[asyncio.Task[Any]] = set()


def configure_runtime(
    registry: PluginRegistry,
    manager: ModelManager,
    runtime_models_dir: str,
    background_tasks: set[asyncio.Task[Any]],
) -> None:
    """Use an application's shared model-download runtime."""

    global plugin_registry, model_manager, models_dir, _background_tasks
    plugin_registry = registry
    model_manager = manager
    models_dir = runtime_models_dir
    _background_tasks = background_tasks


# ---------------------------------------------------------------------------
# FastMCP server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="model-download",
    instructions=(
        "Download, convert, and manage AI models from HuggingFace, Ollama, "
        "Ultralytics, Geti, Pipeline Zoo, and more. Use the tools below to "
        "submit download/conversion jobs, monitor their progress, browse "
        "available models on each hub, and discover which plugins are active."
    ),
)

# Register prompts from the model-download-user skill files
_prompt_count = register_skill_prompts(mcp)
if _prompt_count:
    logger.info("mcp_prompts_registered", count=_prompt_count)

# ---- helpers ---------------------------------------------------------------


def _job_snapshots() -> List[Dict[str, Any]]:
    """Return thread-safe copies of all job records."""
    return model_manager.list_jobs(limit=2**31 - 1)


def _plugin_info() -> Dict[str, Any]:
    """Build the plugin info dict (mirrors GET /plugins)."""
    plugins_info: Dict[str, list] = {}
    for plugin_type in plugin_registry.plugins:
        plugins_info[plugin_type] = []
        for plugin_name, plugin in plugin_registry.plugins.get(plugin_type, {}).items():
            can_handle_parallel = hasattr(plugin, "get_download_tasks") and callable(
                getattr(plugin, "get_download_tasks")
            )
            plugin_supported_hubs = plugin.plugin_supported_hubs()

            if len(plugin_supported_hubs) > 1:
                hub_description = getattr(plugin, "hub_description", None)
                hub_capabilities = getattr(plugin, "hub_capabilities", None)
                for hub in plugin_supported_hubs:
                    is_available, _ = plugin_registry.hub_is_available(hub)
                    if not is_available:
                        continue
                    hub_desc = hub_description(hub) if callable(hub_description) else None
                    hub_caps: Dict[str, Any] = {"supports_parallel_downloads": can_handle_parallel}
                    if callable(hub_capabilities):
                        hub_caps.update(hub_capabilities(hub))
                    plugins_info[plugin_type].append(
                        {
                            "name": hub,
                            "type": plugin_type,
                            "description": hub_desc or "No description available",
                            "capabilities": hub_caps,
                            "hub_config_keys": get_hub_config_keys(plugin, hub),
                            "available": True,
                            "unavailable_reason": None,
                        }
                    )
                continue

            capabilities = {
                "supports_parallel_downloads": can_handle_parallel,
                "supports_listing": getattr(plugin, "supports_listing", False),
                "listing_filter_fields": getattr(plugin, "listing_filter_fields", []),
            }
            description = getattr(plugin, "__doc__", "No description available").strip()
            is_available, reason = plugin_registry.hub_is_available(plugin_name)
            plugins_info[plugin_type].append(
                {
                    "name": plugin_name,
                    "type": plugin_type,
                    "description": description,
                    "capabilities": capabilities,
                    "hub_config_keys": get_hub_config_keys(plugin, plugin_name),
                    "available": is_available,
                    "unavailable_reason": reason if not is_available else None,
                }
            )

    total_plugins = sum(len(plugins) for plugins in plugins_info.values())
    available_plugins = sum(
        1
        for plugin_type in plugins_info
        for plugin in plugins_info[plugin_type]
        if plugin.get("available", False)
    )
    return {
        "available_plugins": plugins_info,
        "total_count": total_plugins,
        "available_count": available_plugins,
    }


# ---- MCP tools -------------------------------------------------------------


@mcp.tool
def health_check() -> dict:
    """Check whether the model-download service is running."""
    return {"status": "ok"}


@mcp.tool
async def download_model(
    name: str,
    hub: str,
    download_path: str = "",
    type: Optional[str] = None,
    is_ovms: bool = False,
    config: Optional[Dict[str, Any]] = None,
    revision: Optional[str] = None,
) -> dict:
    """Submit a model download (and optional OpenVINO conversion) job.

    Args:
        name: Model identifier (e.g. 'meta-llama/Llama-3.2-1B', 'yolov8n').
        hub: Source hub — one of huggingface, ollama, ultralytics, geti,
             pipeline-zoo-models, hls, remote-url, omz.
        download_path: Destination path relative to MODELS_DIR (or absolute).
                       Defaults to MODELS_DIR root when empty.
        type: Model type hint (llm, vlm, embeddings, rerank, vision, etc.).
        is_ovms: Set True to convert the model to OpenVINO IR format for OVMS.
        config: Optional conversion/optimisation config dict
                (precision, device, cache_size, etc.).
        revision: Optional model revision / tag / branch.

    Returns:
        A dict with job_ids and processing status.
    """
    model_kwargs: Dict[str, Any] = {
        "name": name,
        "hub": hub,
        "is_ovms": is_ovms,
    }
    if type is not None:
        model_kwargs["type"] = type
    if revision is not None:
        model_kwargs["revision"] = revision
    if config is not None:
        model_kwargs["config"] = config

    model_request = ModelRequest(**model_kwargs)
    request = ModelDownloadRequest(models=[model_request])

    resolved_path = download_path or models_dir

    try:
        job_ids = await submit_models(
            request,
            resolved_path,
            plugin_registry=plugin_registry,
            model_manager=model_manager,
            models_dir=models_dir,
            background_tasks=_background_tasks,
        )
        return {
            "message": f"Started processing model '{name}'",
            "job_ids": job_ids,
            "status": "processing",
        }
    except ModelSubmissionError as exc:
        return {"error": str(exc), "status": "failed"}
    except Exception as exc:
        logger.error(f"Unexpected error in MCP download_model: {exc}")
        return {"error": str(exc), "status": "failed"}


@mcp.tool
def get_job_status(job_id: str) -> dict:
    """Get the current status of a specific job.

    Args:
        job_id: The UUID of the job to query.

    Returns:
        The full job record including status, model_name, hub, output_dir, etc.
    """
    job = model_manager.get_job_status(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}
    return job


@mcp.tool
def list_jobs() -> dict:
    """List all jobs (queued, running, completed, failed, cancelled)."""
    return {"jobs": _job_snapshots()}


@mcp.tool
def cancel_job(job_id: str) -> dict:
    """Cancel a running or queued job.

    Args:
        job_id: The UUID of the job to cancel.

    Returns:
        Confirmation message or error details.
    """
    job = model_manager.get_job_status(job_id)
    if job is None:
        return {"error": f"Job {job_id} not found"}

    if job["status"] in ("completed", "failed", "canceled"):
        return {
            "error": f"Job {job_id} is already in terminal state '{job['status']}'"
        }

    cancelled = model_manager.cancel_job(job_id)
    if not cancelled:
        return {"error": f"Job {job_id} could not be cancelled"}

    return {"message": f"Job {job_id} has been cancelled", "job_id": job_id, "status": "canceled"}


@mcp.tool
def get_model_jobs(model_name: str) -> dict:
    """Get all jobs related to a specific model name.

    Args:
        model_name: The model identifier to look up.

    Returns:
        A list of matching job records.
    """
    model_jobs = [
        job for job in _job_snapshots() if job.get("model_name") == model_name
    ]
    if not model_jobs:
        return {"error": f"No jobs found for model '{model_name}'"}
    return {"jobs": model_jobs}


@mcp.tool
def get_model_results() -> dict:
    """Get completed model downloads and conversions."""
    completed = []
    for job in _job_snapshots():
        if job.get("status") == "completed":
            operation_type = job.get("operation_type")
            result: Dict[str, Any] = {
                "job_id": job.get("id"),
                "model_name": job.get("model_name"),
                "hub": job.get("hub"),
                "operation_type": operation_type,
                "status": "success",
                "model_path": job.get("output_dir"),
                "completion_time": job.get("completion_time"),
            }
            if operation_type != "upload":
                result["is_ovms"] = operation_type == "convert"
            completed.append(result)
    return {"results": completed}


@mcp.tool
def list_plugins() -> dict:
    """List all available plugins, their capabilities, and config keys.

    Returns:
        Plugin information grouped by type (downloader, converter).
    """
    return _plugin_info()


@mcp.tool
async def list_hub_models(
    hub: str,
    limit: int = 50,
    offset: int = 0,
    filters: Optional[Dict[str, Any]] = None,
) -> dict:
    """Browse or search models available on a hub.

    Args:
        hub: Hub name (e.g. 'huggingface', 'ultralytics', 'geti',
             'pipeline-zoo-models').
        limit: Maximum number of models to return (1-200).
        offset: Number of models to skip for pagination.
        filters: Hub-specific filters (e.g. {"author": "meta-llama",
                 "search": "llama"} for HuggingFace).

    Returns:
        A paginated list of models with metadata.
    """
    if limit < 1 or limit > 200:
        return {"error": "limit must be between 1 and 200"}
    if offset < 0:
        return {"error": "offset must be >= 0"}

    hub_name = hub.lower()
    plugin = plugin_registry.get_plugin("downloader", hub_name)
    if plugin is None:
        plugin = plugin_registry.find_plugin_for_model("downloader", "", hub_name)
    if plugin is None:
        return {
            "error": f"Hub '{hub}' was not activated. "
            f"Active hubs: {', '.join(sorted(plugin_registry.activated_plugins))}."
        }

    if not getattr(plugin, "supports_listing", False):
        return {"error": f"Hub '{hub}' does not support listing models"}

    is_available, reason = plugin_registry.hub_is_available(hub_name)
    if not is_available:
        return {"error": reason}

    try:
        result = await asyncio.to_thread(
            plugin.list_models,
            filters=filters or {},
            limit=limit,
            offset=offset,
            hub=hub_name,
            resolved_config=plugin.resolve_config({}, hub=hub_name),
        )
    except ListingNotSupportedError:
        return {"error": f"Hub '{hub}' does not support listing models"}
    except ListingAuthError as exc:
        return {"error": f"Authentication error: {exc}"}
    except ValueError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        logger.error(f"Failed to list models for hub '{hub}': {exc}")
        return {"error": f"Failed to list models from hub '{hub}'"}

    raw_items = result.get("items", [])
    items = [ModelListItem(**item).model_dump(exclude_none=True) for item in raw_items[:limit]]
    count = len(items)
    total = result.get("total")
    has_more = (offset + count < total) if total is not None else (len(raw_items) > limit)

    return {
        "hub": hub_name,
        "items": items,
        "count": count,
        "total": total,
        "limit": limit,
        "offset": offset,
        "has_more": has_more,
        "next_offset": offset + limit if has_more else None,
    }


# ---- MCP resources ----------------------------------------------------------


@mcp.resource("models://jobs", mime_type="application/json")
def resource_jobs() -> str:
    """All model download/conversion jobs."""
    return json.dumps({"jobs": _job_snapshots()}, default=str)


@mcp.resource("models://jobs/{job_id}", mime_type="application/json")
def resource_job(job_id: str) -> str:
    """A specific job record by ID."""
    job = model_manager.get_job_status(job_id)
    if job is None:
        return json.dumps({"error": f"Job {job_id} not found"})
    return json.dumps(job, default=str)


@mcp.resource("models://results", mime_type="application/json")
def resource_results() -> str:
    """Completed model downloads and conversions."""
    completed = []
    for job in _job_snapshots():
        if job.get("status") == "completed":
            completed.append(
                {
                    "job_id": job.get("id"),
                    "model_name": job.get("model_name"),
                    "hub": job.get("hub"),
                    "model_path": job.get("output_dir"),
                    "completion_time": job.get("completion_time"),
                }
            )
    return json.dumps({"results": completed}, default=str)


@mcp.resource("models://plugins", mime_type="application/json")
def resource_plugins() -> str:
    """Available plugins and their capabilities."""
    return json.dumps(_plugin_info(), default=str)
