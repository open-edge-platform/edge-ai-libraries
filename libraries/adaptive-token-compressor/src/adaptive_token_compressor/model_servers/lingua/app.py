# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0

"""LLMLingua-2 FastAPI server. Dual-mode entry:

  - Module:     python -m adaptive_token_compressor.model_servers.lingua
    - Standalone: python lingua_server.py --backend pytorch --device xpu --port 8001  (Docker)

Heavy deps (torch / llmlingua / fastapi / IPEX) are deferred into
``build_app`` so module import from a client doesn't pull them in.
"""
from __future__ import annotations

import argparse
import logging
import os
import time
from pathlib import Path
from typing import Any, Literal

# HF env must be set BEFORE huggingface_hub is imported transitively (it
# reads HF_ENDPOINT / HF_HUB_OFFLINE on first import). Defaults match
# router production: hf-mirror endpoint, online so first-run can download.
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_OFFLINE", "0")

# pydantic stays at module scope — FastAPI treats locally-defined BaseModel
# subclasses as query parameters, not request body.
from pydantic import BaseModel, ConfigDict, Field, field_validator  # noqa: E402  (after env setup is intentional)


class CompressRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1)
    mode: Literal["llmlingua2"] | None = None
    rate: float = Field(default=0.33, gt=0.0, le=1.0)
    force_tokens: list[str] | None = Field(default=None, max_length=100)
    force_reserve_digit: bool = Field(default=False, strict=True)
    digit_neighbor_radius: int = Field(default=0, ge=0, le=100)

    @field_validator("digit_neighbor_radius", mode="before")
    @classmethod
    def _reject_bool_radius(cls, v: Any) -> Any:
        # bool is a subclass of int, so non-strict validation would silently
        # accept `true`/`false` as 1/0. Reject it explicitly while still allowing
        # float-valued integers like 99.0.
        if isinstance(v, bool):
            raise ValueError("digit_neighbor_radius must be an integer, not a boolean")
        return v


logger = logging.getLogger("adaptive_token_compressor.model_servers.lingua")

# Ensure app logger emits INFO in container too. Uvicorn logs alone are not
# enough to confirm backend/device mapping.
_LOG_LEVEL = os.environ.get("LINGUA_LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _LOG_LEVEL, logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger.setLevel(getattr(logging, _LOG_LEVEL, logging.INFO))

# Optional, deployment-tunable hard ceiling on request `text` length (chars).
# Unset or <= 0 means "no hard limit" (default) so unknown-large but legitimate
# contexts are not rejected out of the box. Set LINGUA_MAX_TEXT_CHARS in
# production once the real upper bound is known to bound worst-case resource use
# (compression runs a transformer model — oversized input is a cheap DoS vector).
def _parse_max_text_chars() -> int:
    raw = os.environ.get("LINGUA_MAX_TEXT_CHARS", "0").strip()
    try:
        val = int(raw)
    except ValueError:
        logger.warning("Invalid LINGUA_MAX_TEXT_CHARS=%r; treating as unset (no limit)", raw)
        return 0
    return val if val > 0 else 0


MAX_TEXT_CHARS = _parse_max_text_chars()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LLMLingua-2 FastAPI server")

    def _env_str(name: str, default: str) -> str:
        return os.environ.get(name, default)

    parser.add_argument(
        "--backend",
        type=str,
        default=_env_str("LINGUA_BACKEND", "pytorch"),
        choices=["pytorch", "ov"],
        help="Execution backend: pytorch (with optional IPEX) or OpenVINO",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=_env_str("LINGUA_DEVICE", "xpu"),
        choices=["xpu", "cpu", "cuda"],
    )
    parser.add_argument(
        "--xpu_index",
        type=int,
        default=int(_env_str("LINGUA_XPU_INDEX", "0")),
        help="XPU device index used when --device=xpu",
    )
    parser.add_argument("--port", type=int, default=int(_env_str("LINGUA_PORT", "8001")))
    parser.add_argument("--host", type=str, default=_env_str("LINGUA_HOST", "localhost"))
    parser.add_argument(
        "--model_name_id",
        type=str,
        default=_env_str("LINGUA_MODEL_NAME_ID", _env_str("LINGUA_MODEL", "")),
        help=(
            "HF model id (optional). "
            "If omitted, the LLMLingua-2 default model is used."
        ),
    )
    parser.add_argument(
        "--mode",
        type=str,
        default=_env_str("LINGUA_MODE", "llmlingua2"),
        choices=["llmlingua2"],
        help="Compression mode. Only llmlingua2 (LLMLingua-2 path) is supported.",
    )
    return parser.parse_args()


def build_app(args: argparse.Namespace) -> Any:
    import torch  # noqa: F401
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
    from llmlingua import PromptCompressor

    if args.backend == "pytorch" and args.device == "xpu":
        # Fail fast: pytorch+xpu must not silently fall back to CPU.
        import intel_extension_for_pytorch  # noqa: F401
    if args.backend == "pytorch" and args.device == "cuda":
        if not torch.cuda.is_available():
            raise RuntimeError(
                "--device cuda requested, but this PyTorch build has no CUDA support. "
                "Use --device cpu or --device xpu."
            )

    logger.info("Backend=%s  Requested device=%s", args.backend, args.device)

    startup_mode = (args.mode or "llmlingua2").strip().lower()
    supported_modes = {"llmlingua2"}
    if startup_mode not in supported_modes:
        raise ValueError("--mode must be: llmlingua2")

    requested_model_name = (args.model_name_id or "").strip()
    logger.info("Startup default compression mode: %s", startup_mode)
    logger.info(
        "Request-level mode override enabled; supported modes: %s",
        ", ".join(sorted(supported_modes)),
    )
    logger.info("HF_HUB_OFFLINE=%s  HF_ENDPOINT=%s",
                os.environ.get("HF_HUB_OFFLINE"), os.environ.get("HF_ENDPOINT"))

    mode_state: dict[str, dict[str, Any]] = {}

    def _ensure_mode_state(selected_mode: str) -> dict[str, Any]:
        if selected_mode in mode_state:
            return mode_state[selected_mode]

        default_model_name = (
            "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        )
        effective_model_name = requested_model_name or default_model_name

        logger.info(
            "Initializing mode=%s with model=%s",
            selected_mode,
            effective_model_name if effective_model_name else "<llmlingua-default>",
        )

        llm_lingua = PromptCompressor(
            model_name=effective_model_name,
            use_llmlingua2=True,
            device_map="cpu",
        )

        runtime_device = str(llm_lingua.device)
        ov_exec_devices = "n/a"

        if args.backend == "pytorch":
            if args.device == "xpu":
                xpu_index = args.xpu_index
                try:
                    if hasattr(torch, "xpu") and torch.xpu.is_available():
                        xpu_count = torch.xpu.device_count()
                        logger.info("Detected XPU devices: %d", xpu_count)
                        for idx in range(xpu_count):
                            logger.info("XPU[%d] name: %s", idx, torch.xpu.get_device_name(idx))
                        if xpu_index < 0 or xpu_index >= xpu_count:
                            raise RuntimeError(
                                f"Invalid --xpu_index={xpu_index}; available range is 0..{xpu_count - 1}."
                            )
                        logger.info(
                            "Selecting xpu:%d (%s). Note: index alone cannot guarantee iGPU vs dGPU.",
                            xpu_index,
                            torch.xpu.get_device_name(xpu_index),
                        )
                    else:
                        logger.warning("--device xpu requested, but torch.xpu is not available")
                except Exception as exc:
                    logger.warning("Failed to enumerate XPU devices: %s", type(exc).__name__)

                device = torch.device(f"xpu:{xpu_index}")
                llm_lingua.model = llm_lingua.model.to(device)
                llm_lingua.device = device
                runtime_device = str(device)
                logger.info("PyTorch runtime mapped to device: %s", runtime_device)
            elif args.device == "cuda":
                device = torch.device("cuda:0")
                llm_lingua.model = llm_lingua.model.to(device)
                llm_lingua.device = device
                runtime_device = str(device)
                logger.info("PyTorch runtime mapped to device: %s", runtime_device)
            else:
                logger.info("PyTorch runtime mapped to device: cpu")

            try:
                param_device = next(llm_lingua.model.parameters()).device
                logger.info("Model parameter device: %s", param_device)
            except Exception as exc:
                logger.warning("Failed to read model parameter device: %s", type(exc).__name__)
        else:
            try:
                import openvino as ov
                from optimum.intel import OVModelForTokenClassification
            except ImportError as exc:
                raise RuntimeError(
                    "--backend ov requires openvino + optimum-intel. "
                    "Install with: pip install openvino optimum[openvino]"
                ) from exc

            core = ov.Core()
            available_devices = list(core.available_devices)

            if args.device == "xpu":
                preferred_ov_gpu = f"GPU.{args.xpu_index}"
                if preferred_ov_gpu in available_devices:
                    ov_device = preferred_ov_gpu
                elif args.xpu_index == 0 and "GPU" in available_devices:
                    # Some OV runtimes expose a generic GPU device without index.
                    ov_device = "GPU"
                else:
                    gpu_like = [d for d in available_devices if d.startswith("GPU")]
                    raise RuntimeError(
                        "--backend ov with --device xpu could not map "
                        f"--xpu_index={args.xpu_index}. Requested {preferred_ov_gpu!r}, "
                        f"available OV GPU devices: {gpu_like or 'none'}"
                    )
            elif args.device == "cpu":
                ov_device = "CPU"
            else:
                raise RuntimeError(
                    "--backend ov does not support --device cuda. "
                    "Use --device xpu (maps to OV GPU) or --device cpu."
                )

            logger.info("OpenVINO requested device=%s mapped device=%s", args.device, ov_device)
            logger.info("OpenVINO available devices: %s", available_devices)
            for dev_name in available_devices:
                try:
                    full_name = core.get_property(dev_name, "FULL_DEVICE_NAME")
                except Exception:
                    full_name = "unknown"
                logger.info("OV[%s] name: %s", dev_name, full_name)

            # Record mapped OV device full name up front for deterministic logging.
            try:
                ov_mapped_full_name = core.get_property(ov_device, "FULL_DEVICE_NAME")
            except Exception:
                ov_mapped_full_name = "unknown"
            logger.info("OV mapped FULL_DEVICE_NAME: %s", ov_mapped_full_name)

            # Persist OpenVINO IR under mounted cache so restarts can reuse it.
            ov_cache_root = Path(
                os.environ.get("LINGUA_OV_CACHE_DIR", "/root/.cache/huggingface/ov_ir")
            )
            if not effective_model_name:
                raise RuntimeError(
                    "--backend ov requires --model_name_id to be explicitly set."
                )

            model_cache_key = effective_model_name.replace("/", "__")
            ov_model_dir = ov_cache_root / model_cache_key
            ov_xml = ov_model_dir / "openvino_model.xml"
            ov_bin = ov_model_dir / "openvino_model.bin"

            if ov_xml.exists() and ov_bin.exists():
                logger.info("OpenVINO IR cache hit: %s", ov_model_dir)
                llm_lingua.model = OVModelForTokenClassification.from_pretrained(
                    str(ov_model_dir),
                    export=False,
                    device=ov_device,
                )
            else:
                logger.info("OpenVINO IR cache miss, exporting model for: %s", effective_model_name)
                llm_lingua.model = OVModelForTokenClassification.from_pretrained(
                    effective_model_name,
                    export=True,
                    device=ov_device,
                )
                try:
                    ov_model_dir.mkdir(parents=True, exist_ok=True)
                    llm_lingua.model.save_pretrained(str(ov_model_dir))
                    logger.info("OpenVINO IR persisted to: %s", ov_model_dir)
                except Exception as exc:
                    logger.warning("Failed to persist OpenVINO IR cache: %s", type(exc).__name__)

            ov_exec_devices = f"{ov_device} ({ov_mapped_full_name})"
            try:
                req = getattr(llm_lingua.model, "request", None)
                compiled_model = getattr(req, "compiled_model", None)
                if compiled_model is not None:
                    ov_exec_devices = compiled_model.get_property("EXECUTION_DEVICES")
            except Exception:
                pass

            # LLMLingua moves tokenizer tensors via torch.Tensor.to(self.device).
            # Keep tensor device on CPU; OpenVINO runtime target is tracked separately.
            llm_lingua.device = torch.device("cpu")
            runtime_device = f"ov:{ov_device}"
            logger.info("OpenVINO execution devices (startup probe): %s", ov_exec_devices)

        logger.info("Model runtime device: %s", runtime_device)
        logger.info("LLMLingua tensor device: %s", llm_lingua.device)

        state = {
            "compressor": llm_lingua,
            "model_name": effective_model_name,
            "runtime_device": runtime_device,
            "ov_exec_devices": ov_exec_devices,
            "ov_exec_reprobe_done": False,
        }
        mode_state[selected_mode] = state
        return state

    # Ensure startup mode is ready at boot; other mode(s) are loaded lazily on first request.
    _ensure_mode_state(startup_mode)

    if not _is_patched():
        logger.warning(
            "LLMLingua-2 source patch NOT applied — digit_neighbor_radius "
            "is silently ignored. Run "
            "`python -m adaptive_token_compressor.model_servers.lingua.apply_patch`."
        )

    app = FastAPI(title="Lingua Server")

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception):
        logger.error(
            "Unhandled request error for %s: %s",
            request.url.path,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "internal server error"},
        )

    @app.exception_handler(RequestValidationError)
    async def _log_invalid_request(request: Request, exc: RequestValidationError):
        # Requirement: log requests with invalid parameters (a burst signals the
        # interface is under attack). Log only field locations + error types, not
        # the raw offending values, to avoid injecting attacker-controlled data
        # into the logs. Response body stays the FastAPI-standard generic 422.
        summary = "; ".join(
            f"{'.'.join(str(p) for p in e.get('loc', []))}:{e.get('type', '?')}"
            for e in exc.errors()
        )
        logger.warning(
            "invalid /compress request rejected (422) from %s: %s",
            request.client.host if request.client else "unknown",
            summary,
        )
        # Keep the body generic (no echo of attacker-controlled values) BUT
        # shaped to the published HTTPValidationError schema (detail: array of
        # ValidationError), so the response still conforms to the OpenAPI spec.
        return JSONResponse(
            status_code=422,
            content={"detail": [{"loc": [], "msg": "invalid request parameters", "type": "validation_error"}]},
        )

    _ERROR_RESPONSES = {
        400: {"description": "Malformed request body or unsupported mode"},
        413: {"description": "Request text exceeds LINGUA_MAX_TEXT_CHARS"},
        422: {"description": "Request failed schema validation"},
    }

    @app.post("/compress", responses=_ERROR_RESPONSES)
    async def compress_text(request: CompressRequest) -> dict:
        start = time.perf_counter()
        # Deployment-tunable hard ceiling on text size (DoS guard). 0 = no limit.
        if MAX_TEXT_CHARS and len(request.text) > MAX_TEXT_CHARS:
            logger.warning(
                "oversized /compress request rejected (413): text=%d chars exceeds LINGUA_MAX_TEXT_CHARS=%d",
                len(request.text), MAX_TEXT_CHARS,
            )
            raise HTTPException(status_code=413, detail="text too large")
        request_mode = ((request.mode or startup_mode).strip().lower() if request.mode else startup_mode)
        if request_mode not in supported_modes:
            logger.warning("invalid /compress mode rejected (400): %r", request.mode)
            raise HTTPException(
                status_code=400,
                detail=(
                    "invalid mode in request; expected one of: "
                    + ", ".join(sorted(supported_modes))
                ),
            )
        state = _ensure_mode_state(request_mode)
        llm_lingua = state["compressor"]

        force_tokens = (
            request.force_tokens if request.force_tokens else ["\n", "?"]
        )

        def _plain_compress() -> dict:
            return llm_lingua.compress_prompt(
                request.text,
                rate=request.rate,
                force_tokens=force_tokens,
                force_reserve_digit=request.force_reserve_digit,
            )

        # Patched LLMLingua reads `_digit_neighbor_radius` instance attr;
        # vanilla version ignores it.
        llm_lingua._digit_neighbor_radius = request.digit_neighbor_radius
        # Defense in depth: LLMLingua can raise bare AssertionError / ValueError
        # on adversarial-but-schema-valid inputs. Convert any such failure into a
        # clean 400 with a generic message instead of leaking a 500 + stack trace.
        try:
            result = _plain_compress()
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning("compression failed (400) for a valid-shaped request: %s", type(exc).__name__)
            raise HTTPException(status_code=400, detail="compression failed for the given parameters") from exc

        # On OV path, retry execution-device probe after first real inference.
        if args.backend == "ov" and not state["ov_exec_reprobe_done"]:
            try:
                req = getattr(llm_lingua.model, "request", None)
                compiled_model = getattr(req, "compiled_model", None)
                if compiled_model is not None:
                    probed = compiled_model.get_property("EXECUTION_DEVICES")
                    if probed:
                        state["ov_exec_devices"] = probed
            except Exception:
                # Keep startup fallback value if probe still unavailable.
                pass
            state["ov_exec_reprobe_done"] = True
            logger.info("OpenVINO execution devices (post-first-compress): %s", state["ov_exec_devices"])

        elapsed = time.perf_counter() - start
        result["compression_time_ms"] = round(elapsed * 1000, 2)
        result["compression_time_s"] = round(elapsed, 3)
        return result

    @app.get("/health")
    async def health() -> dict:
        initialized_modes = {
            m: {
                "model_name_id": s["model_name"],
                "device": s["runtime_device"],
                "execution_devices": s["ov_exec_devices"],
            }
            for m, s in mode_state.items()
        }
        return {
            "status": "ok",
            "mode": startup_mode,
            "supports_request_mode_override": True,
            "supported_modes": sorted(supported_modes),
            "initialized_modes": initialized_modes,
        }

    return app


def _is_patched() -> bool:
    # Inline (no relative import) so this file runs standalone from Docker.
    try:
        import llmlingua
        src = Path(llmlingua.__file__).parent / "prompt_compressor.py"
        return "_digit_neighbor_radius" in src.read_text(encoding="utf-8")
    except Exception:
        return False


def start_server(args: argparse.Namespace) -> None:
    import uvicorn

    app = build_app(args)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    # Docker COPYs this file as lingua_server.py and invokes it directly.
    start_server(_parse_args())
