# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""Synchronous task REST API; file exchange uses the shared upload directory."""
from __future__ import annotations

import json
import logging
import os
import secrets
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import httpx
from fastapi import Depends, FastAPI, HTTPException, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .agent import ExtractionResponseError
from .config import Config
from .llmclient import ContextOverflowError, LLMClient
from .pipeline import extract_bundle
from .planning import PlanningResponseError
from .readers import DEFAULT_MAX_TASK_BYTES, TaskTooLarge, materialize_task
from .schemas import ExtractionResult, ExtractionTask
from .shared import TASK_DIRECTORY, shared_path, upload_directory

logger = logging.getLogger(__name__)


def create_app(
    config: Config | None = None, *, api_key: str | None = None,
    max_task_bytes: int | None = None, upload_dir: Path | None = None,
) -> FastAPI:
    cfg = config or Config.from_env()
    key = os.getenv("OKF_EXTRACTOR_API_KEY", "") if api_key is None else api_key
    max_bytes = max_task_bytes if max_task_bytes is not None else int(
        os.getenv("OKF_EXTRACTOR_MAX_TASK_BYTES", str(DEFAULT_MAX_TASK_BYTES))
    )
    if max_bytes <= 0:
        raise ValueError("OKF_EXTRACTOR_MAX_TASK_BYTES must be positive")
    shared_dir = (upload_dir if upload_dir is not None else upload_directory()).resolve()
    app = FastAPI(title="OKF Extractor", version="1.0.0")
    bearer = HTTPBearer(auto_error=False)

    def authorize(
        credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    ) -> None:
        if key and (credentials is None or not secrets.compare_digest(
            credentials.credentials.encode("utf-8"), key.encode("utf-8"),
        )):
            raise HTTPException(401, "Invalid extractor credentials", headers={"WWW-Authenticate": "Bearer"})

    def process(task: ExtractionTask) -> ExtractionResult:
        client = None
        lock = None
        try:
            task_dir = shared_path(shared_dir, f"{TASK_DIRECTORY}/{task.task_id}")
            task_dir.mkdir(parents=True, exist_ok=True)
            output = shared_path(shared_dir, f"{TASK_DIRECTORY}/{task.task_id}/bundle")
            # A duplicate task must not overwrite a finished result or race another writer.
            lock_path = task_dir / ".running"
            try:
                lock = lock_path.open("x")
            except FileExistsError:
                raise HTTPException(409, "This task is already running") from None
            if output.exists():
                raise HTTPException(409, "This task already has a completed bundle")
            with TemporaryDirectory(prefix=".work-", dir=task_dir) as temporary:
                root = Path(temporary)
                tree = materialize_task(
                    task, root / "sources", float(cfg.batch["chars_per_token"]), max_bytes,
                    shared_dir=shared_dir,
                )
                candidate = root / "bundle"
                client = LLMClient(cfg.llm)
                began = time.monotonic()
                concepts = extract_bundle(cfg, client, tree, candidate, options=task.options,
                                          label=f"task {task.task_id[:8]}")
                print(f"[task {task.task_id[:8]}] done: {len(concepts)} concept(s) in "
                      f"{time.monotonic() - began:.0f}s", flush=True)
                # Only non-secret metadata lives with the bundle, not raw documents.
                (candidate / "task.json").write_text(json.dumps({
                    "task_id": task.task_id, "concept_count": len(concepts),
                    "sources": [{"path": item.path, "asset_id": item.asset_id} for item in task.items],
                }, ensure_ascii=False, indent=2), encoding="utf-8")
                # Publish atomically once the bundle and manifest are complete.
                candidate.rename(output)
            return ExtractionResult(
                task_id=task.task_id, bundle_path=output.relative_to(shared_dir).as_posix(),
                concept_count=len(concepts),
            )
        except HTTPException:
            raise
        except TaskTooLarge as error:
            raise HTTPException(413, str(error)) from error
        except PlanningResponseError as error:
            logger.warning("OKF task %s failed during instruction planning: %s", task.task_id, error)
            raise HTTPException(
                502, str(error), headers={"X-OKF-Task-ID": task.task_id},
            ) from error
        except ExtractionResponseError as error:
            logger.warning("OKF task %s failed during concept extraction: %s", task.task_id, error)
            raise HTTPException(
                502, str(error), headers={"X-OKF-Task-ID": task.task_id},
            ) from error
        except ValueError as error:
            logger.warning("OKF task %s rejected: %s", task.task_id, error)
            raise HTTPException(
                422, str(error), headers={"X-OKF-Task-ID": task.task_id},
            ) from error
        except (httpx.HTTPError, ContextOverflowError) as error:
            logger.exception("Model request failed for OKF task %s", task.task_id)
            raise HTTPException(502, "The extraction model request failed") from error
        except Exception:
            logger.exception("OKF task %s failed", task.task_id)
            raise HTTPException(500, "OKF extraction failed") from None
        finally:
            if client is not None:
                client.close()
            if lock is not None:
                lock.close()
                lock_path.unlink(missing_ok=True)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/tasks", response_model=ExtractionResult, dependencies=[Depends(authorize)])
    def submit(task: ExtractionTask, response: Response) -> ExtractionResult:
        """Read shared files, plan instructions, extract and return a shared bundle path."""
        response.headers["X-OKF-Task-ID"] = task.task_id
        return process(task)

    return app


app = create_app()