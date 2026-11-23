# Copyright (C) 2025 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Serve only the built Vue console, including history-mode routes."""

import logging
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.staticfiles import StaticFiles


def console_directory() -> Path:
    packaged = Path(__file__).parent / "console_ui_dist"
    source = Path(__file__).resolve().parents[1] / "ui" / "dist"
    return source if source.is_dir() else packaged


class ConsoleStaticFiles(StaticFiles):
    async def check_config(self) -> None:
        if Path(self.directory).is_dir():
            await super().check_config()
        else:
            logging.getLogger(__name__).warning(
                "Console build is missing. Run npm ci && npm run build in data-intelligence-engine/ui."
            )

    async def get_response(self, path, scope):
        if not (Path(self.directory) / "index.html").is_file():
            return JSONResponse(
                status_code=503,
                content={"detail": "Console is not built. Run npm ci && npm run build in data-intelligence-engine/ui."},
            )
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            # Missing assets and traversal attempts must not return the SPA.
            if (
                exc.status_code != 404
                or Path(path).suffix
                or ".." in Path(path).parts
                or path.replace("\\", "/").startswith("assets/")
            ):
                raise
            return await super().get_response("index.html", scope)