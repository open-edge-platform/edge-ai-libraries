# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Inference Router entry point.

Two ways to run the service:

1. ``uvicorn src.main:app --host 0.0.0.0 --port 8000`` (Docker / compose).
   Module-level ``app`` is built synchronously at import; provider init runs
   in the FastAPI startup hook.

2. ``python -m src.main`` with the legacy CLI flags (``--port``, ``--verbose``,
   ``--max-concurrency``, ``--save_logs_to``, …). The CLI translates flags into
   the ``GATEWAY_*`` / ``ROUTER_*`` env vars the app already understands and
   then hands off to ``uvicorn.run``.
"""
# pyright: reportMissingImports=false

import argparse
import asyncio
import logging
import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from src.config import load_config
from src.config.base import TelemetryBackendType, TelemetryConfig
from src.router import RouterOrchestrator
from src.observability import (
    FileBasedTelemetry,
    InMemoryTelemetry,
    Telemetry,
)
from src.router.logging_utils import log_to_gateway_file
from src.api.app import create_app
from src.api.logging_setup import (
    resolve_log_dir,
    resolve_verbose_flags,
    setup_logging,
)


# Bootstrap logger; ``setup_logging`` re-applies the level once config is loaded.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("gateway")


# ---------------------------------------------------------------------------
# Telemetry construction
# ---------------------------------------------------------------------------


def _build_telemetry(
    cfg: TelemetryConfig,
    fallback_dir: Path,
    log_dir: Path | None = None,
) -> Telemetry:
    """Construct a telemetry backend matching the legacy gateway's policy.

    - ``enabled=True`` + ``backend=file`` → :class:`FileBasedTelemetry`. The
      target path is ``cfg.file_path`` if set; otherwise it co-locates with
      ``log_dir`` (when present) or ``fallback_dir`` (typically the
      ``config.yaml`` directory).
    - Otherwise → :class:`InMemoryTelemetry`. Events are still queryable via
      ``/v1/metrics`` for the lifetime of the process.
    """
    if cfg.enabled and cfg.backend == TelemetryBackendType.FILE:
        if cfg.file_path:
            path = Path(cfg.file_path)
        else:
            base = log_dir if log_dir is not None else fallback_dir
            path = base / "telemetry.jsonl"
        logger.info(f"Telemetry backend: file ({path})")
        return FileBasedTelemetry(path)
    if not cfg.enabled:
        logger.info("Telemetry backend: memory (telemetry.enabled=false)")
    else:
        logger.info("Telemetry backend: memory")
    return InMemoryTelemetry()


# ---------------------------------------------------------------------------
# App factory used by both the ``uvicorn src.main:app`` entry path and
# ``python -m src.main``.
# ---------------------------------------------------------------------------


def build_app() -> FastAPI:
    """Build the FastAPI app, deferring provider init to the startup hook."""
    log_dir = resolve_log_dir()
    verbose, verbose_full = resolve_verbose_flags()

    config_path = Path(os.environ.get("GATEWAY_CONFIG", "config.yaml"))
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {config_path}")

    logger.info(f"Loading config from {config_path}")
    config = load_config(str(config_path))
    setup_logging(config)

    telemetry = _build_telemetry(
        config.telemetry, fallback_dir=config_path.parent, log_dir=log_dir
    )

    # Construct the orchestrator synchronously. ``RouterOrchestrator.__init__``
    # only registers config/decision engine/plugin manager; provider creation
    # happens in ``initialize()``, which we call from the startup hook below.
    router = RouterOrchestrator(config, telemetry=telemetry)

    max_concurrency = int(os.environ.get("GATEWAY_MAX_CONCURRENCY", "3"))
    app = create_app(
        router,
        config,
        telemetry,
        max_concurrency=max_concurrency,
        verbose=verbose,
        verbose_full=verbose_full,
        log_dir=log_dir,
    )

    @app.on_event("startup")
    async def _initialize_providers() -> None:
        try:
            await router.initialize()
        except Exception as e:
            msg = f"❌ Failed to initialize router: {e}"
            print(msg)
            log_to_gateway_file(msg, log_dir)
            logger.error(msg)
            raise

        msg = f"✅ Router initialized with config: {config_path}"
        print(msg)
        log_to_gateway_file(msg, log_dir)

        provider_names = list(router.provider_map)
        msg = (
            f"   - Providers: {len(provider_names)} "
            f"({', '.join(provider_names) or 'none'})"
        )
        print(msg)
        log_to_gateway_file(msg, log_dir)

        msg = (
            f"   - Max concurrency: "
            f"{'unlimited' if max_concurrency <= 0 else max_concurrency}"
        )
        print(msg)
        log_to_gateway_file(msg, log_dir)

        msg = f"   - Verbose logging: {verbose}"
        print(msg)
        log_to_gateway_file(msg, log_dir)

        msg = f"   - Verbose full logging: {verbose_full}"
        print(msg)
        log_to_gateway_file(msg, log_dir)

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        router.shutdown()

    return app


# Module-level ``app`` for ``uvicorn src.main:app``. Building this at import
# time mirrors how ``src.router.gateway:app`` was wired previously, so the
# Docker/compose ``CMD`` strings need only the module string changed.
app: FastAPI = build_app()


# ---------------------------------------------------------------------------
# CLI (mirrors the legacy gateway's argparse interface)
# ---------------------------------------------------------------------------


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inference Router API Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind")
    parser.add_argument("--port", type=int, default=8080, help="Port to bind")
    parser.add_argument("--config", default="config.yaml", help="Path to config file")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print raw backend responses to the terminal",
    )
    parser.add_argument(
        "--verbose_full",
        action="store_true",
        help="Print raw requests and raw backend responses to the terminal",
    )
    parser.add_argument(
        "--save_logs_to",
        default=None,
        help="Directory to save gateway logs (requests and responses)",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=3,
        help="Max concurrent requests (0 = unlimited)",
    )
    return parser.parse_args()


def cli_main() -> None:
    """CLI entry point: parse flags, set env vars, launch uvicorn."""
    args = _parse_args()

    if args.verbose_full:
        args.verbose = True
    if args.verbose:
        os.environ["GATEWAY_VERBOSE"] = "1"
    if args.verbose_full:
        os.environ["GATEWAY_VERBOSE_FULL"] = "1"
    if args.save_logs_to:
        os.environ["GATEWAY_LOG_DIR"] = args.save_logs_to
    os.environ["GATEWAY_MAX_CONCURRENCY"] = str(args.max_concurrency)
    os.environ["GATEWAY_CONFIG"] = args.config

    banner = [
        "=" * 80,
        "🚀 Starting Inference Router API Server",
        "=" * 80,
        f"   Host: {args.host}",
        f"   Port: {args.port}",
        f"   Config: {args.config}",
        f"   Verbose: {args.verbose}",
        f"   Verbose full: {args.verbose_full}",
        f"   Max concurrency: "
        f"{'unlimited' if args.max_concurrency <= 0 else args.max_concurrency}",
        "=" * 80,
    ]
    for line in banner:
        print(line)

    # ``--reload`` requires the import string form so uvicorn can re-import.
    target = "src.main:app" if args.reload else app
    uvicorn.run(
        target,
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    cli_main()
