# Copyright (C) 2026 Intel Corporation
# SPDX-License-Identifier: Apache-2.0
"""Which prepared local models are multimodal and what they can embed.

A multimodal source is configured with the same fields as a text one --
`embedding_backend` (the runtime), `embedding_model` (a prepared model ID under
the shared model root), `embedding_device` -- and the same
engine defaults pattern (`ENGINE_VIDEO_EMBEDDING_*`, `ENGINE_IMAGE_EMBEDDING_*`).
The original asset scope and selected representation choose a compatible model
at source creation. Explicit models are recognized here:

- by the **directory**, when the path holds one (X-CLIP's `config.json` says
    `model_type: xclip`, or its two IR towers are present; a GME package has
    `gme_openvino_config.json`), so a model
  under any name is still recognized;
- else by the **id**'s prefix.

A model that is neither remains a document model unless media was requested;
an incompatible model cannot silently turn a media source into a document one.

Each entry also says what the model can embed (`supported_roles`, read off its
class without loading it), which runtimes it runs on, which of its inputs are
fixed by the model itself (X-CLIP's frames per clip). Missing models must be
downloaded and exported outside the engine before they can be loaded.
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, FrozenSet, Iterable, Mapping, Optional, Sequence

import config
from core.content import AUDIO, IMAGE, ROLE_L2_TRANSCRIPT, ROLE_LONG_VIDEO, ROLE_to_KIND, VIDEO
from core.multimodal.routing import (
    ASSET_ROLES, asset_families, representation, validate_model_options, validate_options,
)

VIDEO_CATEGORY = "video"
IMAGE_CATEGORY = "image"

#: Options that pick a model's behaviour rather than which model it is.
MODEL_PARAMS = ("frames_per_clip", "max_image_tokens")

def _category_defaults(category: str) -> Dict[str, str]:
    prefix = "VIDEO" if category == VIDEO_CATEGORY else "IMAGE"
    return {
        "backend": getattr(config, f"{prefix}_EMBEDDING_BACKEND"),
        "model_id": getattr(config, f"{prefix}_EMBEDDING_MODEL_ID"),
        "model_path": getattr(config, f"{prefix}_EMBEDDING_MODEL_PATH"),
        "device": getattr(config, f"{prefix}_EMBEDDING_DEVICE"),
    }


@dataclass(frozen=True)
class MultimodalModel:
    """One multimodal model family the engine can run."""

    name: str
    category: str
    model_id_prefixes: Sequence[str]
    # G18 transition only: main calls the OpenVINO provider llamaindex_openvino.
    # Accept its canonical name without changing main's provider architecture.
    backends: FrozenSet[str] = field(
        default_factory=lambda: frozenset({"llamaindex_openvino"})
    )

    # --- what it is -------------------------------------------------------------

    def implementation(self):
        raise NotImplementedError

    @property
    def supported_roles(self) -> FrozenSet[str]:
        return frozenset(self.implementation().supported_roles)

    @property
    def supported_asset_types(self) -> FrozenSet[str]:
        """Asset families supported through at least one representation.

        GME supports video *captions*, not raw video. Roles remain the precise
        capability boundary; an asset family alone never promises raw input.
        """
        return frozenset(
            kind for kind, roles in ASSET_ROLES.items()
            if roles & self.supported_roles
        )

    @property
    def supported_kinds(self) -> FrozenSet[str]:
        """The `block_kinds` a source with this model may ask for."""
        kinds = {ROLE_to_KIND[role] for role in self.supported_roles}
        # No model embeds sound; one that embeds transcripts embeds a
        # recording through what was said in it.
        if ROLE_L2_TRANSCRIPT in self.supported_roles:
            kinds.add(AUDIO)
        return frozenset(kinds)

    def matches_id(self, model_id: Optional[str]) -> bool:
        return bool(model_id) and any(
            str(model_id).startswith(prefix) for prefix in self.model_id_prefixes
        )

    def matches_dir(self, path: Path) -> bool:
        raise NotImplementedError

    # --- checking prepared artifacts -------------------------------------------

    def is_ready(self, path: Path) -> bool:
        raise NotImplementedError

    def preparation_problem(self, path: Path) -> str:
        """An actionable detail when the prepared package is incomplete."""
        return ""

    def fixed_params(self, path: Path) -> Dict[str, Any]:
        """Inputs the model itself fixes. A source may state them, not change them."""
        return {}

    def build(self, path: Path, device: str, params: Mapping[str, Any]):
        raise NotImplementedError


class _XClip(MultimodalModel):
    def implementation(self):
        from inference.multimodal.xclip_openvino import XClipOpenVinoEmbedding

        return XClipOpenVinoEmbedding

    @staticmethod
    def _config(path: Path) -> dict:
        try:
            value = json.loads((path / "config.json").read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def matches_dir(self, path: Path) -> bool:
        from inference.multimodal.xclip_openvino import find_ir_dir

        model_type = self._config(path).get("model_type")
        return model_type == "xclip" or (
            not model_type and find_ir_dir(str(path)) is not None
        )

    def is_ready(self, path: Path) -> bool:
        return not self.preparation_problem(path)

    def preparation_problem(self, path: Path) -> str:
        from inference.multimodal.xclip_openvino import find_ir_dir

        missing = []
        metadata = self._config(path)
        if metadata.get("model_type") != "xclip":
            missing.append('config.json with model_type="xclip"')
        vision = metadata.get("vision_config")
        frames = vision.get("num_frames") if isinstance(vision, dict) else None
        if not isinstance(frames, int) or isinstance(frames, bool) or frames <= 0:
            missing.append("config.json vision_config.num_frames (positive integer)")
        if not (path / "tokenizer_config.json").is_file():
            missing.append("tokenizer_config.json")
        if not (path / "tokenizer.json").is_file() and not all(
            (path / name).is_file() for name in ("vocab.json", "merges.txt")
        ):
            missing.append("tokenizer.json (or vocab.json + merges.txt)")
        if find_ir_dir(str(path)) is None:
            missing.append("xclip_video.xml/.bin and xclip_text.xml/.bin")
        return f"Missing or invalid X-CLIP package files: {', '.join(missing)}" if missing else ""

    def fixed_params(self, path: Path) -> Dict[str, Any]:
        frames = self._config(path).get("vision_config", {}).get("num_frames")
        return {"frames_per_clip": int(frames)} if frames else {}

    def build(self, path: Path, device: str, params: Mapping[str, Any]):
        return self.implementation()(
            model_path=str(path),
            device=device,
            frames_per_clip=int(params["frames_per_clip"]),
        )


class _Gme(MultimodalModel):
    def implementation(self):
        from inference.multimodal.gme_qwen2vl import GmeQwen2VLEmbedding

        return GmeQwen2VLEmbedding

    def _package(self, path: Path) -> Optional[Path]:
        from inference.multimodal.gme_qwen2vl import find_package

        try:
            return find_package(str(path))
        except (FileNotFoundError, OSError):
            return None

    def matches_dir(self, path: Path) -> bool:
        return self._package(path) is not None

    def is_ready(self, path: Path) -> bool:
        from inference.multimodal.gme_qwen2vl import choose_precision

        package = self._package(path)
        if package is None:
            return False
        try:
            choose_precision(package)
        except (OSError, ValueError, KeyError, TypeError):
            return False
        return True

    def build(self, path: Path, device: str, params: Mapping[str, Any]):
        return self.implementation()(
            model_path=str(path),
            device=device,
            max_image_tokens=params.get("max_image_tokens"),
        )


MODELS: Sequence[MultimodalModel] = (
    _XClip("xclip", VIDEO_CATEGORY, ("microsoft/xclip-",)),
    _Gme(
        "gme_qwen2vl", IMAGE_CATEGORY, ("Alibaba-NLP/gme-",),
        backends=frozenset({'llamaindex_openvino', 'native_openvino_gme'}),
    ),
)


# --- paths ----------------------------------------------------------------------


def local_path(model_path: str) -> Path:
    """An absolute path for `model_path`, which may be relative to the model dir."""
    from core.embedding import resolve_model_path, workspace_model_dir

    resolved = resolve_model_path(model_path)
    if os.path.isabs(resolved) and os.path.exists(resolved):
        return Path(resolved)
    return Path(workspace_model_dir(model_path))


def stored_path(path: Path) -> str:
    """How a path is written into a profile: relative to the model dir if inside it."""
    root = os.path.realpath(config.MODEL_DIR)
    real = os.path.realpath(str(path))
    if os.path.commonpath([real, root]) == root:
        return os.path.relpath(real, root)
    return str(path)


def path_for_id(model_id: str) -> Path:
    """Where a model named only by its id is kept: `$MODEL_DIR/<name>`."""
    return Path(config.MODEL_DIR) / str(model_id).rstrip("/").split("/")[-1]


# --- which model ----------------------------------------------------------------


def lookup(model_id: Optional[str], model_path: Optional[str]) -> Optional[MultimodalModel]:
    """The multimodal model these name, or None for a text model."""
    if model_path or model_id:
        path = local_path(model_path) if model_path else path_for_id(model_id)
        if path.is_dir():
            for model in MODELS:
                if model.matches_dir(path):
                    return model
    for model in MODELS:
        if model.matches_id(model_id):
            return model
    return None


def default_model(category: str) -> MultimodalModel:
    defaults = _category_defaults(category)
    model = lookup(defaults["model_id"], defaults["model_path"])
    if model is None or model.category != category:
        raise ValueError(
            f"The default {category} model ({defaults['model_id']!r} at "
            f"{defaults['model_path']!r}) is not a multimodal model the engine knows"
        )
    return model


def default_for(asset_types: Iterable[str], block_roles=None) -> Optional[MultimodalModel]:
    """Choose from original asset scope plus its selected representation."""
    options = {'asset_types': list(asset_types or ())}
    if block_roles is not None:
        options['block_roles'] = block_roles
    families = asset_families(options)
    if not families or families == {'document'}:
        return None
    _, roles = representation(options)
    # Long video is an intentionally uncovered member of the default video
    # representation, not a promise that X-CLIP can encode long recordings.
    needed = roles - {ROLE_LONG_VIDEO}
    for category in (VIDEO_CATEGORY, IMAGE_CATEGORY):
        # A broken, unrelated category default must not prevent image/caption
        # sources from being created (or vice versa).
        if not any(
            model.category == category and needed and needed <= model.supported_roles
            for model in MODELS
        ):
            continue
        model = default_model(category)
        if needed and needed <= model.supported_roles:
            return model
    raise ValueError(
        'No single default model embeds the selected asset representation: '
        'a source has one model; create separate sources/collections.'
    )


# --- resolving a source's model -------------------------------------------------


@dataclass(frozen=True)
class Resolved:
    """What a multimodal source embeds with, as fixed at creation."""

    model: MultimodalModel
    model_id: Optional[str]
    model_path: str          # as stored: relative to the model dir when inside it
    backend: str
    params: Dict[str, Any]   # what the source stated

    def record(self) -> Dict[str, Any]:
        return {
            "name": self.model.name,
            "category": self.model.category,
            "id": self.model_id,
            "path": self.model_path,
        }


def resolve(options: Mapping[str, Any]) -> Optional[Resolved]:
    """The multimodal model a source's options select, or None for a text source.

    Same precedence as a text source: what the source says, else the engine's
    `ENGINE_*_EMBEDDING_*` default for that kind of model. Nothing is downloaded
    here; this runs when a source is created and readiness is checked when attached.
    """
    model_id = options.get("embedding_model")
    validate_options(options)
    families = asset_families(options)
    model = lookup(model_id, None) if model_id else None
    media_requested = bool(families & {IMAGE, VIDEO, AUDIO})
    if not media_requested and model is None:
        # Document/figure filters do not turn PDF sources into media sources.
        # Unscoped media declarations were rejected above, independently of
        # backend selection; the remaining options retain document defaults.
        return None
    routing, roles = representation(options)
    if not model_id:
        model = default_for(routing['asset_types'], options.get('block_roles'))
    elif model is None:
        raise ValueError(
            f"Cannot identify embedding_model {model_id!r} as a supported media model; "
            f"check the prepared model package at {str(path_for_id(model_id))!r}"
        )
    needed = roles if options.get('block_roles') else roles - {ROLE_LONG_VIDEO}
    unsupported_roles = needed - model.supported_roles
    if unsupported_roles:
        raise ValueError(
            f"Model {model.name!r} does not support block_roles "
            f"{', '.join(sorted(unsupported_roles))} for the selected asset_types"
        )
    defaults = _category_defaults(model.category)
    if model_id:
        path = path_for_id(model_id)
    else:
        path = local_path(defaults["model_path"])
    backend = config.normalize_model_backend(
        str(options.get("embedding_backend") or defaults["backend"])
    )
    if backend not in model.backends:
        raise ValueError(
            f"Model {model.name!r} runs on {', '.join(sorted(model.backends))}, "
            f"not {backend!r}"
        )
    unsupported = set(routing['block_kinds']) - set(model.supported_kinds)
    if unsupported:
        raise ValueError(
            f"Model {model.name!r} embeds {', '.join(sorted(model.supported_kinds))}, "
            f"not {', '.join(sorted(unsupported))}"
        )
    return Resolved(
        model=model,
        model_id=model_id or defaults["model_id"],
        model_path=stored_path(path),
        backend=backend,
        params={**{key: options[key] for key in MODEL_PARAMS if key in options}, **routing},
    )


def load(record: Mapping[str, Any], options: Mapping[str, Any]):
    """Validate local artifacts and build the model a source's profile recorded.

    The model and its path come from the profile, so changing an engine default
    later does not change what an existing source embeds with. The device does
    not change what a vector means, so it follows the source, else the engine
    default for that kind of model, as it is now.
    """
    validate_model_options(options)
    model = next((m for m in MODELS if m.name == record.get("name")), None)
    if model is None:
        raise ValueError(f"Unknown multimodal model {record.get('name')!r}")
    path = local_path(str(record.get("path") or ""))
    if not model.is_ready(path):
        detail = model.preparation_problem(path)
        raise FileNotFoundError(
            f"No prepared {model.name} model at {str(path)!r}. "
            f"{detail + '. ' if detail else ''}Prepare its model, "
            "tokenizer, and OpenVINO weights before starting the engine; use "
            "ENGINE_MODEL_ROOT_PATH and select the package with embedding_model. "
            "The engine does not download or export models."
        )
    params = {key: options[key] for key in MODEL_PARAMS if key in options}
    for key, value in model.fixed_params(path).items():
        stated = params.get(key)
        if stated is not None and int(stated) != int(value):
            raise ValueError(
                f"{key}={stated} does not match the model's {value} "
                f"(fixed by the checkpoint at {str(path)!r})"
            )
        params[key] = value
    device = str(
        options.get("embedding_device") or _category_defaults(model.category)["device"]
    )
    return model.build(path, device, params)


def classify_dir(path: str) -> Optional[str]:
    """The multimodal model name a model directory holds, for the model list."""
    candidate = Path(path)
    for model in MODELS:
        if model.matches_dir(candidate):
            return model.name
    return None


__all__ = [
    "IMAGE_CATEGORY",
    "MODELS",
    "MultimodalModel",
    "Resolved",
    "VIDEO_CATEGORY",
    "classify_dir",
    "default_for",
    "default_model",
    "load",
    "local_path",
    "lookup",
    "resolve",
    "stored_path",
]
