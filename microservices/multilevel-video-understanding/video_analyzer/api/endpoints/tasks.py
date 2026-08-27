# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""CRUD endpoints for dynamic video summary tasks (runtime prompt registration)."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Response, status
from fastapi.responses import JSONResponse

from video_analyzer.prompts.prompt_autogen import generate_prompt_set
from video_analyzer.prompts.prompt_registry import (
    RegistryError,
    get_registry,
    reconstitute_content,
    resolve_content_to_sections,
)
from video_analyzer.core.summarizer import ModelConfig
from video_analyzer.model_serving.openai_llm import LLM
from video_analyzer.schemas.task_registration import (
    PatchTaskRequest,
    PromptContent,
    RegisterTaskRequest,
    TaskDetailResponse,
    TaskInfo,
    TaskListResponse,
)
from video_analyzer.utils.logger import logger

router = APIRouter(prefix="/tasks", tags=["Prompt Tasks API"])


# =========================================================================
# helpers
# =========================================================================
def _http_from_registry_error(exc: RegistryError) -> HTTPException:
    """Map a RegistryError into a structured HTTPException."""
    detail = {"error": exc.code, **exc.detail}
    return HTTPException(status_code=exc.http_status, detail=detail)


def _build_detail_response(name: str, source: str, description: Optional[str],
                           sections: dict) -> TaskDetailResponse:
    return TaskDetailResponse(
        name=name,
        source=source,
        description=description,
        content=reconstitute_content(sections),
    )


async def _sections_from_mode(mode: str, description: Optional[str],
                              content: Optional[PromptContent]) -> tuple[dict, Optional[str]]:
    """Produce (sections, desc) from a register/patch payload.

    For `autogen`: call the service LLM. For `full`: parse the content string.
    """
    if mode == "autogen":
        cfg = ModelConfig()
        llm = LLM(
            model_name=cfg.LLM_MODEL_NAME,
            api_key=cfg.LLM_API_KEY,
            base_url=cfg.LLM_BASE_URL,
            remove_thinking=True,
        )
        sections = await generate_prompt_set(description or "", llm)
        return sections, description
    if mode == "full":
        if content is None:
            raise RegistryError(400, "missing_content", detail="mode=full requires content")
        text = content.text
        url = str(content.url) if content.url else None
        sections, _raw = resolve_content_to_sections(text, url)
        return sections, description
    raise RegistryError(400, "invalid_mode", detail=f"unknown mode {mode!r}")


def _builtin_task_detail(name: str) -> TaskDetailResponse:
    """Render a built-in prompt instance so GET /v1/tasks/{name} works for them too."""
    from video_analyzer.prompts.prompt_builder import get_prompt_instance
    inst = get_prompt_instance(name)

    # Each built-in stores its templates as module-level strings named
    # GLOBAL_PROMPT / MACRO_CHUNK_PROMPT / LOCAL_PROMPT / T_MINUS_1_PROMPT.
    import inspect
    module = inspect.getmodule(inst)
    sections = {
        "global":  getattr(module, "GLOBAL_PROMPT", "").strip() + "\n",
        "macro":   getattr(module, "MACRO_CHUNK_PROMPT", "").strip() + "\n",
        "local":   getattr(module, "LOCAL_PROMPT", "").strip() + "\n",
        "t_minus": getattr(module, "T_MINUS_1_PROMPT", "").strip() + "\n",
    }
    return _build_detail_response(name, "builtin", None, sections)


# =========================================================================
# GET /v1/tasks  — list
# =========================================================================
@router.get(
    "",
    response_model=TaskListResponse,
    summary="List all video summary tasks (built-in + runtime-registered).",
)
def list_tasks() -> TaskListResponse:
    rows = get_registry().list_all()
    return TaskListResponse(tasks=[TaskInfo(**r) for r in rows])


# =========================================================================
# GET /v1/tasks/{name}  — detail
# =========================================================================
@router.get(
    "/{name}",
    response_model=TaskDetailResponse,
    summary="Get the four prompt sections for a specific video summary task.",
)
def get_task(name: str) -> TaskDetailResponse:
    registry = get_registry()
    if registry.is_builtin(name):
        try:
            return _builtin_task_detail(name)
        except Exception as e:
            logger.warning("Failed to introspect built-in task %s: %s", name, e)
            raise HTTPException(
                status_code=500,
                detail={"error": "introspection_failed", "detail": str(e)},
            )
    rec = registry.get_record(name)
    if rec is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "task_name": name},
        )
    return _build_detail_response(rec.name, "dynamic", rec.description, rec.sections)


# =========================================================================
# POST /v1/tasks  — create
# =========================================================================
@router.post(
    "",
    response_model=TaskDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new dynamic video summary task (autogen or full mode).",
)
async def register_task(request: RegisterTaskRequest) -> TaskDetailResponse:
    try:
        sections, desc = await _sections_from_mode(request.mode, request.description, request.content)
        rec = get_registry().add(request.task_name, sections, desc)
    except RegistryError as e:
        raise _http_from_registry_error(e)

    logger.info("Registered dynamic task '%s' (mode=%s)", request.task_name, request.mode)
    return _build_detail_response(rec.name, "dynamic", rec.description, rec.sections)


# =========================================================================
# PATCH /v1/tasks/{name}  — update / rename / regenerate
# =========================================================================
@router.patch(
    "/{name}",
    response_model=TaskDetailResponse,
    summary="Update a dynamic video summary task — rename, change description, or regenerate prompts.",
)
async def update_task(name: str, request: PatchTaskRequest) -> TaskDetailResponse:
    registry = get_registry()

    if registry.is_builtin(name):
        raise HTTPException(
            status_code=403,
            detail={"error": "builtin_immutable", "task_name": name,
                    "detail": "built-in tasks cannot be modified via API"},
        )

    if registry.get_record(name) is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "not_found", "task_name": name},
        )

    try:
        current_name = name
        # 1) Regenerate prompts if mode+payload provided.
        if request.mode is not None:
            sections, _ = await _sections_from_mode(
                request.mode, request.description, request.content,
            )
            registry.replace(current_name, sections, request.description)
        elif request.description is not None:
            registry.update_description(current_name, request.description)

        # 2) Rename last so the replace/update above uses the original key.
        if request.new_task_name is not None and request.new_task_name != current_name:
            rec = registry.rename(current_name, request.new_task_name)
            current_name = rec.name
        else:
            rec = registry.get_record(current_name)
    except RegistryError as e:
        raise _http_from_registry_error(e)

    return _build_detail_response(rec.name, "dynamic", rec.description, rec.sections)


# =========================================================================
# DELETE /v1/tasks/{name}
# =========================================================================
@router.delete(
    "/{name}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a dynamic video summary task. Built-ins cannot be deleted.",
)
def delete_task(name: str) -> Response:
    try:
        get_registry().delete(name)
    except RegistryError as e:
        raise _http_from_registry_error(e)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
