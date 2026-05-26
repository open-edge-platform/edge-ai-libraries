"""Tests for the FastAPI application entry point (main.py)."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

import pytest
from httpx import ASGITransport, AsyncClient

from src.core.config import load_config
from src.main import lifespan


class TestAppLifespan:
    async def test_lifespan_startup_shutdown(self, config_file: str):
        """Exercises the lifespan context manager directly."""
        import src.core.settings as settings_module
        from src.core.settings import Settings

        original = settings_module.settings
        new_settings = Settings()
        new_settings.CONFIG_PATH = config_file
        settings_module.settings = new_settings

        from fastapi import FastAPI

        app = FastAPI(lifespan=lifespan)

        # Manually invoke lifespan
        async with lifespan(app):
            assert hasattr(app.state, "worker")
            assert hasattr(app.state, "config")
            assert len(app.state.config.subscriptions) > 0
            assert app.state.worker._running is True

        # After lifespan exit, worker should be stopped
        assert app.state.worker._running is False

        settings_module.settings = original

    async def test_app_module_creates_fastapi(self):
        """Verifies the module-level app object and router are wired."""
        import src.main as main_module

        assert hasattr(main_module, "app")
        assert main_module.app.title == "Alert Service"
        routes = [r.path for r in main_module.app.routes]
        assert "/api/v1/health" in routes
